import json
from types import SimpleNamespace

from private_desk.api import decide
from private_desk.cli import main
from private_desk.config import load_config, typesafe_status
from private_desk.jev.client import FakeJevClient, TypeSafeJevClient, JevUnavailable
from private_desk.jev.mixer import Answers
from private_desk.jev.questions import build_questions


def test_doctor_typesafe_missing_does_not_print_key(isolated, monkeypatch):
    from private_desk.doctor import run_doctor

    monkeypatch.setattr("private_desk.doctor._which", lambda _name: None)
    payload = run_doctor(strict=False)
    assert payload["checks"]["typesafe"] == "missing"
    blob = json.dumps(payload)
    assert "sk-" not in blob


def test_doctor_typesafe_configured_no_leak(isolated, monkeypatch):
    from private_desk.doctor import run_doctor
    from private_desk.config import save_config

    monkeypatch.setattr("private_desk.doctor._which", lambda _name: None)
    cfg = load_config()
    cfg.typesafe_api_key = "sk-test-do-not-print"
    save_config(cfg)
    assert typesafe_status() == "configured"
    payload = run_doctor(strict=False)
    assert payload["checks"]["typesafe"] == "configured"
    blob = json.dumps(payload)
    assert "sk-test-do-not-print" not in blob
    assert "sk-test" not in blob


