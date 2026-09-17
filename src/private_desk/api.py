from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Any

from private_desk import jobs, paths
from private_desk.config import load_config, save_config
from private_desk.holo_session import holo_importable
from private_desk.kinds import KindError, get_kind, load_kinds, resolve_inference, validate_params
from private_desk.local_model import probe_local_model, unavailable_message
from private_desk.lock import DesktopLock
from private_desk.proc import kill_tree
from private_desk.pythonpath import apply_worker_pythonpath

PROTOCOL = jobs.PROTOCOL


@dataclass
class Result:
    ok: bool
    payload: dict[str, Any]
    exit_code: int


def _ok(**fields: Any) -> Result:
    return Result(True, {"protocol": PROTOCOL, "ok": True, **fields}, 0)


def _err(code: str, message: str, exit_code: int) -> Result:
    return Result(
        False,
        {"protocol": PROTOCOL, "ok": False, "error": {"code": code, "message": message}},
        exit_code,
    )


def list_kinds() -> Result:
    cfg = load_config()
    kinds = []
    for kind in load_kinds().values():
        kinds.append(kind.public_view(resolve_inference(kind, cfg)))
    kinds.sort(key=lambda k: k["id"])
    return _ok(kinds=kinds)


def setup_config(
    *,
    browser: str | None = None,
    browser_profile: str | None = None,
    repo_url: str | None = None,
) -> Result:
    """Write browser / profile / repo_url. Agents pass flags; humans can use the TTY wizard."""
    if not any(v is not None and str(v).strip() for v in (browser, browser_profile, repo_url)):
        return _err(
            "kind_denied",
            'Pass --browser (menu-bar app name), e.g. --browser "Google Chrome".',
            2,
        )
    cfg = load_config()
    if browser is not None:
        cfg.browser = browser.strip()
    if browser_profile is not None:
        cfg.browser_profile = browser_profile.strip() or cfg.browser_profile
    if repo_url is not None:
        cfg.repo_url = repo_url.strip() or cfg.repo_url
    path = save_config(cfg)
    return _ok(
        config_path=str(path),
        browser=cfg.browser,
        browser_profile=cfg.browser_profile,
        repo_url=cfg.repo_url,
    )


def holo_ready(holo_bin: str) -> bool:
    if which(holo_bin) or Path(holo_bin).is_file():
        return True
    return holo_importable()


def start_job(kind_id: str, params: dict[str, Any] | None, idempotency_key: str | None) -> Result:
    params = params or {}
    cfg = load_config()
    try:
        kind = get_kind(kind_id)
        validate_params(kind, params)
    except KindError as exc:
        return _err("kind_denied", exc.message, 2)

    if kind.risk == "mutating" and not cfg.allow_mutating:
        return _err("kind_denied", "Mutating jobs are disabled.", 2)

    if idempotency_key:
        existing = jobs.find_idempotent(idempotency_key)
        if existing:
            return _ok(job=jobs.public_job(existing))

    if kind.runner == "holo" and not holo_ready(cfg.holo_bin):
        return _err("runtime_unavailable", "holo / holo_desktop is not installed.", 5)

    inference = resolve_inference(kind, cfg)
    if kind.runner == "holo" and inference == "local":
        if probe_local_model(cfg.holo_base_url) != "reachable":
            return _err("runtime_unavailable", unavailable_message(cfg.holo_base_url), 5)

    job_id = jobs.new_job_id()
    held = DesktopLock.try_acquire(job_id)
    if held is None:
        return _err("desktop_busy", "Another private-desk job owns the desktop.", 4)

    job = None
    try:
        job = jobs.new_job(
            kind=kind.id,
            risk=kind.risk,
            inference=inference,
            idempotency_key=idempotency_key,
            job_id=job_id,
        )
        params_path = paths.job_dir(job["job_id"]) / "params.json"
        params_path.write_text(json.dumps(params) + "\n")

        env = os.environ.copy()
        env["PRIVATE_DESK_LOCK_FD"] = str(held.fd)
        if "PRIVATE_DESK_PUBLIC_KINDS" not in env:
            env["PRIVATE_DESK_PUBLIC_KINDS"] = str(paths.public_kinds_dir())
        apply_worker_pythonpath(env)
        cmd = [sys.executable, "-m", "private_desk.worker", job["job_id"]]
        log = (paths.job_dir(job["job_id"]) / "worker.log").open("ab")
        popen_kw: dict[str, Any] = {
            "args": cmd,
            "env": env,
            "stdin": subprocess.DEVNULL,
            "stdout": log,
            "stderr": subprocess.STDOUT,
            "close_fds": True,
            "pass_fds": (held.fd,),
            "start_new_session": True,
        }
        proc = subprocess.Popen(**popen_kw)
        log.close()
        jobs.pid_path(job["job_id"]).write_text(str(proc.pid))
        held.write_meta(job["job_id"], proc.pid)
        held.detach_parent()
        return _ok(job=jobs.public_job(job))
    except Exception:
        if job is not None:
            jobs.set_state(
                job,
                "failed",
                error={"code": "internal", "message": "Failed to start worker."},
            )
        held.close()
        return _err("internal", "Failed to start worker.", 1)


def get_job(job_id: str) -> Result:
    job = jobs.load_job(job_id)
    if not job:
        return _err("not_found", f"Job '{job_id}' not found.", 3)
    return _ok(job=jobs.public_job(job))


def wait_job(job_id: str, *, poll_s: float = 1.0) -> Result:
    """Block until the job leaves running, then return the same payload as get."""
    while True:
        result = get_job(job_id)
        if not result.ok:
            return result
        if result.payload["job"].get("state") != "running":
            return result
        time.sleep(poll_s)


def status_jobs() -> Result:
    active = [jobs.public_job(j) for j in jobs.list_jobs() if j.get("state") in jobs.ACTIVE]
    return _ok(jobs=active)


def cancel_job(job_id: str) -> Result:
    job = jobs.load_job(job_id)
    if not job:
        return _err("not_found", f"Job '{job_id}' not found.", 3)
    if job.get("state") in jobs.TERMINAL:
        return _ok(job=jobs.public_job(job))
    jobs.cancel_path(job_id).write_text("cancel\n")
    jobs.set_state(job, "cancelled")
    pid_file = jobs.pid_path(job_id)
    if pid_file.is_file():
        try:
            pid = int(pid_file.read_text().strip())
        except ValueError:
            pid = 0
        if pid:
            kill_tree(pid)
    job = jobs.load_job(job_id) or job
    return _ok(job=jobs.public_job(job))


def resume_job(job_id: str) -> Result:
    job = jobs.load_job(job_id)
    if not job:
        return _err("not_found", f"Job '{job_id}' not found.", 3)
    if job.get("state") != "needs_you":
        return _ok(job=jobs.public_job(job))
    jobs.resume_path(job_id).write_text("resume\n")
    return _ok(job=jobs.public_job(job))


def job_logs(job_id: str) -> Result:
    job = jobs.load_job(job_id)
    if not job:
        return _err("not_found", f"Job '{job_id}' not found.", 3)
    log = paths.job_dir(job_id) / "worker.log"
    # Never put log text in JSON. Path only; tty dump is CLI's job when stdout is a tty.
    return _ok(job=jobs.public_job(job), log_path=str(log))
