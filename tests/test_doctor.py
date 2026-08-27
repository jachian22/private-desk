from private_desk.doctor import run_doctor
from private_desk.needs_you import classify_needs_you


def test_doctor_missing_holo_is_not_failure(isolated):
    payload = run_doctor(strict=False)
    assert payload["exit_code"] == 0
    assert payload["ok"] is True
    assert payload["checks"]["dummy_kinds"] == "ok"


def test_doctor_strict_fails_without_holo(isolated):
    payload = run_doctor(strict=True)
    if payload["checks"]["holo"] == "missing":
        assert payload["exit_code"] == 5
        assert payload["ok"] is False


def test_needs_you_token_not_false_positive_on_prompt():
    prompt = "Do not type passwords. If you see a login wall, wait."
    assert classify_needs_you("assistant", prompt) is None
    assert classify_needs_you("message", "NEEDS_YOU: needs_login") == "needs_login"
    assert classify_needs_you("session.paused", "") == "mfa_required"
