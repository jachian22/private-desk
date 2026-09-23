"""TypeSafe adapter, Vercel AI Gateway evaluate, scripted policy, injectable fake."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from types import SimpleNamespace
from typing import Any, Protocol

from private_desk.config import Config, ai_gateway_api_key, typesafe_api_key
from private_desk.jev.mixer import Answers
from private_desk.jev.questions import NONE_KIND
from private_desk.kinds import Kind

GATEWAY_EVALUATE_URL = "https://ai-gateway.vercel.sh/v4/ai/evaluation-model"
GATEWAY_MODEL_ID = "typesafe-ai/jev"
_NO_JEV_KEY = (
    "Jev is not configured. Set AI_GATEWAY_API_KEY, run `npx vercel ai-gateway setup`, or set TYPESAFE_API_KEY. "
    "Formulaic start still works."
)


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
    for bag_name in ("choices", "answers"):
        bag = getattr(response, bag_name, None)
        if not bag or key not in bag:
            continue
        obj = bag[key]
        if isinstance(obj, dict):
            value = obj.get("choice")
        else:
            value = getattr(obj, "choice", None)
        if value is not None:
            return str(value)
    return None


def _noul_from(obj: Any) -> float | None:
    if obj is None:
        return None
    if isinstance(obj, dict):
        if "noul" in obj:
            return _noul(obj.get("noul"))
        if "probability" in obj:
            return _noul(obj.get("probability"))
        return None
    if hasattr(obj, "noul"):
        return _noul(getattr(obj, "noul", 0.0))
    if hasattr(obj, "probability"):
        return _noul(getattr(obj, "probability", 0.0))
    return None


def _noul_of(response: Any, key: str) -> float:
    nouls = getattr(response, "nouls", None)
    if nouls and key in nouls:
        found = _noul_from(nouls[key])
        if found is not None:
            return found
    answers = getattr(response, "answers", None)
    if answers and key in answers:
        found = _noul_from(answers[key])
        if found is not None:
            return found
    return 0.0


def answers_from_response(response: Any) -> Answers:
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
        return answers_from_response(self.ask_response(state, questions))


def _gateway_questions(questions: dict[str, Any]) -> dict[str, Any]:
    built: dict[str, Any] = {}
    for qid, spec in questions.items():
        qtype = spec["type"]
        if qtype == "noul":
            qtype = "boolean"
        item: dict[str, Any] = {"type": qtype, "instructions": spec["instructions"]}
        if spec.get("criteria"):
            item["criteria"] = spec["criteria"]
        built[qid] = item
    return built


def _gateway_response(payload: dict[str, Any]) -> SimpleNamespace:
    raw = payload.get("answers")
    if not isinstance(raw, dict):
        raise JevUnavailable("Vercel AI Gateway returned no answers.")
    choices: dict[str, Any] = {}
    nouls: dict[str, Any] = {}
    answers: dict[str, Any] = {}
    for qid, ans in raw.items():
        if not isinstance(ans, dict):
            continue
        kind = ans.get("type")
        if kind == "boolean":
            obj = SimpleNamespace(noul=_noul(ans.get("probability")), type="boolean")
            nouls[qid] = obj
            answers[qid] = obj
        elif kind == "choice":
            obj = SimpleNamespace(choice=ans.get("choice"), type="choice")
            choices[qid] = obj
            answers[qid] = obj
        else:
            answers[qid] = SimpleNamespace(**ans)
    return SimpleNamespace(choices=choices, nouls=nouls, answers=answers)


def _gateway_http_hint(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode(errors="replace") if exc.fp is not None else ""
        data = json.loads(raw) if raw else {}
    except Exception:
        return ""
    err = data.get("error") if isinstance(data, dict) else None
    if not isinstance(err, dict):
        return ""
    kind = str(err.get("type") or "")
    if kind == "customer_verification_required":
        return " Add a credit card on the Vercel AI Gateway page to unlock free credits."
    return ""


def _post_gateway(url: str, headers: dict[str, str], body: bytes, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        hint = _gateway_http_hint(exc)
        raise JevUnavailable(f"Vercel AI Gateway request failed (HTTP {exc.code}).{hint}") from exc
    except JevUnavailable:
        raise
    except Exception as exc:
        raise JevUnavailable("Vercel AI Gateway request failed.") from exc
    if not isinstance(payload, dict):
        raise JevUnavailable("Vercel AI Gateway returned no answers.")
    return payload


class VercelGatewayJevClient:
    """Jev via Gateway evaluate (`/v4/ai/evaluation-model`). Not chat completions."""

    def __init__(
        self,
        api_key: str,
        *,
        model_id: str = GATEWAY_MODEL_ID,
        url: str = GATEWAY_EVALUATE_URL,
        post: Any | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise JevUnavailable("Vercel AI Gateway API key is not configured.")
        self.api_key = api_key
        self.model_id = model_id
        self.url = url
        self._post = post or _post_gateway
        self.timeout = timeout

    def ask_response(self, state: dict[str, Any], questions: dict[str, Any]) -> Any:
        body = json.dumps(
            {
                "state": state,
                "questions": _gateway_questions(questions),
            }
        ).encode()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "ai-evaluation-model-specification-version": "4",
            "ai-model-id": self.model_id,
            "ai-gateway-protocol-version": "0.0.1",
            "ai-gateway-auth-method": "api-key",
        }
        payload = self._post(self.url, headers, body, self.timeout)
        return _gateway_response(payload)

    def ask(self, state: dict[str, Any], questions: dict[str, Any]) -> Answers:
        return answers_from_response(self.ask_response(state, questions))


def live_jev_client(cfg: Config | None = None) -> JevClient:
    gw = ai_gateway_api_key(cfg)
    if gw:
        return VercelGatewayJevClient(gw)
    key = typesafe_api_key(cfg)
    if not key:
        raise JevUnavailable(_NO_JEV_KEY)
    return TypeSafeJevClient(key)
