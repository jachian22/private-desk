from types import SimpleNamespace

import pytest

from private_desk.config import Config
from private_desk.doctor import run_doctor, spawn_parent_app
from private_desk.local_model import probe_local_model


@pytest.fixture(autouse=True)
def _no_local_model(monkeypatch):
    monkeypatch.setattr("private_desk.doctor.probe_local_model", lambda _url: "unreachable")


def test_doctor_missing_holo_is_not_failure(isolated, monkeypatch):
    monkeypatch.setattr("private_desk.doctor._which", lambda _name: None)
    payload = run_doctor(strict=False)
    assert payload["exit_code"] == 0
    assert payload["ok"] is True
    assert payload["checks"]["dummy_kinds"] == "ok"
    assert payload["checks"]["holo"] == "missing"
    assert payload["onboarding"]["first_job"] == "demo_dummy_files"
    assert payload["onboarding"]["next"] == "setup"
    assert "demo_dummy_files" in payload["onboarding"]["ready"]


def test_doctor_strict_fails_without_holo(isolated, monkeypatch):
    monkeypatch.setattr("private_desk.doctor._which", lambda _name: None)
    payload = run_doctor(strict=True)
    assert payload["checks"]["holo"] == "missing"
    assert payload["exit_code"] == 5
    assert payload["ok"] is False


def test_doctor_strict_fails_when_holo_doctor_nonzero(isolated, monkeypatch):
    monkeypatch.setattr("private_desk.doctor._which", lambda _name: "/usr/local/bin/holo")
    monkeypatch.setattr(
        "private_desk.doctor.subprocess.run",
        lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="", stderr=""),
    )
    payload = run_doctor(strict=True)
    assert payload["checks"]["holo"] == "ok"
    assert payload["checks"]["permissions"] == "not_ready"
    assert payload["exit_code"] == 5
    assert payload["ok"] is False


def test_doctor_strict_passes_when_holo_doctor_ok(isolated, monkeypatch):
    monkeypatch.setattr("private_desk.doctor._which", lambda _name: "/usr/local/bin/holo")
    monkeypatch.setattr(
        "private_desk.doctor.subprocess.run",
        lambda *_a, **_k: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    payload = run_doctor(strict=True)
    assert payload["ok"] is True
    assert payload["exit_code"] == 0
    assert payload["checks"]["permissions"] == "ok"


def test_doctor_notes_boot_command_when_pet_down(isolated, monkeypatch):
    monkeypatch.setattr("private_desk.doctor._which", lambda _name: None)
    payload = run_doctor(strict=False)
    assert payload["ok"] is True
    assert payload["checks"]["local_model"] == "unreachable"
    notes = payload["notes"]
    joined = "\n".join(notes)
    assert "Local model is not running." in notes
    assert "llama-server" in joined
    assert "--host 127.0.0.1" in joined
    assert "Hcompany/Holo-3.1-35B-A3B-GGUF" in joined
    assert "0.0.0.0" not in joined


def test_doctor_reachable_omits_boot_notes(isolated, monkeypatch):
    monkeypatch.setattr("private_desk.doctor.probe_local_model", lambda _url: "reachable")
    monkeypatch.setattr("private_desk.doctor._which", lambda _name: None)
    payload = run_doctor(strict=False)
    assert payload["checks"]["local_model"] == "reachable"
    assert payload["checks"]["llama_cpp"] == "reachable"
    joined = "\n".join(payload["notes"])
    assert "Local model is not running." not in joined
    assert "llama-server" not in joined


def test_probe_closed_port_is_unreachable():
    assert probe_local_model("http://127.0.0.1:1/v1") == "unreachable"


def test_spawn_parent_walks_to_cursor(monkeypatch):
    rows = {
        10: ("zsh", 11, "/bin/zsh"),
        11: ("Cursor", 1, "/Applications/Cursor.app/Contents/MacOS/Cursor"),
    }
    monkeypatch.setattr("private_desk.doctor._process_row", lambda pid: rows.get(pid))
    assert spawn_parent_app(10) == "Cursor"


def test_doctor_names_screen_recording_parent(isolated, monkeypatch):
    monkeypatch.setattr("private_desk.doctor._which", lambda _name: None)
    monkeypatch.setattr("private_desk.doctor.spawn_parent_app", lambda: "Terminal")
    payload = run_doctor(strict=False)
    assert payload["checks"]["spawn_parent"] == "Terminal"
    joined = "\n".join(payload["notes"])
    assert "hai-agent-runtime" in joined
    assert "Terminal" in joined


def test_default_repo_url_is_this_repo():
    assert Config().repo_url == "https://github.com/jachian22/private-desk"


def test_onboarding_dummy_when_holo_missing_but_browser_set(isolated, monkeypatch):
    from private_desk.config import load_config, save_config

    monkeypatch.setattr("private_desk.doctor._which", lambda _name: None)
    cfg = load_config()
    cfg.browser = "Google Chrome"
    save_config(cfg)
    payload = run_doctor(strict=False)
    assert payload["onboarding"]["next"] == "demo_dummy_files"
    assert any(item["kind"] == "demo_open_repo" for item in payload["onboarding"]["blocked"])
    assert any(item["kind"] == "demo_dino" and item["need"] == "jev" for item in payload["onboarding"]["blocked"])


def test_onboarding_blocks_dino_on_safari(isolated, monkeypatch):
    from private_desk.config import load_config, save_config

    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gw-test")
    monkeypatch.setattr("private_desk.doctor._which", lambda _name: None)
    cfg = load_config()
    cfg.browser = "Safari"
    save_config(cfg)
    payload = run_doctor(strict=False)
    blob = str(payload)
    assert "gw-test" not in blob
    assert any(item["kind"] == "demo_dino" and item["need"] == "chromium" for item in payload["onboarding"]["blocked"])


def test_onboarding_open_repo_when_holo_ready(isolated, monkeypatch):
    from private_desk.config import load_config, save_config

    monkeypatch.setattr("private_desk.doctor._which", lambda _name: "/usr/local/bin/holo")
    monkeypatch.setattr(
        "private_desk.doctor.subprocess.run",
        lambda *_a, **_k: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    cfg = load_config()
    cfg.browser = "Google Chrome"
    save_config(cfg)
    payload = run_doctor(strict=False)
    assert payload["onboarding"]["next"] == "demo_open_repo"
    assert "demo_open_repo" in payload["onboarding"]["ready"]
    assert any(item["kind"] == "demo_star_repo" and item["need"] == "allow_mutating" for item in payload["onboarding"]["blocked"])
