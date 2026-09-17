from types import SimpleNamespace

import pytest

from private_desk.config import Config
from private_desk.doctor import run_doctor
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


def test_default_repo_url_is_this_repo():
    assert Config().repo_url == "https://github.com/jachian22/private-desk"