def test_env_key_wins(isolated, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-from-env")
    assert typesafe_status() == "configured"
    from private_desk.doctor import run_doctor

    monkeypatch.setattr("private_desk.doctor._which", lambda _name: None)
    blob = json.dumps(run_doctor(strict=False))
    assert "sk-from-env" not in blob


def test_dump_state_no_api_no_prompt(isolated):
    result = decide("open the repo", dump_state=True)
    assert result.ok
    assert result.payload["decision"] is None
    dump = result.payload["dump"]
    assert dump["state"]["utterance"] == "open the repo"
    assert "prompt" not in json.dumps(dump)
    assert "kind" in dump["questions"]
    assert "none" in dump["questions"]["kind"]["criteria"]


def test_scripted_open_repo(isolated):
    result = decide("open the repo", policy="scripted")
    assert result.ok
    assert result.payload["decision"]["next"] == "start"
    assert result.payload["decision"]["kind"] == "demo_open_repo"
    assert result.payload["decision"]["legal"] is True
    assert result.payload["invocation"]["argv"] == ["start", "demo_open_repo"]


def test_scripted_dummy(isolated):
    result = decide("write dummy files", policy="scripted")
    assert result.payload["decision"]["kind"] == "demo_dummy_files"
    assert result.payload["invocation"]["argv"] == ["start", "demo_dummy_files"]


def test_scripted_star_mutating_off(isolated):
    result = decide("star the repo", policy="scripted")
    assert result.payload["decision"]["next"] == "tell_them"
    assert result.payload["decision"]["blocked_by"] == "mutating_disabled"
    assert result.payload["invocation"] is None


def test_scripted_star_asks_first_when_mutating_allowed(isolated):
    from private_desk.config import save_config

    cfg = load_config()
    cfg.allow_mutating = True
    save_config(cfg)
    result = decide("star the repo", policy="scripted")
    assert result.payload["decision"]["blocked_by"] == "ask_first"
    assert result.payload["decision"]["ask_first"] is True
    assert result.payload["invocation"] is None


def test_scripted_dino_asks_first(isolated):
    result = decide("play chrome://dino", policy="scripted")
    assert result.ok
    assert result.payload["decision"]["kind"] == "demo_dino"
    assert result.payload["decision"]["blocked_by"] == "ask_first"
    assert result.payload["decision"]["ask_first"] is True
    assert result.payload["invocation"] is None


def test_scripted_tweet_needs_canned_param(isolated):
    result = decide("get the word out", policy="scripted")
    assert result.payload["decision"]["kind"] == "demo_post_x"
    assert result.payload["decision"]["blocked_by"] == "required_params"
    assert result.payload["invocation"] is None


def test_scripted_unknown(isolated):
    result = decide("make me a sandwich", policy="scripted")
    assert result.payload["decision"]["blocked_by"] == "none"
    assert result.payload["invocation"] is None


def test_secret_utterance_refuses_before_client(isolated):
    client = FakeJevClient(Answers(kind="demo_open_repo", next="start", kick_now=0.99))
    result = decide("here's my password hunter2", client=client)
    assert result.ok
    assert result.payload["decision"]["blocked_by"] == "secret_in_request"
    assert client.calls == []
    assert result.payload["jev"] is None


def test_injected_answers_open_repo(isolated):
    result = decide(
        "please do the github thing",
        answers=Answers(kind="demo_open_repo", next="start", kick_now=0.8),
    )
    assert result.payload["decision"]["legal"] is True
    assert result.payload["invocation"]["argv"] == ["start", "demo_open_repo"]
    assert result.payload["jev"]["kick_now"] == 0.8


def test_missing_key_is_jev_unavailable(isolated):
    result = decide("open the repo", policy="jev")
    assert result.ok is False
    assert result.exit_code == 5
    assert result.payload["error"]["code"] == "jev_unavailable"


def test_fake_client_used_when_passed(isolated):
    client = FakeJevClient(Answers(kind="demo_dummy_files", next="start", kick_now=0.9))
    result = decide("underspecified", client=client)
    assert result.ok
    assert len(client.calls) == 1
    state, questions = client.calls[0]
    assert "prompt" not in json.dumps(state)
    assert "prompt" not in json.dumps(questions)
    assert result.payload["decision"]["kind"] == "demo_dummy_files"


def test_cli_scripted_and_dump(isolated, capsys):
    assert main(["decide", "--utterance", "open the repo", "--policy", "scripted"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["decision"]["kind"] == "demo_open_repo"
    assert "job_id" not in json.dumps(out)

    assert main(["decide", "--utterance", "open the repo", "--dump-state"]) == 0
    dump_out = json.loads(capsys.readouterr().out)
    assert dump_out["decision"] is None
    assert dump_out["dump"]["state"]["utterance"] == "open the repo"


def test_cli_secret(isolated, capsys):
    assert main(["decide", "--utterance", "here's my password x", "--policy", "scripted"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["decision"]["blocked_by"] == "secret_in_request"


def test_decide_does_not_start(isolated):
    from private_desk import jobs

    decide("open the repo", policy="scripted")
    assert jobs.list_jobs() == []


def test_job_id_not_found(isolated):
    result = decide("is it done?", job_id="job_missing", policy="scripted")
    assert result.exit_code == 3
    assert result.payload["error"]["code"] == "not_found"


def test_typesafe_adapter_reads_mock(isolated, monkeypatch):
    class _Ans:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class _Resp:
        choices = {
            "kind": _Ans(choice="demo_open_repo"),
            "next": _Ans(choice="start"),
        }
        nouls = {
            "kick_now": _Ans(noul=0.91),
            "ask_first": _Ans(noul=0.1),
            "use_local_only": _Ans(noul=0.1),
            "mutating_ok": _Ans(noul=0.1),
            "secret_in_request": _Ans(noul=0.05),
        }

    class _CM:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def system_one(self, **kw):
            assert "kinds" in kw["state"]
            assert "kind" in kw["questions"]
            return _Resp()

    fake_mod = SimpleNamespace(
        Choice=lambda **kw: ("choice", kw),
        Noul=lambda **kw: ("noul", kw),
        TypeSafeClient=lambda **kw: _CM(),
    )
    monkeypatch.setitem(__import__("sys").modules, "typesafe_sdk", fake_mod)
    client = TypeSafeJevClient("sk-test")
    from private_desk.kinds import load_kinds
    from private_desk.config import Config
    from private_desk.jev.questions import build_state

    real = load_kinds()
    state = build_state(utterance="open", kinds=real, cfg=Config(), job=None, desktop_busy=False)
    questions = build_questions(kinds=real, include_job=False)
    answers = client.ask(state, questions)
    assert answers.kind == "demo_open_repo"
    assert answers.kick_now == 0.91


def test_typesafe_import_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def boom(name, *a, **k):
        if name == "typesafe_sdk":
            raise ImportError("no sdk")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", boom)
    client = TypeSafeJevClient("sk-test")
    try:
        client.ask({"utterance": "x"}, {"kind": {"type": "choice", "instructions": "k", "criteria": {"none": "n"}}})
    except JevUnavailable as exc:
        assert "typesafe-sdk" in exc.message
    else:
        raise AssertionError("expected JevUnavailable")
