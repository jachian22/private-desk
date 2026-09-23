"""decide: label a gate. Never forks a worker."""

from __future__ import annotations

from typing import Any

from private_desk import jobs
from private_desk.api import Result, _err, _ok
from private_desk.config import Config, load_config
from private_desk.jev.client import (
    JevUnavailable,
    ScriptedJevClient,
    live_jev_client,
)
from private_desk.jev.mixer import Answers, Decision, Facts, mix
from private_desk.jev.questions import build_questions, build_state
from private_desk.jev.secrets import utterance_is_secret
from private_desk.kinds import load_kinds


def _desktop_busy() -> bool:
    return any(j.get("state") in jobs.ACTIVE for j in jobs.list_jobs())


def _secret_decision() -> Decision:
    return mix(
        Answers(kind="none", next="start", kick_now=0.99, secret_in_request=0.99),
        Facts(utterance="", kinds={}, cfg=Config(), secret=True),
    )


def _result(decision: Decision, *, jev: dict[str, Any] | None, extra: dict[str, Any] | None = None) -> Result:
    payload: dict[str, Any] = {
        "decision": decision.as_payload(),
        "invocation": decision.invocation,
        "jev": jev,
    }
    if decision.user_action is not None:
        payload["user_action"] = decision.user_action
    if extra:
        payload.update(extra)
    return _ok(**payload)


def decide(
    utterance: str,
    *,
    job_id: str | None = None,
    dump_state: bool = False,
    policy: str = "jev",
    client: Any | None = None,
    answers: Answers | None = None,
) -> Result:
    text = (utterance or "").strip()
    if not text:
        return _err("kind_denied", "Pass --utterance.", 2)

    cfg = load_config()
    kinds = load_kinds()
    job = None
    if job_id:
        job = jobs.load_job(job_id)
        if not job:
            return _err("not_found", f"Job '{job_id}' not found.", 3)
        job = jobs.public_job(job)

    desktop_busy = _desktop_busy()
    state = build_state(
        utterance=text,
        kinds=kinds,
        cfg=cfg,
        job=job,
        desktop_busy=desktop_busy,
    )
    questions = build_questions(kinds=kinds, include_job=job is not None)
    dump = {"state": state, "questions": questions}

    if dump_state:
        return _ok(dump=dump, decision=None, invocation=None, jev=None)

    if utterance_is_secret(text):
        return _result(_secret_decision(), jev=None)

    facts = Facts(
        utterance=text,
        kinds=kinds,
        cfg=cfg,
        job=job,
        desktop_busy=desktop_busy,
        secret=False,
    )

    resolved = answers
    jev_bag: dict[str, Any] | None = None
    if resolved is None:
        try:
            if client is None:
                if policy == "scripted":
                    client = ScriptedJevClient(kinds)
                elif policy == "jev":
                    client = live_jev_client(cfg)
                else:
                    return _err("kind_denied", f"Unknown decide policy '{policy}'.", 2)
            resolved = client.ask(state, questions)
        except JevUnavailable as exc:
            return _err("jev_unavailable", exc.message, 5)
    jev_bag = resolved.as_jev()
    decision = mix(resolved, facts)
    return _result(decision, jev=jev_bag)
