from private_desk.api import list_kinds, start_job
from private_desk.config import Config
from private_desk.kinds import interpolate_prompt, load_kinds
from private_desk.runners import artifact_dir_for


def test_open_repo_kind_has_confirm_token(isolated):
    kind = load_kinds()["demo_open_repo"]
    assert kind.confirm_token == "open_repo"
    assert kind.launch_url == "{repo_url}"
    assert kind.launch_isolated is True
    listed = list_kinds().payload["kinds"]
    item = next(k for k in listed if k["id"] == "demo_open_repo")
    assert "confirm_token" not in item
    assert "prompt" not in item
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
    assert "session_canary_github" not in kinds

    listed = list_kinds().payload["kinds"]
    for item in listed:
        assert "prompt" not in item
        assert item["id"] != "session_canary_template"


def test_private_canary_listed_without_prompt(isolated):
    kinds_dir = isolated / "config" / "kinds"
    kinds_dir.mkdir(parents=True)
    (kinds_dir / "session_canary_github.yaml").write_text(
        """
id: session_canary_github
title: GitHub session canary
description: Confirm a GitHub session in the dedicated Chrome profile.
risk: read_only
inference: local
may_need_you: true
runner: holo
url_allowlist:
  - https://github.com/
denied_actions:
  - star
params:
  type: object
  additionalProperties: false
  properties: {}
prompt: |
  Open Chrome profile {browser_profile}.
  Go to github.com. Never type passwords.
  SECRET_SHOULD_NOT_LEAK
"""
    )
    kinds = load_kinds()
    assert "session_canary_github" in kinds
    assert "SECRET_SHOULD_NOT_LEAK" in kinds["session_canary_github"].prompt

    listed = list_kinds().payload["kinds"]
    item = next(k for k in listed if k["id"] == "session_canary_github")
    assert "prompt" not in item
    assert "SECRET_SHOULD_NOT_LEAK" not in str(item)
    assert item["inference"] == "local"
    assert item["may_need_you"] is True
    assert item["risk"] == "read_only"


def test_private_kind_wins_on_id_clash(isolated):
    kinds_dir = isolated / "config" / "kinds"
    kinds_dir.mkdir(parents=True)
    (kinds_dir / "demo_dummy_files.yaml").write_text(
        """
id: demo_dummy_files
title: Private override
description: Should win over the public kind.
risk: read_only
inference: local
may_need_you: false
runner: files
prompt: hidden
"""
    )
    kinds = load_kinds()
    assert kinds["demo_dummy_files"].title == "Private override"
    item = next(k for k in list_kinds().payload["kinds"] if k["id"] == "demo_dummy_files")
    assert item["title"] == "Private override"
    assert "prompt" not in item


def test_canary_prompt_interpolates_browser_profile(isolated):
    kind = load_kinds()["demo_open_repo"]
    kind.prompt = "Open {browser}. Use profile {browser_profile}. Never type passwords."
    extra = {
        "browser": "Firefox",
        "browser_profile": "private-desk",
        "artifact_dir": "x",
        "date": "2026-08-28",
        "repo_url": "https://github.com",
    }
    text = interpolate_prompt(kind, {}, extra)
    assert text == "Open Firefox. Use profile private-desk. Never type passwords."


EXAMPLE_KIND = """
id: sync_example_statements
title: Example statement download
description: Shape-only private kind for tests. Not a bank.
risk: read_only
inference: local
may_need_you: true
runner: dummy
requires_artifacts: true
url_allowlist:
  - https://example.com/
denied_actions:
  - transfer
  - pay
  - send_money
  - wire
  - zelle
  - submit_payment
params:
  type: object
  additionalProperties: false
  required: [product, period]
  properties:
    product:
      type: string
      enum: [checking, savings, credit]
    period:
      type: string
      enum: [last_statement, last_3_statements]
artifacts:
  dir_template: "{artifact_root}/{date}/{kind}-{product}"
prompt: |
  Download statements for {product} / {period} into {artifact_dir}.
  SECRET_SHOULD_NOT_LEAK
"""


def _write_example_kind(isolated):
    kinds_dir = isolated / "config" / "kinds"
    kinds_dir.mkdir(parents=True, exist_ok=True)
    (kinds_dir / "sync_example_statements.yaml").write_text(EXAMPLE_KIND)
    return kinds_dir


def test_private_statement_kind_listed_without_prompt(isolated):
    _write_example_kind(isolated)
    listed = list_kinds().payload["kinds"]
    item = next(k for k in listed if k["id"] == "sync_example_statements")
    assert "prompt" not in item
    assert "SECRET_SHOULD_NOT_LEAK" not in str(item)
    assert item["inference"] == "local"
    assert item["may_need_you"] is True
    assert item["risk"] == "read_only"
    assert item["params"]["required"] == ["product", "period"]
    assert item["params"]["additionalProperties"] is False


def test_statement_params_required_and_enum(isolated):
    _write_example_kind(isolated)
    missing = start_job("sync_example_statements", {}, None)
    assert missing.ok is False
    assert missing.payload["error"]["code"] == "kind_denied"
    bad = start_job(
        "sync_example_statements",
        {"product": "brokerage", "period": "last_statement"},
        None,
    )
    assert bad.ok is False
    assert bad.payload["error"]["code"] == "kind_denied"


def test_dir_template_interpolates_validated_params(isolated):
    _write_example_kind(isolated)
    kind = load_kinds()["sync_example_statements"]
    path = artifact_dir_for(
        kind,
        Config(),
        {"product": "checking", "period": "last_statement"},
    )
    assert path.name == "sync_example_statements-checking"
    assert "checking" in str(path)

