"""Filesystem layout. Override with PRIVATE_DESK_HOME in tests."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "private-desk"


def home_override() -> Path | None:
    raw = os.environ.get("PRIVATE_DESK_HOME")
    return Path(raw).expanduser() if raw else None


def config_dir() -> Path:
    override = home_override()
    if override:
        return override / "config"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / APP_NAME
    return Path.home() / ".config" / APP_NAME


def data_dir() -> Path:
    override = home_override()
    if override:
        return override / "data"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def jobs_dir() -> Path:
    return data_dir() / "jobs"


def job_dir(job_id: str) -> Path:
    return jobs_dir() / job_id


def lock_path() -> Path:
    return data_dir() / "desktop.lock"


def private_kinds_dir() -> Path:
    return config_dir() / "kinds"


def public_kinds_dir() -> Path:
    env = os.environ.get("PRIVATE_DESK_PUBLIC_KINDS")
    if env:
        return Path(env)
    # src/private_desk/paths.py -> repo root / kinds when developing
    return Path(__file__).resolve().parents[2] / "kinds"


def config_path() -> Path:
    return config_dir() / "config.toml"
