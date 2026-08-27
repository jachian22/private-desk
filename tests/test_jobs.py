from __future__ import annotations

import re
import time

from private_desk.api import cancel_job, get_job, resume_job, start_job, status_jobs


def _wait(job_id: str, state: str, timeout: float = 8.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        result = get_job(job_id)
        assert result.ok
        last = result.payload["job"]
        if last["state"] == state:
            return last
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} never reached {state}: {last}")


def test_dummy_running_to_succeeded(isolated):
    result = start_job("demo_dummy_files", {}, "dummy-test-1")
    assert result.ok
    job_id = result.payload["job"]["job_id"]
    job = _wait(job_id, "succeeded")
    assert job["kind"] == "demo_dummy_files"
    assert job["summary"] is None
    files = job["artifacts"]["files"]
    pdfs = [name for name in files if name.endswith(".pdf")]
    assert len(pdfs) == 3
    assert all(re.fullmatch(r"\d{4}-\d{2}\.pdf", name) for name in pdfs)
    assert "manifest.json" in files


def test_idempotency_returns_same_job_id(isolated):
    a = start_job("demo_dummy_files", {}, "same-key")
    assert a.ok
    job_id = a.payload["job"]["job_id"]
    _wait(job_id, "succeeded")
    b = start_job("demo_dummy_files", {}, "same-key")
    assert b.ok
    assert b.payload["job"]["job_id"] == job_id


def test_desktop_busy_then_cancel(isolated, monkeypatch):
    monkeypatch.setenv("PRIVATE_DESK_FAKE_RUNNER", "hang")
    first = start_job("demo_dummy_files", {}, "hang-1")
    assert first.ok
    job_id = first.payload["job"]["job_id"]
    _wait(job_id, "running")
    second = start_job("demo_dummy_files", {}, "hang-2")
    assert second.ok is False
    assert second.exit_code == 4
    assert second.payload["error"]["code"] == "desktop_busy"
    cancelled = cancel_job(job_id)
    assert cancelled.ok
    job = _wait(job_id, "cancelled")
    assert job["state"] == "cancelled"
    monkeypatch.delenv("PRIVATE_DESK_FAKE_RUNNER")
    third = start_job("demo_dummy_files", {}, "after-cancel")
    assert third.ok
    _wait(third.payload["job"]["job_id"], "succeeded")


def test_needs_you_then_resume(isolated, monkeypatch):
    monkeypatch.setenv("PRIVATE_DESK_FAKE_RUNNER", "needs_you")
    started = start_job("demo_dummy_files", {}, "login-1")
    assert started.ok
    job_id = started.payload["job"]["job_id"]
    job = _wait(job_id, "needs_you")
    assert job["user_action"]["code"] == "needs_login"
    assert "Do not send" in job["user_action"]["instruction"]
    active = status_jobs().payload["jobs"]
    assert any(j["job_id"] == job_id for j in active)
    resumed = resume_job(job_id)
    assert resumed.ok
    done = _wait(job_id, "succeeded", timeout=8.0)
    assert done["artifacts"]["artifact_count"] >= 3


def test_mutating_star_denied_by_default(isolated):
    result = start_job("demo_star_repo", {}, None)
    assert result.ok is False
    assert result.payload["error"]["code"] == "kind_denied"


def test_holo_kind_without_runtime_is_unavailable(isolated, monkeypatch):
    monkeypatch.setattr("private_desk.api.holo_ready", lambda _bin: False)
    result = start_job("demo_open_repo", {}, None)
    assert result.ok is False
    assert result.exit_code == 5
    assert result.payload["error"]["code"] == "runtime_unavailable"
