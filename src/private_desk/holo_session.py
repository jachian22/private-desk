"""HoloDesktop via agent_client: pause on NEEDS_YOU, resume on desk resume signal."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from private_desk import jobs, paths
from private_desk.config import Config, browser_for_prompt
from private_desk.kinds import Kind, interpolate_prompt, interpolate_template
from private_desk.launch import close_job_browser, open_https
from private_desk.needs_you import (
    answer_text,
    classify_done,
    classify_failure,
    classify_needs_you,
    classify_timeout,
    event_caller_id,
    fail_message,
    flatten_text,
    is_session_end,
    is_session_paused,
    text_for_needs_you,
    user_action_for,
)
from private_desk.redact import event_to_dict, redact, redact_text
from private_desk.runners import RunnerError, artifact_dir_for, artifacts_payload, wait_for_resume


def holo_importable() -> bool:
    try:
        import holo_desktop.agent_client  # noqa: F401
    except ImportError:
        return False
    return True


POLL_WAIT_S = 10
CONTINUE_PREFIX = (
    "The human finished the laptop action. The URL was just opened again. "
    "Look at that window. Do not type passwords or codes. Do not hunt for the app.\n"
)


def _raise_if_failed(status: Any, error: Any, job_path: Path | None = None) -> None:
    err_text = flatten_text(error)
    if job_path is not None and err_text:
        (job_path / "worker-internal.log").write_text(redact_text(err_text)[:2000] + "\n")
    fail = classify_failure(err_text)
    if fail:
        raise RunnerError(fail, fail_message(fail))
    value = str(getattr(status, "value", status) or "").lower()
    if value == "timed_out" or classify_timeout(err_text):
        raise RunnerError("timeout", fail_message("timeout"))
    if value in {"failed", "interrupted"} or err_text:
        raise RunnerError("model_error", "HoloDesktop session failed.")


def _pause_conflict(exc: BaseException) -> bool:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return status == 409 or "409" in str(exc)


async def _pause_for_human(
    client: Any,
    session_id: str,
    job: dict[str, Any],
    kind: Kind,
    code: str,
    cancelled,
    *,
    browser: str = "",
    launch_url: str = "",
    isolated: bool = False,
) -> bool:
    """Pause Holo and wait for laptop resume. False if the session already ended (answer 409)."""
    jobs.set_state(
        job,
        "needs_you",
        user_action=user_action_for(code),
        step={
            "id": "waiting_for_human",
            "label": "Waiting on the laptop",
            "n": 1,
            "of": 2,
        },
    )
    alive = True
    try:
        await client.pause(session_id)
    except Exception as exc:
        # Holo `answer` (NEEDS_YOU) ends the session. Still wait for the human.
        if not _pause_conflict(exc):
            raise
        alive = False
    await asyncio.to_thread(wait_for_resume, job, kind.max_time_s)
    if await cancelled():
        if alive:
            await client.cancel(session_id)
        raise RunnerError("cancelled", "Job cancelled.")
    jobs.set_state(
        job,
        "running",
        user_action=None,
        step={"id": "holo_run", "label": "Running HoloDesktop", "n": 1, "of": 1},
    )
    if launch_url:
        await asyncio.to_thread(
            open_https, browser, launch_url, isolated=isolated, reuse=True
        )
    if alive:
        await _resume_session(client, session_id)
    return alive


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


async def _continue_session(
    client: Any,
    prompt: str,
    kind: Kind,
    job_path: Path,
) -> str:
    from holo_desktop.agent_client.requests import build_session_request

    request = build_session_request(
        task=CONTINUE_PREFIX + prompt,
        max_steps=kind.max_steps,
        max_time_s=kind.max_time_s,
    )
    session_id = await client.create_session(request)
    (job_path / "holo.session").write_text(session_id)
    return session_id


def _append_jsonl(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(obj, default=str) + "\n")


async def _run_session(
    job: dict[str, Any],
    kind: Kind,
    cfg: Config,
    params: dict[str, Any],
) -> dict[str, Any]:
    from holo_desktop.agent_client import AgentApiClient, SpawnConfig, ensure_running
    from holo_desktop.agent_client.requests import build_session_request

    artifact_dir = artifact_dir_for(kind, cfg, params)
    extra = {
        "artifact_dir": str(artifact_dir),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "repo_url": cfg.repo_url,
        "browser": browser_for_prompt(cfg),
        "browser_profile": cfg.browser_profile,
        "url_allowlist": "\n".join(kind.url_allowlist),
        "denied_actions": ", ".join(kind.denied_actions),
    }
    prompt = interpolate_prompt(kind, params, extra)
    opened_job_browser = False
    launch_url = interpolate_template(kind.launch_url, params, extra)
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

    daemon = None
    session_id: str | None = None
    client: Any = None
    confirmed = not bool(kind.confirm_token)
    try:
        if launch_url:
            open_https(extra["browser"], launch_url, isolated=kind.launch_isolated)
            opened_job_browser = True
        from holo_desktop.cli.bootstrap import load_holo_env
        from holo_desktop.settings import load_holo_settings

        load_holo_env()
        settings = load_holo_settings()
        if job.get("inference") == "hosted" and not settings.auth.api_key:
            raise RunnerError("model_error", "Hosted Holo is not signed in.")
        daemon = await ensure_running(SpawnConfig(**spawn_kw), settings=settings)
        async with AgentApiClient(daemon.base_url, daemon.token) as client:
            request = build_session_request(
                task=prompt,
                max_steps=kind.max_steps,
                max_time_s=kind.max_time_s,
            )
            session_id = await client.create_session(request)
            (job_path / "holo.session").write_text(session_id)

            async def cancelled() -> bool:
                current = jobs.load_job(job["job_id"])
                return bool(current and current.get("state") == "cancelled")

            from_index = 0

            async def after_human(code: str) -> None:
                """Wait for the laptop. Restart Holo if NEEDS_YOU ended the session."""
                nonlocal session_id, from_index
                alive = await _pause_for_human(
                    client,
                    session_id,
                    job,
                    kind,
                    code,
                    cancelled,
                    browser=extra["browser"],
                    launch_url=launch_url,
                    isolated=kind.launch_isolated,
                )
                if alive:
                    return
                session_id = await _continue_session(client, prompt, kind, job_path)
                from_index = 0

            while True:
                if await cancelled():
                    await client.cancel(session_id)
                    raise RunnerError("cancelled", "Job cancelled.")
                changes = await client.get_changes(
                    session_id,
                    from_index,
                    wait_for_seconds=POLL_WAIT_S,
                    include_events=True,
                )
                if changes is None:
                    live = await client.get_status(session_id)
                    if is_session_paused(live.status):
                        await after_human("mfa_required")
                        continue
                    if is_session_end(live.status):
                        _raise_if_failed(live.status, live.error, job_path)
                        break
                    continue
                from_index += len(changes.new_events)
                waited = False
                for event in changes.new_events:
                    if await cancelled():
                        await client.cancel(session_id)
                        raise RunnerError("cancelled", "Job cancelled.")
                    raw = event_to_dict(event)
                    _append_jsonl(raw_log, raw)
                    _append_jsonl(safe_log, redact(raw))
                    event_type = str(raw.get("type") or getattr(event, "type", "") or "")
                    status = str(raw.get("status") or getattr(event, "status", "") or "")
                    text = flatten_text(raw)
                    code = classify_needs_you(
                        event_type,
                        text_for_needs_you(raw),
                        status=status,
                        caller_id=event_caller_id(raw),
                    )
                    if code:
                        await after_human(code)
                        waited = True
                        break
                    fail = classify_failure(text)
                    if fail:
                        await client.cancel(session_id)
                        raise RunnerError(fail, fail_message(fail))
                    if classify_done(
                        answer_text(raw),
                        kind.confirm_token,
                        event_caller_id(raw),
                    ):
                        confirmed = True
                        try:
                            await client.cancel(session_id)
                        except Exception:
                            pass
                        break
                    jobs.heartbeat(job)
                if confirmed:
                    break
                if waited:
                    continue
                if is_session_paused(changes.status):
                    await after_human("mfa_required")
                    continue
                if is_session_end(changes.status):
                    _raise_if_failed(changes.status, changes.error, job_path)
                    break
    except RunnerError:
        raise
    except ImportError as exc:
        raise RunnerError("runtime_unavailable", "holo_desktop is not installed.") from exc
    except Exception as exc:
        name = type(exc).__name__
        try:
            (job_path / "worker-internal.log").write_text(f"{name}: {redact_text(str(exc))[:2000]}\n")
        except OSError:
            pass
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
        if daemon is not None:
            await daemon.aclose()
        if opened_job_browser:
            close_job_browser(isolated=kind.launch_isolated)

    files = sorted(p.name for p in artifact_dir.iterdir() if p.is_file()) if artifact_dir.exists() else []
    if kind.requires_artifacts and not files:
        raise RunnerError("internal", "Runner finished but the artifact directory is empty.")
    if kind.confirm_token and not confirmed:
        raise RunnerError(
            "model_error",
            f"Holo finished without DONE: {kind.confirm_token}.",
        )
    return artifacts_payload(artifact_dir, files)


def run_holo_session(job: dict[str, Any], kind: Kind, cfg: Config, params: dict[str, Any]) -> dict[str, Any]:
    if not holo_importable():
        raise RunnerError("runtime_unavailable", "holo_desktop is not installed.")
    return asyncio.run(_run_session(job, kind, cfg, params))
