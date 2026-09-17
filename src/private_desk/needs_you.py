"""Classify Holo events for needs_you. Only match an explicit token or pause status."""

from __future__ import annotations

import re
from typing import Any

NEEDS_YOU_TOKEN = re.compile(
    r"NEEDS_YOU:\s*(mfa_required|needs_login|os_permission)\b",
    re.I,
)

PAUSE_TYPES = frozenset(
    {
        "pause",
        "paused",
        "session.paused",
        "user_input_required",
        "waiting_for_user",
    }
)

# Holo TrajectoryStatus.IDLE is end-of-turn success, not a human wait.
SESSION_PAUSE_STATUSES = frozenset({"paused"})
SESSION_END_STATUSES = frozenset(
    {"idle", "completed", "failed", "timed_out", "interrupted"}
)

INSTRUCTIONS = {
    "mfa_required": "Enter the code on your laptop. Do not send the code in chat.",
    "needs_login": "Sign in on your laptop. Do not send the password or code in chat.",
    "os_permission": "Grant Screen Recording and Accessibility on your laptop, then continue.",
}

FAIL_TOKEN = re.compile(
    r"(?<!reply )FAILED:\s*(ui_changed|session_expired|needs_login|timeout|unexpected_nav|guardrail|bank_unavailable)\b",
    re.I,
)

FAIL_MESSAGES = {
    "ui_changed": "The statements page did not match the expected layout.",
    "session_expired": "The site session expired during the job.",
    "needs_login": "No usable browser session; sign in on the laptop.",
    "timeout": "The job hit its time or step limit.",
    "unexpected_nav": "Navigation left the URL allowlist.",
    "guardrail": "The runner approached a denied action.",
    "bank_unavailable": "The site was unavailable.",
}


def _status_value(status: Any) -> str:
    if status is None:
        return ""
    return str(getattr(status, "value", status) or "").lower().replace("-", "_")


def _pause_kind(label: str | None) -> bool:
    kind = _status_value(label)
    return bool(kind) and (kind in PAUSE_TYPES or kind.endswith(".paused"))


def is_session_paused(status: Any) -> bool:
    return _status_value(status) in SESSION_PAUSE_STATUSES


def is_session_end(status: Any) -> bool:
    return _status_value(status) in SESSION_END_STATUSES


def event_caller_id(raw: dict[str, Any] | None) -> str:
    """Holo nests caller_id under data. The task prompt is caller_id=user."""
    if not raw:
        return ""
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    if not isinstance(data, dict):
        return ""
    return str(data.get("caller_id") or raw.get("caller_id") or "").lower()


def classify_needs_you(
    event_type: str | None,
    text: str,
    status: str | None = None,
    caller_id: str | None = None,
) -> str | None:
    # The kind prompt lists NEEDS_YOU: codes. Holo echoes that as a user message_event.
    if (caller_id or "").lower() == "user":
        return None
    token = NEEDS_YOU_TOKEN.search(text or "")
    if token:
        return token.group(1).lower()
    if _pause_kind(event_type) or _pause_kind(status):
        return "mfa_required"
    return None


def flatten_text(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " ".join(flatten_text(v) for v in obj.values())
    if isinstance(obj, list):
        return " ".join(flatten_text(v) for v in obj)
    return str(obj)


def instruction_for(code: str) -> str:
    return INSTRUCTIONS.get(code, INSTRUCTIONS["mfa_required"])


def event_agent_kind(raw: dict[str, Any] | None) -> str:
    if not raw:
        return ""
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    if not isinstance(data, dict):
        return ""
    return str(data.get("kind") or "").lower()


def text_for_needs_you(raw: dict[str, Any] | None) -> str:
    """Skip policy/observation: those quote NEEDS_YOU: from the task prompt."""
    kind = event_agent_kind(raw)
    if kind in {"policy_event", "observation_event"}:
        return ""
    return answer_text(raw) or flatten_text(raw)


def answer_text(raw: dict[str, Any] | None) -> str:
    """Final Holo answer only. Policy/reasoning that quotes DONE: must not count."""
    if not raw:
        return ""
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    if not isinstance(data, dict):
        return ""
    kind = str(data.get("kind") or "").lower()
    if kind == "answer_event":
        return flatten_text(data.get("answer"))
    if kind == "tool_result":
        req = data.get("tool_req") if isinstance(data.get("tool_req"), dict) else {}
        if str(req.get("tool_name") or "") == "answer":
            args = req.get("args") if isinstance(req.get("args"), dict) else {}
            return flatten_text(args.get("content"))
    return ""


def classify_done(
    text: str,
    expected: str | None,
    caller_id: str | None = None,
) -> bool:
    """True when a non-user answer is a line `DONE: <token>`. Prompt quotes do not count."""
    token = (expected or "").strip().lower()
    if not token:
        return False
    if (caller_id or "").lower() == "user":
        return False
    body = text or ""
    if re.search(r"could not be completed|was unable to|task could not", body, re.I):
        return False
    return bool(re.search(rf"(?m)^DONE:\s*{re.escape(token)}\s*$", body, re.I))


def classify_failure(text: str) -> str | None:
    token = FAIL_TOKEN.search(text or "")
    if token:
        return token.group(1).lower()
    return None


def classify_timeout(text: str) -> bool:
    lowered = (text or "").lower()
    return any(
        needle in lowered
        for needle in ("timeout", "timed out", "max_time", "max_steps", "max steps")
    )


def fail_message(code: str) -> str:
    return FAIL_MESSAGES.get(code, "The job failed.")
