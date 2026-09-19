"""Utterance secret scan. Runs before any TypeSafe call. Not param-key SECRET_KEY_RE."""

from __future__ import annotations

import re

# Offer/assignment of a secret. Do not match bare "session" (session canary).
SECRET_UTTERANCE_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:password|passwd|otp|mfa|secret|cookie|ssn|account[_\s-]?number|routing(?:\s*number)?)\s*(?:is\b|:|=)"
    r"|\b(?:here'?s|here is)\s+(?:my\s+)?(?:password|otp|passwd)\b"
    r"|\bmy\s+(?:password|otp|passwd)\b"
    r"|--param\s+\S*(?:password|otp|secret|token|cookie)="
    r")"
)


def utterance_is_secret(utterance: str) -> bool:
    return bool(SECRET_UTTERANCE_RE.search(utterance or ""))
