from private_desk.needs_you import (
    answer_text,
    classify_done,
    classify_failure,
    classify_needs_you,
    classify_timeout,
    event_caller_id,
    fail_message,
    flatten_text,
    is_session_end,
    is_session_paused,
    text_for_needs_you,
)


def test_needs_you_token_not_false_positive_on_prompt():
    prompt = "Do not type passwords. If you see a login wall, wait."
    assert classify_needs_you("assistant", prompt) is None
    assert classify_needs_you("message", "NEEDS_YOU: needs_login") == "needs_login"
    assert classify_needs_you("session.paused", "") == "mfa_required"


def test_task_prompt_echo_is_not_needs_you():
    """Live bug: first Holo event is the kind prompt, which lists NEEDS_YOU: codes."""
    raw = {
        "type": "AgentEvent",
        "data": {
            "kind": "message_event",
            "caller_id": "user",
            "content": [
                "Reply with exactly one of:\n"
                "NEEDS_YOU: needs_login\n"
                "NEEDS_YOU: mfa_required\n"
                "Then wait.\n"
            ],
        },
    }
    assert event_caller_id(raw) == "user"
    text = flatten_text(raw)
    assert "NEEDS_YOU: needs_login" in text
    assert classify_needs_you("AgentEvent", text, caller_id="user") is None
    assert classify_needs_you("AgentEvent", "NEEDS_YOU: needs_login", caller_id="assistant") == (
        "needs_login"
    )


def test_done_token_skips_prompt_echo_and_requires_assistant():
    prompt = "When the page is visible, reply with exactly:\nDONE: open_repo\nThen exit."
    assert classify_done(prompt, "open_repo", caller_id="user") is False
    assert classify_done("DONE: open_repo", "open_repo", caller_id="assistant") is True
    assert classify_done("could not be completed", "open_repo", caller_id="assistant") is False
    assert classify_done("DONE: open_repo", "", caller_id="assistant") is False
    quoted = "6. When public repository page is visible, reply with DONE: open_repo"
    assert classify_done(quoted, "open_repo", caller_id="assistant") is False


def test_policy_quote_of_done_token_is_not_success():
    """Live bug: Holo quoted DONE: open_repo in reasoning, job marked succeeded."""
    policy = {
        "type": "AgentEvent",
        "data": {
            "kind": "policy_event",
            "reasoning_content": (
                "When public repository page is visible, reply with DONE: open_repo\n"
                "I was unable to open Chrome."
            ),
        },
    }
    assert answer_text(policy) == ""
    assert classify_done(flatten_text(policy), "open_repo", caller_id="assistant") is False
    fail_answer = {
        "type": "AgentEvent",
        "data": {
            "kind": "answer_event",
            "answer": "The task could not be completed.\nDONE: open_repo\n",
        },
    }
    text = answer_text(fail_answer)
    assert "DONE: open_repo" in text
    assert classify_done(text, "open_repo") is False
    ok = {"type": "AgentEvent", "data": {"kind": "answer_event", "answer": "DONE: open_repo\n"}}
    assert classify_done(answer_text(ok), "open_repo") is True


def test_policy_quote_of_needs_you_is_not_pause():
    policy = {
        "type": "AgentEvent",
        "data": {
            "kind": "policy_event",
            "reasoning_content": (
                "If login appears, reply NEEDS_YOU: needs_login. "
                "The repo page never appeared."
            ),
        },
    }
    assert text_for_needs_you(policy) == ""
    assert classify_needs_you("AgentEvent", text_for_needs_you(policy)) is None
    live = {"type": "AgentEvent", "data": {"kind": "answer_event", "answer": "NEEDS_YOU: needs_login\n"}}
    assert classify_needs_you("AgentEvent", text_for_needs_you(live)) == "needs_login"
    tool = {
        "type": "AgentEvent",
        "data": {
            "kind": "tool_result",
            "tool_req": {
                "tool_name": "answer",
                "args": {"content": "NEEDS_YOU: needs_login"},
            },
        },
    }
    assert text_for_needs_you(tool) == "NEEDS_YOU: needs_login"
    assert classify_needs_you("AgentEvent", text_for_needs_you(tool)) == "needs_login"


def test_needs_you_token_codes():
    assert classify_needs_you("assistant", "NEEDS_YOU: mfa_required") == "mfa_required"
    assert classify_needs_you("assistant", "NEEDS_YOU: os_permission") == "os_permission"


def test_quiet_pause_maps_to_needs_you():
    for event_type in (
        "pause",
        "paused",
        "session.paused",
        "waiting_for_user",
        "user_input_required",
        "agent.paused",
    ):
        assert classify_needs_you(event_type, "") == "mfa_required", event_type


def test_quiet_pause_via_status_field():
    assert classify_needs_you("session.update", "", status="PAUSED") == "mfa_required"
    assert classify_needs_you("session.update", "", status="paused") == "mfa_required"
    assert classify_needs_you("session.update", "", status="running") is None
    # Holo IDLE is end-of-turn success, not a human wait.
    assert classify_needs_you("session.update", "", status="idle") is None
    assert classify_needs_you("idle", "") is None


def test_normal_event_types_are_not_needs_you():
    for event_type in ("assistant", "message", "step", "tool", "session.started"):
        assert classify_needs_you(event_type, "Opening the browser") is None


def test_failure_tokens_map_to_stable_codes():
    assert classify_failure("FAILED: ui_changed") == "ui_changed"
    assert classify_failure("FAILED: session_expired") == "session_expired"
    assert classify_failure("FAILED: unexpected_nav") == "unexpected_nav"
    assert classify_failure("FAILED: guardrail") == "guardrail"
    assert classify_failure("The page looks different") is None
    assert (
        classify_failure("If the layout is wrong, reply FAILED: ui_changed and stop.")
        is None
    )
    assert "layout" in fail_message("ui_changed")
    assert "$" not in fail_message("ui_changed")


def test_timeout_classifier():
    assert classify_timeout("Hit max_time_s") is True
    assert classify_timeout("max steps exceeded") is True
    assert classify_timeout("HoloDesktop session failed") is False


def test_session_paused_is_not_idle():
    assert is_session_paused("paused") is True
    assert is_session_paused("PAUSED") is True
    assert is_session_paused("idle") is False
    assert is_session_end("idle") is True
    assert is_session_end("completed") is True
    assert is_session_end("paused") is False
