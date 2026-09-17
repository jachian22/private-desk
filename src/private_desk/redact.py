from __future__ import annotations

import json
import re
from typing import Any

DROP_KEY_SUBSTR = re.compile(
    r"screenshot|image_b64|base64|clipboard|keystroke|cookie|frames?|video|har\b|\bdom\b|\bhtml\b|\bocr\b",
    re.I,
)
DROP_KEYS_EXACT = re.compile(
    r"^(screenshot|screenshots|image|images|image_b64|b64|video|html|dom|har|"
    r"cookie|cookies|header|headers|clipboard|keystroke|keystrokes|frame|frames|"
    r"ocr|payload_png|png|jpeg|webp)$",
    re.I,
)

AMOUNT_RE = re.compile(r"\$\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\$\d+\.\d{2}")
ACCOUNTISH_RE = re.compile(r"\b\d{8,}\b")
DATA_URI_RE = re.compile(r"data:image\/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+")
B64_BLOB_RE = re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")


def redact(value: Any) -> Any:
    """Drop CUA secrets from an untrusted payload. Safe to JSON-serialize."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            key = str(k)
            if DROP_KEYS_EXACT.match(key) or DROP_KEY_SUBSTR.search(key):
                continue
            out[key] = redact(v)
        return out
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def redact_text(text: str) -> str:
    return _redact_string(text)


def _redact_string(text: str) -> str:
    text = DATA_URI_RE.sub("[redacted-image]", text)
    text = B64_BLOB_RE.sub("[redacted-blob]", text)
    text = AMOUNT_RE.sub("[redacted-amount]", text)
    text = ACCOUNTISH_RE.sub("[redacted-number]", text)
    return text


def redact_json_text(text: str) -> str:
    try:
        return json.dumps(redact(json.loads(text)))
    except json.JSONDecodeError:
        return redact_text(text)


def event_to_dict(event: Any) -> dict[str, Any]:
    if hasattr(event, "model_dump"):
        try:
            data = event.model_dump(mode="json")
        except TypeError:
            data = event.model_dump()
        return data if isinstance(data, dict) else {"value": data}
    if isinstance(event, dict):
        return event
    payload: dict[str, Any] = {"type": getattr(event, "type", None)}
    for attr in ("text", "message", "content", "name", "status"):
        if hasattr(event, attr):
            payload[attr] = getattr(event, attr)
    return payload
