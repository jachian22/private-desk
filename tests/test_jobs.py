from __future__ import annotations

import re
import time

from private_desk import jobs
from private_desk.api import cancel_job, get_job, resume_job, start_job, status_jobs, wait_job


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


def test_wait_job_returns_when_not_running(isolated):
    started = start_job("demo_dummy_files", {}, "wait-test-1")
    job_id = started.payload["job"]["job_id"]
    waited = wait_job(job_id, poll_s=0.05)
    assert waited.ok
    assert waited.payload["job"]["state"] == "succeeded"
    assert waited.payload["job"]["job_id"] == job_id


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


def test_dummy_kind_artifact_dir_includes_product(isolated):
    kinds_dir = isolated / "config" / "kinds"
    kinds_dir.mkdir(parents=True, exist_ok=True)
    (kinds_dir / "sync_example_statements.yaml").write_text(
        """
id: sync_example_statements
title: Example statement download
risk: read_only
inference: local
may_need_you: false
runner: dummy
requires_artifacts: true
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
prompt: unused
"""
    )
    result = start_job(
        "sync_example_statements",
        {"product": "checking", "period": "last_statement"},
        "example-checking-1",
    )
    assert result.ok
    job = _wait(result.payload["job"]["job_id"], "succeeded")
    artifact_dir = job["artifacts"]["artifact_dir"]
    assert artifact_dir.endswith("sync_example_statements-checking")
    assert job["summary"] is None
    files = job["artifacts"]["files"]
    assert all("/" not in name for name in files)
    assert any(name.endswith(".pdf") for name in files)


def test_local_holo_kind_refuses_when_pet_down(isolated, monkeypatch):
    kinds_dir = isolated / "config" / "kinds"
    kinds_dir.mkdir(parents=True, exist_ok=True)
    (kinds_dir / "session_local.yaml").write_text(
        """
id: session_local
title: Local holo kind
risk: read_only
inference: local
may_need_you: true
runner: holo
params:
  type: object
  additionalProperties: false
  properties: {}
prompt: unused
"""
    )
    monkeypatch.setattr("private_desk.api.holo_ready", lambda _bin: True)
    monkeypatch.setattr("private_desk.api.probe_local_model", lambda _url: "unreachable")
    result = start_job("session_local", {}, None)
    assert result.ok is False
    assert result.exit_code == 5
    assert result.payload["error"]["code"] == "runtime_unavailable"
    assert "llama-server" in result.payload["error"]["message"]
    assert "Start llama-server" in result.payload["error"]["message"]
    assert jobs.list_jobs() == []


def test_hosted_kind_does_not_require_local_model(isolated, monkeypatch):
    monkeypatch.setattr("private_desk.api.holo_ready", lambda _bin: True)
    monkeypatch.setattr("private_desk.api.probe_local_model", lambda _url: "unreachable")
    monkeypatch.setattr("private_desk.api.DesktopLock.try_acquire", lambda _job_id: None)
    result = start_job("demo_open_repo", {}, None)
    assert result.ok is False
    assert result.payload["error"]["code"] == "desktop_busy"
