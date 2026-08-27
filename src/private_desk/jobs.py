from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from private_desk import paths

PROTOCOL = "private-desk/v0"
TERMINAL = frozenset({"succeeded", "failed", "cancelled"})
IN_FLIGHT = frozenset({"running", "needs_you"})
ACTIVE = IN_FLIGHT  # v1: no queued


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_job_id() -> str:
    return f"job_{int(time.time() * 1000):x}{secrets.token_hex(4)}"


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    """Return only the assistant-visible Job fields."""
    keys = (
        "protocol",
        "job_id",
        "kind",
        "state",
        "risk",
        "inference",
        "idempotency_key",
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
        "heartbeat_at",
        "step",
        "user_action",
        "summary",
        "error",
        "artifacts",
    )
    return {k: job.get(k) for k in keys}


def job_path(job_id: str) -> Path:
    return paths.job_dir(job_id) / "job.json"


def pid_path(job_id: str) -> Path:
    return paths.job_dir(job_id) / "worker.pid"


def resume_path(job_id: str) -> Path:
    return paths.job_dir(job_id) / "resume.signal"


def cancel_path(job_id: str) -> Path:
    return paths.job_dir(job_id) / "cancel.signal"


def load_job(job_id: str) -> dict[str, Any] | None:
    p = job_path(job_id)
    if not p.is_file():
        return None
    return json.loads(p.read_text())


def write_job(job: dict[str, Any]) -> None:
    d = paths.job_dir(job["job_id"])
    d.mkdir(parents=True, exist_ok=True)
    job["updated_at"] = utcnow()
    tmp = d / "job.json.tmp"
    tmp.write_text(json.dumps(public_job(job), indent=2) + "\n")
    tmp.replace(d / "job.json")


def new_job(
    *,
    kind: str,
    risk: str,
    inference: str,
    idempotency_key: str | None,
    job_id: str | None = None,
) -> dict[str, Any]:
    now = utcnow()
    job = {
        "protocol": PROTOCOL,
        "job_id": job_id or new_job_id(),
        "kind": kind,
        "state": "running",
        "risk": risk,
        "inference": inference,
        "idempotency_key": idempotency_key,
        "created_at": now,
        "updated_at": now,
        "started_at": now,
        "finished_at": None,
        "heartbeat_at": now,
        "step": None,
        "user_action": None,
        "summary": None,
        "error": None,
        "artifacts": None,
    }
    write_job(job)
    return job


def heartbeat(job: dict[str, Any]) -> None:
    job["heartbeat_at"] = utcnow()
    write_job(job)


def list_jobs() -> list[dict[str, Any]]:
    root = paths.jobs_dir()
    if not root.is_dir():
        return []
    jobs = []
    for child in root.iterdir():
        p = child / "job.json"
        if p.is_file():
            jobs.append(json.loads(p.read_text()))
    jobs.sort(key=lambda j: j.get("created_at") or "", reverse=True)
    return jobs


def find_idempotent(key: str) -> dict[str, Any] | None:
    if not key:
        return None
    cutoff = time.time() - 24 * 3600
    for job in list_jobs():
        if job.get("idempotency_key") != key:
            continue
        created = job.get("created_at") or ""
        try:
            ts = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
        except ValueError:
            ts = 0.0
        if ts < cutoff:
            continue
        return job
    return None


def set_state(job: dict[str, Any], state: str, **fields: Any) -> dict[str, Any]:
    job["state"] = state
    for k, v in fields.items():
        job[k] = v
    if state in TERMINAL:
        job["finished_at"] = utcnow()
        job["user_action"] = None
    write_job(job)
    return job
