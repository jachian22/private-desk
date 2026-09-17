from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from private_desk import paths
from private_desk.config import Config

SECRET_KEY_RE = re.compile(
    r"^(.*_)?(password|passwd|secret|token|otp|mfa|sms|cookie|session|ssn|pan|"
    r"account_number|routing)(s|_.*)?$",
    re.I,
)


class KindError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class Kind:
    id: str
    title: str
    description: str
    risk: str
    inference: str
    may_need_you: bool
    runner: str
    requires_artifacts: bool
    max_steps: int
    max_time_s: int
    url_allowlist: list[str]
    denied_actions: list[str]
    params: dict[str, Any]
    dir_template: str
    prompt: str
    confirm_token: str
    launch_url: str
    launch_isolated: bool
    source: Path

    def public_view(self, resolved_inference: str) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "risk": self.risk,
            "inference": resolved_inference,
            "may_need_you": self.may_need_you,
            "params": self.params,
        }


def _is_runnable_kind_file(path: Path) -> bool:
    if path.suffix not in {".yaml", ".yml"}:
        return False
    if path.name.startswith("_"):
        return False
    if path.name.endswith(".template.yaml") or path.name.endswith(".template.yml"):
        return False
    return True


def _load_file(path: Path) -> Kind:
    raw = yaml.safe_load(path.read_text()) or {}
    artifacts = raw.get("artifacts") or {}
    return Kind(
        id=raw["id"],
        title=raw.get("title") or raw["id"],
        description=raw.get("description") or "",
        risk=raw.get("risk") or "read_only",
        inference=raw.get("inference") or "inherit",
        may_need_you=bool(raw.get("may_need_you")),
        runner=raw.get("runner") or "holo",
        requires_artifacts=bool(raw.get("requires_artifacts")),
        max_steps=int(raw.get("max_steps") or 40),
        max_time_s=int(raw.get("max_time_s") or 600),
        url_allowlist=list(raw.get("url_allowlist") or []),
        denied_actions=list(raw.get("denied_actions") or []),
        params=raw.get("params") or {"type": "object", "additionalProperties": False, "properties": {}},
        dir_template=(artifacts.get("dir_template") or "{artifact_root}/{date}/{kind}"),
        prompt=raw.get("prompt") or "",
        confirm_token=str(raw.get("confirm_token") or "").strip(),
        launch_url=str(raw.get("launch_url") or "").strip(),
        launch_isolated=bool(raw.get("launch_isolated")),
        source=path,
    )


def load_kinds() -> dict[str, Kind]:
    kinds: dict[str, Kind] = {}
    for directory in (paths.public_kinds_dir(), paths.private_kinds_dir()):
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if not _is_runnable_kind_file(path):
                continue
            kind = _load_file(path)
            kinds[kind.id] = kind  # private dir loaded second → wins
    return kinds


def get_kind(kind_id: str) -> Kind:
    kinds = load_kinds()
    if kind_id not in kinds:
        raise KindError(f"Unknown kind '{kind_id}'.")
    return kinds[kind_id]


def resolve_inference(kind: Kind, cfg: Config) -> str:
    if kind.inference == "inherit":
        return cfg.inference
    return kind.inference


def reject_secret_param_keys(params: dict[str, Any]) -> None:
    for key in params:
        if SECRET_KEY_RE.match(str(key)):
            raise KindError(f"Param name '{key}' is not allowed.")


def validate_params(kind: Kind, params: dict[str, Any]) -> dict[str, Any]:
    reject_secret_param_keys(params)
    schema = kind.params or {}
    props = schema.get("properties") or {}
    if schema.get("additionalProperties") is False:
        extra = set(params) - set(props)
        if extra:
            raise KindError(f"Unknown params: {', '.join(sorted(extra))}.")
    for key in schema.get("required") or []:
        if key not in params:
            raise KindError(f"Missing required param '{key}'.")
    for key, value in params.items():
        spec = props.get(key) or {}
        if spec.get("type") == "string" and not isinstance(value, str):
            raise KindError(f"Param '{key}' must be a string.")
        if "enum" in spec and value not in spec["enum"]:
            raise KindError(f"Param '{key}' must be one of {spec['enum']}.")
    return params


def interpolate_template(template: str, params: dict[str, Any], extra: dict[str, str]) -> str:
    if not (template or "").strip():
        return ""
    mapping = {**params, **extra}
    try:
        return template.format(**mapping)
    except KeyError as exc:
        raise KindError(f"Kind interpolation missing key {exc}.") from exc


def interpolate_prompt(kind: Kind, params: dict[str, Any], extra: dict[str, str]) -> str:
    return interpolate_template(kind.prompt, params, extra)
