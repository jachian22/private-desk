"""Detached job worker. Not a daemon. Parent of Holo for one job."""

from __future__ import annotations

import json
import os
import signal
import sys
import traceback

from private_desk import jobs, paths
from private_desk.config import load_config
from private_desk.kinds import get_kind
from private_desk.lock import DesktopLock
from private_desk.redact import redact_text
from private_desk.runners import RunnerError, run_kind

_stop = False


def _handle_term(_signum, _frame) -> None:
    global _stop
    _stop = True


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python -m private_desk.worker <job_id>", file=sys.stderr)
        return 1
    job_id = args[0]
    signal.signal(signal.SIGTERM, _handle_term)
    signal.signal(signal.SIGINT, _handle_term)

    job = jobs.load_job(job_id)
    if not job:
        return 1

    fd_raw = os.environ.get("PRIVATE_DESK_LOCK_FD")
    desk_lock = DesktopLock.inherit(int(fd_raw)) if fd_raw else None
    paths.job_dir(job_id).mkdir(parents=True, exist_ok=True)
    jobs.pid_path(job_id).write_text(str(os.getpid()))
    if desk_lock is not None:
        desk_lock.write_meta(job_id, os.getpid())

    params_path = paths.job_dir(job_id) / "params.json"
    params = json.loads(params_path.read_text()) if params_path.is_file() else {}

    cfg = load_config()
    try:
        if _stop:
            jobs.set_state(job, "cancelled")
            return 0
        kind = get_kind(job["kind"])
        artifacts = run_kind(job, kind, cfg, params)
        job = jobs.load_job(job_id) or job
        if job.get("state") == "cancelled" or _stop:
            if job.get("state") != "cancelled":
                jobs.set_state(job, "cancelled")
            return 0
        jobs.set_state(
            job,
            "succeeded",
            artifacts=artifacts,
            summary=None,
            step=None,
        )
        return 0
    except RunnerError as exc:
        job = jobs.load_job(job_id) or job
        if exc.code == "cancelled" or job.get("state") == "cancelled" or _stop:
            if job.get("state") != "cancelled":
                jobs.set_state(job, "cancelled")
            return 0
        jobs.set_state(
            job,
            "failed",
            error={"code": exc.code, "message": redact_text(exc.message)},
            step=None,
        )
        return 1
    except Exception:
        job = jobs.load_job(job_id) or job
        paths.job_dir(job_id).joinpath("worker-internal.log").write_text(
            traceback.format_exc()
        )
        jobs.set_state(
            job,
            "failed",
            error={"code": "internal", "message": "Worker hit an internal error."},
            step=None,
        )
        return 1
    finally:
        if desk_lock is not None:
            desk_lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
