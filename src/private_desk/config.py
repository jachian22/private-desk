from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass, fields
from typing import Any
from pathlib import Path

from private_desk import paths

_GATEWAY_KEYCHAIN_SERVICE = "Vercel AI Gateway"


@dataclass
class Config:
    inference: str = "local"
    holo_bin: str = "holo"
    holo_base_url: str = "http://127.0.0.1:8080/v1"
    holo_model: str = "holo3-1-35b"
    artifact_root: str = ""
    repo_url: str = "https://github.com/jachian22/private-desk"
    browser: str = ""
    browser_profile: str = "private-desk"
    allow_mutating: bool = False
    typesafe_api_key: str = ""
    ai_gateway_api_key: str = ""


def load_config() -> Config:
    path = paths.config_path()
    if not path.is_file():
        return Config()
    data = tomllib.loads(path.read_text())
    cfg = Config()
    for key in cfg.__dataclass_fields__:
        if key in data:
            setattr(cfg, key, data[key])
    return cfg


def typesafe_api_key(cfg: Config | None = None) -> str:
    """Env wins. Never log the return value."""
    env = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if env:
        return env
    cfg = cfg if cfg is not None else load_config()
    return str(cfg.typesafe_api_key or "").strip()


def _keychain_ai_gateway_api_key() -> str:
    """macOS Keychain item written by `npx vercel ai-gateway setup`. Never log the return."""
    if sys.platform != "darwin":
        return ""
    if os.environ.get("PRIVATE_DESK_SKIP_KEYCHAIN", "").strip():
        return ""
    accounts = ["vercel-ai-gateway"]
    user = (os.environ.get("USER") or os.environ.get("LOGNAME") or "").strip()
    if user and user not in accounts:
        accounts.append(user)
    accounts.append("")
    for account in accounts:
        cmd = ["security", "find-generic-password", "-s", _GATEWAY_KEYCHAIN_SERVICE]
        if account:
            cmd.extend(["-a", account])
        cmd.append("-w")
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode != 0:
            continue
        key = (proc.stdout or "").strip()
        if key:
            return key
    return ""


def ai_gateway_api_key(cfg: Config | None = None) -> str:
    """Env, then config.toml, then `vercel ai-gateway setup` Keychain. Never log the return."""
    env = os.environ.get("AI_GATEWAY_API_KEY", "").strip()
    if env:
        return env
    cfg = cfg if cfg is not None else load_config()
    from_cfg = str(cfg.ai_gateway_api_key or "").strip()
    if from_cfg:
        return from_cfg
    return _keychain_ai_gateway_api_key()


def jev_configured(cfg: Config | None = None) -> bool:
    return bool(ai_gateway_api_key(cfg) or typesafe_api_key(cfg))


def typesafe_status(cfg: Config | None = None) -> str:
    if ai_gateway_api_key(cfg):
        return "gateway"
    return "configured" if typesafe_api_key(cfg) else "missing"


def browser_for_prompt(cfg: Config) -> str:
    name = (cfg.browser or "").strip()
    return name if name else "the default web browser"


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def save_config(cfg: Config) -> Path:
    """Merge known fields into config.toml. Preserve extra keys the user already set."""
    path = paths.config_path()
    existing: dict[str, Any] = {}
    if path.is_file():
        existing = tomllib.loads(path.read_text())
    data = dict(existing)
    for field in fields(cfg):
        data[field.name] = getattr(cfg, field.name)
    lines = [f"{key} = {_toml_scalar(value)}" for key, value in data.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def artifact_root_path(cfg: Config) -> Path:
    raw = (cfg.artifact_root or "").strip()
    if raw:
        return Path(raw).expanduser()
    return paths.data_dir() / "inbox"
