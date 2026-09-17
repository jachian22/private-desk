from datetime import datetime, timezone

from private_desk.redact import event_to_dict, redact


def test_redaction_strips_screenshot_amount_and_account():
    payload = {
        "screenshot": "iVBORw0KGgoAAAANSUhEUg==",
        "image_b64": "data:image/png;base64,AAAA",
        "content": "data:image/png;base64," + ("A" * 220) + "==",
        "note": "Balance $12,345.67 for account 123456789012",
        "nested": {"html": "<html>secret</html>", "ok": "hello"},
        "cookies": ["session=abc"],
    }
    out = redact(payload)
    dumped = str(out)
    assert "screenshot" not in out
    assert "image_b64" not in out
    assert "cookies" not in out
    assert "html" not in out["nested"]
    assert out["nested"]["ok"] == "hello"
    assert "$12,345.67" not in dumped
    assert "[redacted-amount]" in out["note"]
    assert "123456789012" not in dumped
    assert "[redacted-number]" in out["note"]
    assert "iVBORw0KGgo" not in dumped
    assert "AAAA" not in dumped or "[redacted" in out["content"]


def test_event_to_dict_json_mode_datetimes():
    class FakeEvent:
        def model_dump(self, mode: str = "python"):
            stamp = datetime(2026, 8, 28, tzinfo=timezone.utc)
            if mode == "json":
                return {"type": "AgentEvent", "timestamp": stamp.isoformat()}
            return {"type": "AgentEvent", "timestamp": stamp}

    raw = event_to_dict(FakeEvent())
    assert raw["type"] == "AgentEvent"
    assert isinstance(raw["timestamp"], str)
