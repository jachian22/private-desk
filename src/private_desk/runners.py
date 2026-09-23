from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from private_desk import jobs, paths
from private_desk.config import Config, artifact_root_path
from private_desk.kinds import Kind
from private_desk.needs_you import user_action_for


class RunnerError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def artifact_dir_for(kind: Kind, cfg: Config, params: dict[str, Any] | None = None) -> Path:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    root = artifact_root_path(cfg)
    mapping = {key: str(value) for key, value in (params or {}).items()}
    mapping.update(
        artifact_root=str(root),
        date=date,
        kind=kind.id,
    )
    try:
        raw = kind.dir_template.format(**mapping)
    except KeyError as exc:
        raise RunnerError("kind_denied", f"dir_template missing key {exc}.") from exc
    path = Path(raw).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def month_pdf_names(n: int = 3) -> list[str]:
    d = datetime.now(timezone.utc).date().replace(day=1)
    names: list[str] = []
    for _ in range(n):
        names.append(d.strftime("%Y-%m.pdf"))
        d = (d - timedelta(days=1)).replace(day=1)
    names.reverse()
    return names


def write_dummy_pdfs(artifact_dir: Path) -> list[str]:
    names = month_pdf_names()
    for name in names:
        (artifact_dir / name).write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\ntrailer\n%%EOF\n")
    manifest = {"files": names, "note": "local-only dummy manifest"}
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return [*names, "manifest.json"]


def artifacts_payload(artifact_dir: Path, files: list[str]) -> dict[str, Any]:
    return {
        "artifact_count": len(files),
        "artifact_dir": str(artifact_dir),
        "files": files,
    }


def wait_for_resume(job: dict[str, Any], timeout_s: int) -> None:
    deadline = time.time() + timeout_s
    signal = jobs.resume_path(job["job_id"])
    cancel = jobs.cancel_path(job["job_id"])
    while time.time() < deadline:
        if signal.is_file():
            try:
                signal.unlink()
            except FileNotFoundError:
                pass
            return
        if cancel.is_file():
            raise RunnerError("cancelled", "Job cancelled.")
        current = jobs.load_job(job["job_id"])
        if current and current.get("state") == "cancelled":
            raise RunnerError("cancelled", "Job cancelled.")
        jobs.heartbeat(job)
        time.sleep(0.2)
    raise RunnerError("timeout", "Timed out waiting for the human to resume.")


def run_dummy(
    job: dict[str, Any],
    kind: Kind,
    cfg: Config,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fake = os.environ.get("PRIVATE_DESK_FAKE_RUNNER")
    if fake == "needs_you":
        jobs.set_state(
            job,
            "needs_you",
            user_action=user_action_for("needs_login"),
            step={"id": "waiting_for_login", "label": "Waiting for login", "n": 1, "of": 2},
        )
        wait_for_resume(job, kind.max_time_s)
        jobs.set_state(job, "running", user_action=None)
    elif fake == "hang":
        hang_until_cancel(job, kind.max_time_s)

    job["step"] = {"id": "writing_files", "label": "Writing dummy PDFs", "n": 1, "of": 1}
    jobs.write_job(job)
    artifact_dir = artifact_dir_for(kind, cfg, params)
    files = write_dummy_pdfs(artifact_dir)
    return artifacts_payload(artifact_dir, files)


def hang_until_cancel(job: dict[str, Any], timeout_s: int) -> None:
    deadline = time.time() + timeout_s
    cancel = jobs.cancel_path(job["job_id"])
    while time.time() < deadline:
        if cancel.is_file():
            raise RunnerError("cancelled", "Job cancelled.")
        current = jobs.load_job(job["job_id"])
        if current and current.get("state") == "cancelled":
            raise RunnerError("cancelled", "Job cancelled.")
        jobs.heartbeat(job)
        time.sleep(0.2)
    raise RunnerError("timeout", "Hit max_time_s.")


def run_holo(job: dict[str, Any], kind: Kind, cfg: Config, params: dict[str, Any]) -> dict[str, Any]:
    from private_desk.holo_session import run_holo_session

    return run_holo_session(job, kind, cfg, params)


def run_kind(job: dict[str, Any], kind: Kind, cfg: Config, params: dict[str, Any]) -> dict[str, Any]:
    if kind.runner == "dummy":
        return run_dummy(job, kind, cfg, params)
    if kind.runner == "dino":
        from private_desk.dino_session import run_dino

        return run_dino(job, kind, cfg, params)
    return run_holo(job, kind, cfg, params)
