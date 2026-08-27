from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from private_desk import paths


@dataclass
class Config:
    inference: str = "local"
    holo_bin: str = "holo"
    holo_base_url: str = "http://127.0.0.1:8080/v1"
    holo_model: str = "holo3-1-35b"
    artifact_root: str = ""
    repo_url: str = "https://github.com"
    browser_profile: str = "private-desk"
    allow_mutating: bool = False


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


def artifact_root_path(cfg: Config) -> Path:
    raw = (cfg.artifact_root or "").strip()
    if raw:
        return Path(raw).expanduser()
    return paths.data_dir() / "inbox"
