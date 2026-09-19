from private_desk.config import Config
from private_desk.jev.mixer import Answers, Facts, mix
from private_desk.jev.secrets import utterance_is_secret
from private_desk.kinds import load_kinds
from private_desk.jev.questions import build_state


def _facts(isolated, *, secret=False, desktop_busy=False, job=None, allow_mutating=False, extra_kind=None):
    kinds = load_kinds()
    if extra_kind:
        kinds[extra_kind.id] = extra_kind
    return Facts(
        utterance="x",
        kinds=kinds,
        cfg=Config(allow_mutating=allow_mutating),
        job=job,
        desktop_busy=desktop_busy,
        secret=secret,
    ), kinds


def test_unknown_kind_tells_them(isolated):
    facts, _ = _facts(isolated)
    decision = mix(Answers(kind="none", next="start", kick_now=0.9), facts)
    assert decision.next == "tell_them"
    assert decision.blocked_by == "none"
    assert decision.legal is False
    assert decision.invocation is None


def test_secret_wins_over_kick_now(isolated):
    facts, _ = _facts(isolated, secret=True)
    decision = mix(
        Answers(kind="demo_open_repo", next="start", kick_now=0.99),
        facts,
    )
    assert decision.blocked_by == "secret_in_request"
    assert decision.next == "tell_them"


def test_utterance_secret_skips_session_canary_words():
    assert utterance_is_secret("here's my password x") is True
    assert utterance_is_secret("password: hunter2") is True
    assert utterance_is_secret("open the repo") is False
    assert utterance_is_secret("session canary") is False
    assert utterance_is_secret("star the repo") is False


def test_hosted_on_private_refused(isolated):
    from private_desk.kinds import _load_file

    kinds_dir = isolated / "config" / "kinds"
    kinds_dir.mkdir(parents=True)
    path = kinds_dir / "private_hosted.yaml"
    path.write_text(
        """
id: private_hosted_demo
title: Private hosted
risk: read_only
inference: hosted
may_need_you: false
runner: dummy
params:
  type: object
  additionalProperties: false
  properties: {}
prompt: SECRET_PROMPT
"""
    )
    kind = _load_file(path)
    facts, _ = _facts(isolated, extra_kind=kind)
    decision = mix(Answers(kind="private_hosted_demo", next="start", kick_now=0.9), facts)
    assert decision.blocked_by == "hosted_on_private"


def test_needs_you_never_starts(isolated):
    facts, _ = _facts(
        isolated,
        job={
            "job_id": "job_test",
            "kind": "demo_open_repo",
            "state": "needs_you",
            "user_action": {"code": "needs_login", "instruction": "Do it on the laptop.", "next": "resume"},
        },
    )
    decision = mix(
        Answers(kind="demo_open_repo", next="start", kick_now=0.99, job_class="needs_you"),
        facts,
    )
    assert decision.blocked_by == "needs_you"
    assert decision.next == "tell_them"
    assert decision.user_action["instruction"] == "Do it on the laptop."


def test_mutating_denied_without_flag(isolated):
    facts, _ = _facts(isolated, allow_mutating=False)
    decision = mix(
        Answers(kind="demo_star_repo", next="start", kick_now=0.9, ask_first=0.1, mutating_ok=0.9),
        facts,
    )
    assert decision.blocked_by == "mutating_disabled"


def test_desktop_busy_blocks_start(isolated):
    facts, _ = _facts(isolated, desktop_busy=True)
    decision = mix(Answers(kind="demo_open_repo", next="start", kick_now=0.9), facts)
    assert decision.blocked_by == "desktop_busy"


def test_keep_waiting_when_this_job_running(isolated):
    facts, _ = _facts(
        isolated,
        desktop_busy=True,
        job={"job_id": "job_r", "kind": "demo_open_repo", "state": "running"},
    )
    decision = mix(Answers(kind="demo_dummy_files", next="start", kick_now=0.9), facts)
    assert decision.blocked_by == "keep_waiting"


def test_ask_first_blocks_start(isolated):
    facts, _ = _facts(isolated, allow_mutating=True)
    decision = mix(
        Answers(kind="demo_star_repo", next="start", kick_now=0.9, ask_first=0.7),
        facts,
    )
    assert decision.blocked_by == "ask_first"
    assert decision.ask_first is True
    assert decision.invocation is None


def test_kick_now_below_threshold(isolated):
    facts, _ = _facts(isolated)
    decision = mix(Answers(kind="demo_open_repo", next="start", kick_now=0.49), facts)
    assert decision.blocked_by == "kick_now_false"


def test_required_params_block(isolated):
    from private_desk.kinds import _load_file

    kinds_dir = isolated / "config" / "kinds"
    kinds_dir.mkdir(parents=True)
    path = kinds_dir / "needs_params.yaml"
    path.write_text(
        """
id: needs_params
title: Needs params
risk: read_only
inference: local
runner: dummy
params:
  type: object
  additionalProperties: false
  required: [product]
  properties:
    product:
      type: string
      enum: [checking]
prompt: hidden
"""
    )
    kind = _load_file(path)
    facts, _ = _facts(isolated, extra_kind=kind)
    decision = mix(Answers(kind="needs_params", next="start", kick_now=0.9), facts)
    assert decision.blocked_by == "required_params"


def test_legal_open_repo(isolated):
    facts, _ = _facts(isolated)
    decision = mix(Answers(kind="demo_open_repo", next="start", kick_now=0.9), facts)
    assert decision.legal is True
    assert decision.next == "start"
    assert decision.kind == "demo_open_repo"
    assert decision.invocation == {"argv": ["start", "demo_open_repo"]}


def test_doctor_without_kind(isolated):
    facts, _ = _facts(isolated)
    decision = mix(Answers(kind="none", next="doctor", kick_now=0.1), facts)
    assert decision.legal is True
    assert decision.next == "doctor"
    assert decision.invocation == {"argv": ["doctor"]}


def test_state_builder_never_includes_prompt(isolated):
    kinds = load_kinds()
    assert any(k.prompt for k in kinds.values())
    state = build_state(
        utterance="open the repo",
        kinds=kinds,
        cfg=Config(),
        job=None,
        desktop_busy=False,
    )
    blob = str(state)
    assert "prompt" not in blob
    for kind in kinds.values():
        if kind.prompt:
            assert kind.prompt not in blob
    assert "demo_open_repo" in {c["id"] for c in state["kinds"]}
