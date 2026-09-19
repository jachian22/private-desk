"""State + question bag Jev may see. Never includes prompts, logs, or keys."""

from __future__ import annotations

from typing import Any

from private_desk.config import Config
from private_desk.kinds import Kind, resolve_inference

NEXT_CRITERIA = {
    "start": "Kick one allowlisted kind. The caller will run start; you do not.",
    "get": "Read an existing job. There is a job_id or they asked how it went.",
    "doctor": "Runtime / setup check. No desktop takeover.",
}

NONE_KIND = "none"
MESSAGE_ONLY = "message_only"

KIND_SENTINELS = {
    NONE_KIND: "No catalog card fits. Do not start.",
    MESSAGE_ONLY: "They want a spoken answer, not a laptop job.",
}

JOB_CLASS_CRITERIA = {
    "succeeded": "Job finished successfully.",
    "needs_you": "Blocked on a human at the laptop.",
    "failed": "Terminal failure.",
    "running": "Worker still has the desktop.",
}


def kind_card(kind: Kind, cfg: Config) -> dict[str, Any]:
    return kind.public_view(resolve_inference(kind, cfg))


def kind_criteria_line(kind: Kind) -> str:
    title = (kind.title or kind.id).strip()
    desc = (kind.description or "").strip()
    if desc:
        return f"{title} — {desc}"
    return title


def build_state(
    *,
    utterance: str,
    kinds: dict[str, Kind],
    cfg: Config,
    job: dict[str, Any] | None,
    desktop_busy: bool,
) -> dict[str, Any]:
    cards = [kind_card(kind, cfg) for kind in sorted(kinds.values(), key=lambda k: k.id)]
    return {
        "utterance": utterance,
        "kinds": cards,
        "job": job,
        "flags": {
            "allow_mutating": bool(cfg.allow_mutating),
            "desktop_busy": bool(desktop_busy),
            "browser_set": bool((cfg.browser or "").strip()),
        },
    }


def build_questions(*, kinds: dict[str, Kind], include_job: bool) -> dict[str, Any]:
    criteria = {kind.id: kind_criteria_line(kind) for kind in kinds.values()}
    criteria.update(KIND_SENTINELS)
    questions: dict[str, Any] = {
        "kind": {
            "type": "choice",
            "instructions": (
                "Which catalog kind fits the utterance? Pick none if nothing fits. "
                "Pick message_only if they only want talk."
            ),
            "criteria": criteria,
        },
        "next": {
            "type": "choice",
            "instructions": "Which CLI verb should the caller run after this gate?",
            "criteria": dict(NEXT_CRITERIA),
        },
        "kick_now": {
            "type": "noul",
            "instructions": (
                "The utterance is a request to run the chosen kind now. "
                "True for catalog asks such as opening the repo or writing dummy files. "
                "False for greetings, status questions, or setup talk. "
                "Do not judge locks, secrets, or mutating policy — code does that."
            ),
        },
        "ask_first": {
            "type": "noul",
            "instructions": (
                "Ask whether they are at the laptop first. "
                "True when the kind may need login or 2FA (may_need_you)."
            ),
        },
        "use_local_only": {
            "type": "noul",
            "instructions": "This kind must not use hosted Holo (account / private).",
        },
        "mutating_ok": {
            "type": "noul",
            "instructions": "They asked for a mutating kind (star, post, delete).",
        },
        "secret_in_request": {
            "type": "noul",
            "instructions": "The utterance offers a password, OTP, cookie, or similar secret.",
        },
    }
    if include_job:
        questions["job_class"] = {
            "type": "choice",
            "instructions": "What is the job's situation?",
            "criteria": dict(JOB_CLASS_CRITERIA),
        }
        questions["keep_waiting"] = {
            "type": "noul",
            "instructions": "The job is still running. Do not start a second job.",
        }
    return questions
