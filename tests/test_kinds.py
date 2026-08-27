from private_desk.api import start_job
from private_desk.kinds import load_kinds


def test_unknown_kind(isolated):
    result = start_job("sync_chase", {}, None)
    assert result.ok is False
    assert result.exit_code == 2
    assert result.payload["error"]["code"] == "kind_denied"


def test_start_rejects_password_param(isolated):
    result = start_job("demo_dummy_files", {"password": "x"}, None)
    assert result.ok is False
    assert result.exit_code == 2
    assert result.payload["error"]["code"] == "kind_denied"
    assert "password" in result.payload["error"]["message"]


def test_kinds_never_include_prompt(isolated):
    kinds = load_kinds()
    assert "demo_dummy_files" in kinds
    assert "session_canary_template" not in kinds
    from private_desk.api import list_kinds

    listed = list_kinds().payload["kinds"]
    for item in listed:
        assert "prompt" not in item
        assert item["id"] != "session_canary_template"
