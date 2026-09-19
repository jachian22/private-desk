"""House rules. Jev can be wrong; physics wins. Never starts a job."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from private_desk.config import Config
from private_desk.kinds import Kind, resolve_inference
from private_desk import paths

NOUL_THRESHOLD = 0.5
NEXT_START = "start"
NEXT_GET = "get"
NEXT_DOCTOR = "doctor"
NEXT_TELL = "tell_them"


@dataclass
class Answers:
    kind: str = "none"
    next: str = NEXT_DOCTOR
    kick_now: float = 0.0
    ask_first: float = 0.0
    use_local_only: float = 0.0
    mutating_ok: float = 0.0
    secret_in_request: float = 0.0
    job_class: str | None = None
    keep_waiting: float = 0.0

    def as_jev(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": self.kind,
            "next": self.next,
            "kick_now": self.kick_now,
            "ask_first": self.ask_first,
            "use_local_only": self.use_local_only,
            "mutating_ok": self.mutating_ok,
            "secret_in_request": self.secret_in_request,
        }
        if self.job_class is not None:
            out["job_class"] = self.job_class
            out["keep_waiting"] = self.keep_waiting
        return out


@dataclass
class Facts:
    utterance: str
    kinds: dict[str, Kind]
    cfg: Config
    job: dict[str, Any] | None = None
    desktop_busy: bool = False
    secret: bool = False


@dataclass
class Decision:
    next: str
    kind: str | None
    legal: bool
    blocked_by: str | None
    ask_first: bool
    invocation: dict[str, Any] | None = None
    user_action: dict[str, Any] | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "next": self.next,
            "kind": self.kind,
            "legal": self.legal,
            "blocked_by": self.blocked_by,
            "ask_first": self.ask_first,
        }


def kind_requires_params(kind: Kind) -> bool:
    required = (kind.params or {}).get("required") or []
    return bool(required)


def is_private_kind(kind: Kind) -> bool:
    try:
        source = kind.source.resolve()
        root = paths.private_kinds_dir().resolve()
        return source.is_relative_to(root)
    except (OSError, ValueError):
        return False


def is_hosted_on_private(kind: Kind, cfg: Config) -> bool:
    if not is_private_kind(kind):
        return False
    return resolve_inference(kind, cfg) == "hosted"


def _tell(
    blocked_by: str,
    kind: str | None = None,
    *,
    ask_first: bool = False,
    user_action: dict[str, Any] | None = None,
) -> Decision:
    return Decision(
        next=NEXT_TELL,
        kind=kind,
        legal=False,
        blocked_by=blocked_by,
        ask_first=ask_first,
        invocation=None,
        user_action=user_action,
    )


def mix(answers: Answers, facts: Facts) -> Decision:
    chosen = (answers.kind or "").strip() or "none"
    kind_obj = facts.kinds.get(chosen) if chosen not in {"none", "message_only"} else None
    kind_id = kind_obj.id if kind_obj else None
    job = facts.job
    wants_start = answers.next == NEXT_START

    if facts.secret or answers.secret_in_request >= NOUL_THRESHOLD:
        return _tell("secret_in_request")

    if wants_start and facts.desktop_busy:
        if job and job.get("state") == "running":
            return _tell("keep_waiting", kind_id or job.get("kind"))
        return _tell("desktop_busy", kind_id)

    if job and job.get("state") == "needs_you":
        return _tell(
            "needs_you",
            job.get("kind"),
            user_action=job.get("user_action"),
        )

    if answers.next == NEXT_DOCTOR and not wants_start:
        return Decision(
            next=NEXT_DOCTOR,
            kind=kind_id,
            legal=True,
            blocked_by=None,
            ask_first=False,
            invocation={"argv": ["doctor"]},
        )

    if answers.next == NEXT_GET and not wants_start:
        if not job:
            return _tell("no_job", kind_id)
        return Decision(
            next=NEXT_GET,
            kind=job.get("kind"),
            legal=True,
            blocked_by=None,
            ask_first=False,
            invocation={"argv": ["get", job["job_id"]]},
        )

    if chosen == "none":
        return _tell("none")
    if chosen == "message_only":
        return _tell("message_only")
    if kind_obj is None:
        return _tell("unknown_kind")

    if kind_requires_params(kind_obj):
        return _tell("required_params", kind_obj.id)
    if is_hosted_on_private(kind_obj, facts.cfg):
        return _tell("hosted_on_private", kind_obj.id)
    if kind_obj.risk == "mutating" and not facts.cfg.allow_mutating:
        return _tell("mutating_disabled", kind_obj.id)
    if answers.ask_first >= NOUL_THRESHOLD:
        return _tell("ask_first", kind_obj.id, ask_first=True)
    if wants_start and answers.kick_now < NOUL_THRESHOLD:
        return _tell("kick_now_false", kind_obj.id)

    if answers.next == NEXT_START:
        return Decision(
            next=NEXT_START,
            kind=kind_obj.id,
            legal=True,
            blocked_by=None,
            ask_first=False,
            invocation={"argv": [NEXT_START, kind_obj.id]},
        )
    return _tell("none", kind_obj.id)
