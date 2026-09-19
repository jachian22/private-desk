"""TypeSafe adapter, scripted policy, injectable fake. Optional SDK."""

from __future__ import annotations

import os
from typing import Any, Protocol

from private_desk.jev.mixer import Answers
from private_desk.jev.questions import NONE_KIND
from private_desk.kinds import Kind


class JevUnavailable(Exception):
    def __init__(self, message: str = "TypeSafe / Jev is not available.") -> None:
        super().__init__(message)
        self.message = message


class JevClient(Protocol):
    def ask(self, state: dict[str, Any], questions: dict[str, Any]) -> Answers: ...


def _noul(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def answers_from_mapping(raw: dict[str, Any]) -> Answers:
    return Answers(
        kind=str(raw.get("kind") or NONE_KIND),
        next=str(raw.get("next") or "doctor"),
        kick_now=_noul(raw.get("kick_now")),
        ask_first=_noul(raw.get("ask_first")),
        use_local_only=_noul(raw.get("use_local_only")),
        mutating_ok=_noul(raw.get("mutating_ok")),
        secret_in_request=_noul(raw.get("secret_in_request")),
        job_class=raw.get("job_class"),
        keep_waiting=_noul(raw.get("keep_waiting")),
    )


class FakeJevClient:
    def __init__(self, answers: Answers) -> None:
        self.answers = answers
        self.calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def ask(self, state: dict[str, Any], questions: dict[str, Any]) -> Answers:
        self.calls.append((state, questions))
        return self.answers


# Longer phrases first.
_SCRIPTED: tuple[tuple[tuple[str, ...], str], ...] = (
    (("dummy files", "write dummy", "dummy"), "demo_dummy_files"),
    (("open the repo", "open repo", "open the github"), "demo_open_repo"),
    (("star the repo", "star repo"), "demo_star_repo"),
    (
        ("post to x", "post on x", "tweet", "post on twitter", "get the word out"),
        "demo_post_x",
    ),
    (("chrome dino", "dino game", "dinosaur", "chrome://dino"), "demo_dino"),
)


def scripted_kind_id(utterance: str, kinds: dict[str, Kind]) -> str | None:
    blob = (utterance or "").lower()
    for phrases, kind_id in _SCRIPTED:
        if kind_id not in kinds:
            continue
        if any(p in blob for p in phrases):
            return kind_id
    for kind in kinds.values():
        needle = kind.id.replace("_", " ").lower()
        if needle and needle in blob:
            return kind.id
        title = (kind.title or "").lower()
        if title and title in blob:
            return kind.id
    return None


def scripted_answers(
    utterance: str,
    kinds: dict[str, Kind],
    *,
    job: dict[str, Any] | None = None,
) -> Answers:
    blob = (utterance or "").lower()
    if any(w in blob for w in ("doctor", "what's wrong", "whats wrong", "not working")):
        return Answers(kind=NONE_KIND, next="doctor", kick_now=0.1, job_class=job.get("state") if job else None)

    kind_id = scripted_kind_id(utterance, kinds)
    if not kind_id:
        return Answers(
            kind=NONE_KIND,
            next="start",
            kick_now=0.1,
            job_class=job.get("state") if job else None,
        )

    kind = kinds[kind_id]
    ask = 0.9 if kind.may_need_you else 0.1
    mutating = 0.9 if kind.risk == "mutating" else 0.1
    return Answers(
        kind=kind_id,
        next="start",
        kick_now=0.9,
        ask_first=ask,
        use_local_only=0.9 if kind.inference == "local" else 0.1,
        mutating_ok=mutating,
        secret_in_request=0.1,
        job_class=job.get("state") if job else None,
        keep_waiting=0.9 if job and job.get("state") == "running" else 0.1,
    )


class ScriptedJevClient:
    def __init__(self, kinds: dict[str, Kind]) -> None:
        self.kinds = kinds

    def ask(self, state: dict[str, Any], questions: dict[str, Any]) -> Answers:
        job = state.get("job") if isinstance(state.get("job"), dict) else None
        return scripted_answers(str(state.get("utterance") or ""), self.kinds, job=job)


def _choice_of(response: Any, key: str) -> str | None:
    choices = getattr(response, "choices", None)
    if choices and key in choices:
        return getattr(choices[key], "choice", None)
    answers = getattr(response, "answers", None)
    if answers and key in answers:
        return getattr(answers[key], "choice", None)
    return None


def _noul_of(response: Any, key: str) -> float:
    nouls = getattr(response, "nouls", None)
    if nouls and key in nouls:
        return _noul(getattr(nouls[key], "noul", 0.0))
    answers = getattr(response, "answers", None)
    if answers and key in answers:
        return _noul(getattr(answers[key], "noul", 0.0))
    return 0.0


class TypeSafeJevClient:
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise JevUnavailable("TypeSafe API key is not configured.")
        self.api_key = api_key

    def ask_response(self, state: dict[str, Any], questions: dict[str, Any]) -> Any:
        try:
            from typesafe_sdk import Choice, Noul, TypeSafeClient
        except ImportError as exc:
            raise JevUnavailable("typesafe-sdk is not installed. pip install 'private-desk[jev]'.") from exc

        built: dict[str, Any] = {}
        for qid, spec in questions.items():
            if spec["type"] == "choice":
                built[qid] = Choice(instructions=spec["instructions"], criteria=spec["criteria"])
            elif spec["type"] == "noul":
                built[qid] = Noul(instructions=spec["instructions"])
        try:
            try:
                client_cm = TypeSafeClient(api_key=self.api_key)
            except TypeError:
                os.environ["TYPESAFE_API_KEY"] = self.api_key
                client_cm = TypeSafeClient()
            with client_cm as client:
                return client.system_one(state=state, questions=built)
        except JevUnavailable:
            raise
        except Exception as exc:
            raise JevUnavailable("TypeSafe request failed.") from exc

    def ask(self, state: dict[str, Any], questions: dict[str, Any]) -> Answers:
        response = self.ask_response(state, questions)
        return Answers(
            kind=_choice_of(response, "kind") or NONE_KIND,
            next=_choice_of(response, "next") or "doctor",
            kick_now=_noul_of(response, "kick_now"),
            ask_first=_noul_of(response, "ask_first"),
            use_local_only=_noul_of(response, "use_local_only"),
            mutating_ok=_noul_of(response, "mutating_ok"),
            secret_in_request=_noul_of(response, "secret_in_request"),
            job_class=_choice_of(response, "job_class"),
            keep_waiting=_noul_of(response, "keep_waiting"),
        )
