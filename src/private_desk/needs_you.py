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

INSTRUCTIONS = {
    "mfa_required": "Enter the code on your laptop. Do not send the code in chat.",
    "needs_login": "Sign in on your laptop. Do not send the password or code in chat.",
    "os_permission": "Grant Screen Recording and Accessibility on your laptop, then continue.",
}


def classify_needs_you(event_type: str | None, text: str) -> str | None:
    token = NEEDS_YOU_TOKEN.search(text or "")
    if token:
        return token.group(1).lower()
    kind = (event_type or "").lower().replace("-", "_")
    if kind in PAUSE_TYPES or kind.endswith(".paused"):
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
