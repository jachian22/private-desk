from private_desk.api import setup_config
from private_desk.cli import main
from private_desk.config import browser_for_prompt, load_config
from private_desk.doctor import run_doctor


def test_setup_writes_browser(isolated):
    result = setup_config(browser="Firefox")
    assert result.ok
    assert result.payload["browser"] == "Firefox"
    cfg = load_config()
    assert cfg.browser == "Firefox"
    assert browser_for_prompt(cfg) == "Firefox"
    text = (isolated / "config" / "config.toml").read_text()
    assert 'browser = "Firefox"' in text


def test_setup_requires_a_field(isolated):
    result = setup_config()
    assert result.ok is False
    assert result.exit_code == 2
    assert result.payload["error"]["code"] == "kind_denied"


def test_setup_cli_flag(isolated, capsys):
    code = main(["setup", "--browser", "Google Chrome"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Google Chrome" in out
    assert load_config().browser == "Google Chrome"


def test_doctor_notes_setup_when_browser_unset(isolated, monkeypatch):
    monkeypatch.setattr("private_desk.doctor._which", lambda _name: None)
    payload = run_doctor(strict=False)
    assert payload["checks"]["browser"] == "unset"
    joined = "\n".join(payload["notes"])
    assert "private-desk setup --browser" in joined


def test_browser_for_prompt_fallback():
    from private_desk.config import Config

    assert browser_for_prompt(Config(browser="")) == "the default web browser"
    assert browser_for_prompt(Config(browser="  Safari ")) == "Safari"
