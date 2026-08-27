"""HoloDesktop via agent_client: pause on NEEDS_YOU, resume on desk resume signal."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from private_desk import jobs, paths
from private_desk.config import Config
from private_desk.kinds import Kind, interpolate_prompt
from private_desk.needs_you import classify_needs_you, flatten_text, instruction_for
from private_desk.redact import event_to_dict, redact
from private_desk.runners import RunnerError, artifact_dir_for, artifacts_payload, wait_for_resume


def holo_importable() -> bool:
    try:
        import holo_desktop.agent_client  # noqa: F401
    except ImportError:
        return False
    return True


async def _resume_session(client: Any, session_id: str) -> None:
    resume = getattr(client, "resume", None)
    if resume is not None:
        await resume(session_id)
        return
    http = getattr(client, "_http", None)
    if http is not None:
        resp = await http.post(f"/sessions/{session_id}/resume")
        if resp.status_code in (200, 204):
            return
        if resp.status_code not in (404, 405):
            resp.raise_for_status()
    await client.send_message(
        session_id,
        "The human finished the laptop action. Continue. Do not type passwords or codes.",
    )


def _append_jsonl(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(obj) + "\n")


async def _run_session(
    job: dict[str, Any],
    kind: Kind,
    cfg: Config,
    params: dict[str, Any],
) -> dict[str, Any]:
    from holo_desktop.agent_client import AgentApiClient, SpawnConfig, ensure_running
    from holo_desktop.agent_client.requests import build_session_request

    artifact_dir = artifact_dir_for(kind, cfg)
    extra = {
        "artifact_dir": str(artifact_dir),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "repo_url": cfg.repo_url,
        "browser_profile": cfg.browser_profile,
    }
    prompt = interpolate_prompt(kind, params, extra)
    job_path = paths.job_dir(job["job_id"])
    raw_log = job_path / "holo-events.raw.jsonl"
    safe_log = job_path / "holo-events.redacted.jsonl"
    runs_dir = job_path / "holo-runs"

    spawn_kw: dict[str, Any] = {"port": 18795, "runs_dir": runs_dir}
    if job.get("inference") == "local":
        spawn_kw["base_url"] = cfg.holo_base_url
        spawn_kw["model"] = cfg.holo_model

    job["step"] = {"id": "holo_run", "label": "Running HoloDesktop", "n": 1, "of": 1}
    jobs.write_job(job)

    daemon = await ensure_running(SpawnConfig(**spawn_kw))
    session_id: str | None = None
    client: Any = None
    try:
        async with AgentApiClient(daemon.base_url, daemon.token) as client:
            request = build_session_request(
                task=prompt,
                max_steps=kind.max_steps,
                max_time_s=kind.max_time_s,
            )
            session_id = await client.create_session(request)
            (job_path / "holo.session").write_text(session_id)
            stream = client.stream(session_id)

            async def cancelled() -> bool:
                current = jobs.load_job(job["job_id"])
                return bool(current and current.get("state") == "cancelled")

            async for event in stream.events():
                if await cancelled():
                    await client.cancel(session_id)
                    raise RunnerError("cancelled", "Job cancelled.")
                raw = event_to_dict(event)
                _append_jsonl(raw_log, raw)
                _append_jsonl(safe_log, redact(raw))
                event_type = str(raw.get("type") or getattr(event, "type", "") or "")
                text = flatten_text(raw)
                code = classify_needs_you(event_type, text)
                if code:
                    await client.pause(session_id)
                    jobs.set_state(
                        job,
                        "needs_you",
                        user_action={
                            "code": code,
                            "instruction": instruction_for(code),
                        },
                        step={
                            "id": "waiting_for_human",
                            "label": "Waiting on the laptop",
                            "n": 1,
                            "of": 2,
                        },
                    )
                    await asyncio.to_thread(wait_for_resume, job, kind.max_time_s)
                    if await cancelled():
                        await client.cancel(session_id)
                        raise RunnerError("cancelled", "Job cancelled.")
                    jobs.set_state(job, "running", user_action=None, step=job.get("step"))
                    await _resume_session(client, session_id)
                jobs.heartbeat(job)

            if stream.error:
                raise RunnerError("model_error", "HoloDesktop session failed.")
    except RunnerError:
        raise
    except ImportError as exc:
        raise RunnerError("runtime_unavailable", "holo_desktop is not installed.") from exc
    except Exception as exc:
        name = type(exc).__name__
        if "Connect" in name or "FileNotFound" in name:
            raise RunnerError("runtime_unavailable", "hai-agent-runtime is missing or unhealthy.") from exc
        raise RunnerError("model_error", "HoloDesktop session failed.") from exc
    finally:
        if session_id and client is not None:
            current = jobs.load_job(job["job_id"])
            if current and current.get("state") == "cancelled":
                try:
                    await client.cancel(session_id)
                except Exception:
                    pass
        await daemon.aclose()

    files = sorted(p.name for p in artifact_dir.iterdir() if p.is_file()) if artifact_dir.exists() else []
    if kind.requires_artifacts and not files:
        raise RunnerError("internal", "Runner finished but the artifact directory is empty.")
    return artifacts_payload(artifact_dir, files)


def run_holo_session(job: dict[str, Any], kind: Kind, cfg: Config, params: dict[str, Any]) -> dict[str, Any]:
    if not holo_importable():
        raise RunnerError("runtime_unavailable", "holo_desktop is not installed.")
    return asyncio.run(_run_session(job, kind, cfg, params))
