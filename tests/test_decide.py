import json
from types import SimpleNamespace

from private_desk.api import decide
from private_desk.cli import main
from private_desk.config import load_config, typesafe_status
from private_desk.jev.client import FakeJevClient, TypeSafeJevClient, JevUnavailable, VercelGatewayJevClient, live_jev_client, GATEWAY_EVALUATE_URL
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


def test_doctor_gateway_configured_no_leak(isolated, monkeypatch):
    from private_desk.doctor import run_doctor
    from private_desk.config import save_config, typesafe_status as status

    monkeypatch.setattr("private_desk.doctor._which", lambda _name: None)
    cfg = load_config()
    cfg.ai_gateway_api_key = "gw-test-do-not-print"
    save_config(cfg)
    assert status() == "gateway"
    payload = run_doctor(strict=False)
    assert payload["checks"]["typesafe"] == "gateway"
    blob = json.dumps(payload)
    assert "gw-test-do-not-print" not in blob
    assert "gw-test" not in blob


def test_gateway_env_preferred_over_typesafe(isolated, monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gw-from-env")
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-from-env")
    assert typesafe_status() == "gateway"
    client = live_jev_client()
    assert isinstance(client, VercelGatewayJevClient)
    from private_desk.doctor import run_doctor

    monkeypatch.setattr("private_desk.doctor._which", lambda _name: None)
    blob = json.dumps(run_doctor(strict=False))
    assert "gw-from-env" not in blob
    assert "sk-from-env" not in blob


def test_keychain_gateway_when_env_and_config_empty(isolated, monkeypatch):
    import subprocess

    monkeypatch.delenv("PRIVATE_DESK_SKIP_KEYCHAIN", raising=False)

    def fake_run(cmd, **kwargs):
        assert cmd[:3] == ["security", "find-generic-password", "-s"]
        assert "Vercel AI Gateway" in cmd
        assert "-w" in cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="vck_from_keychain\n", stderr="")

    monkeypatch.setattr("private_desk.config.subprocess.run", fake_run)
    from private_desk.config import ai_gateway_api_key, typesafe_status

    assert ai_gateway_api_key() == "vck_from_keychain"
    assert typesafe_status() == "gateway"


def test_keychain_gateway_not_used_in_tests(isolated):
    from private_desk.config import ai_gateway_api_key

    assert ai_gateway_api_key() == ""


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


def test_gateway_adapter_maps_boolean_and_choice(isolated):
    captured: dict = {}

    def fake_post(url, headers, body, timeout):
        captured["url"] = url
        captured["headers"] = {k: v for k, v in headers.items() if k.lower() != "authorization"}
        captured["auth"] = headers.get("Authorization", "")
        captured["body"] = json.loads(body)
        return {
            "answers": {
                "kind": {"type": "choice", "choice": "demo_open_repo", "probabilities": {"demo_open_repo": 1}},
                "next": {"type": "choice", "choice": "start"},
                "kick_now": {"type": "boolean", "probability": 0.91},
                "ask_first": {"type": "boolean", "probability": 0.1},
                "use_local_only": {"type": "boolean", "probability": 0.1},
                "mutating_ok": {"type": "boolean", "probability": 0.1},
                "secret_in_request": {"type": "boolean", "probability": 0.05},
            }
        }

    client = VercelGatewayJevClient("gw-secret", post=fake_post)
    from private_desk.config import Config
    from private_desk.kinds import load_kinds
    from private_desk.jev.questions import build_state

    real = load_kinds()
    state = build_state(utterance="open", kinds=real, cfg=Config(), job=None, desktop_busy=False)
    questions = build_questions(kinds=real, include_job=False)
    answers = client.ask(state, questions)
    assert captured["url"] == GATEWAY_EVALUATE_URL
    assert captured["headers"]["ai-model-id"] == "typesafe-ai/jev"
    assert captured["headers"]["ai-evaluation-model-specification-version"] == "4"
    assert captured["body"]["questions"]["kick_now"]["type"] == "boolean"
    assert captured["body"]["questions"]["kind"]["type"] == "choice"
    assert "providerOptions" not in captured["body"]
    assert "gw-secret" not in json.dumps(captured["body"])
    assert captured["auth"] == "Bearer gw-secret"
    assert answers.kind == "demo_open_repo"
    assert answers.next == "start"
    assert answers.kick_now == 0.91


def test_gateway_http_error_no_leak(monkeypatch):
    import urllib.error

    def boom(*_a, **_k):
        raise urllib.error.HTTPError(
            GATEWAY_EVALUATE_URL,
            401,
            "Unauthorized",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("private_desk.jev.client.urllib.request.urlopen", boom)
    client = VercelGatewayJevClient("gw-secret")
    try:
        client.ask(
            {"utterance": "x"},
            {"kick_now": {"type": "noul", "instructions": "k"}},
        )
    except JevUnavailable as exc:
        assert "401" in exc.message
        assert "gw-secret" not in exc.message
    else:
        raise AssertionError("expected JevUnavailable")


def test_gateway_403_asks_for_card(monkeypatch):
    import io
    import urllib.error

    payload = json.dumps(
        {"error": {"type": "customer_verification_required", "message": "add a card"}}
    ).encode()

    def boom(*_a, **_k):
        raise urllib.error.HTTPError(
            GATEWAY_EVALUATE_URL,
            403,
            "Forbidden",
            hdrs=None,
            fp=io.BytesIO(payload),
        )

    monkeypatch.setattr("private_desk.jev.client.urllib.request.urlopen", boom)
    client = VercelGatewayJevClient("gw-secret")
    try:
        client.ask({"n": 1}, {"odd": {"type": "noul", "instructions": "odd?"}})
    except JevUnavailable as exc:
        assert "403" in exc.message
        assert "credit card" in exc.message.lower()
        assert "gw-secret" not in exc.message
    else:
        raise AssertionError("expected JevUnavailable")


def test_decide_jev_uses_gateway(isolated, monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gw-secret")

    def fake_post(url, headers, body, timeout):
        payload = json.loads(body)
        assert payload["questions"]["kind"]["type"] == "choice"
        return {
            "answers": {
                "kind": {"type": "choice", "choice": "demo_open_repo"},
                "next": {"type": "choice", "choice": "start"},
                "kick_now": {"type": "boolean", "probability": 0.9},
                "ask_first": {"type": "boolean", "probability": 0.1},
                "use_local_only": {"type": "boolean", "probability": 0.1},
                "mutating_ok": {"type": "boolean", "probability": 0.1},
                "secret_in_request": {"type": "boolean", "probability": 0.05},
            }
        }

    monkeypatch.setattr("private_desk.jev.client._post_gateway", fake_post)
    result = decide("open the repo", policy="jev")
    assert result.ok
    assert result.payload["decision"]["kind"] == "demo_open_repo"
    assert result.payload["jev"]["kick_now"] == 0.9
    blob = json.dumps(result.payload)
    assert "gw-secret" not in blob
