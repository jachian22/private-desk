from __future__ import annotations

import platform
import shutil
import subprocess
from typing import Any

from private_desk.config import load_config
from private_desk.local_model import boot_notes, probe_local_model

PROTOCOL = "private-desk/v0"


def _which(name: str) -> str | None:
    return shutil.which(name)


def _holo_doctor(holo_bin: str) -> dict[str, Any]:
    path = _which(holo_bin)
    if not path:
        return {"holo": "missing", "permissions": "unknown", "holo_doctor": "missing"}
    try:
        proc = subprocess.run(
            [path, "doctor"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "holo": "ok",
            "permissions": "unknown",
            "holo_doctor": "failed",
        }
    # Exit code only. Do not grep holo doctor English for permissions.
    permissions = "ok" if proc.returncode == 0 else "not_ready"
    return {
        "holo": "ok",
        "permissions": permissions,
        "holo_doctor": "ran",
        "holo_doctor_exit": proc.returncode,
    }


def run_doctor(*, strict: bool = False) -> dict[str, Any]:
    cfg = load_config()
    holo = _holo_doctor(cfg.holo_bin)
    local = probe_local_model(cfg.holo_base_url)
    dummy_ok = True
    holo_ok = holo["holo"] == "ok"
    checks = {
        "holo": holo["holo"],
        "permissions": holo["permissions"],
        "local_model": local,
        "llama_cpp": local,
        "webhook": "not used in v1",
        "platform": platform.system(),
        "allow_mutating": cfg.allow_mutating,
        "inference_default": cfg.inference,
        "browser": cfg.browser or "unset",
        "dummy_kinds": "ok" if dummy_ok else "fail",
        "holo_kinds": "ok" if holo_ok else "blocked",
    }
    notes = [
        "demo_dummy_files does not need Holo. Missing holo is not a doctor failure.",
        "Public demos demo_open_repo and demo_star_repo use hosted Holo (screens go to H Company).",
        "Bank and session-canary kinds require local llama.cpp at holo_base_url.",
        "Holo never types passwords. Account kinds use browser + browser_profile from config (private-desk setup).",
        "demo_star_repo needs allow_mutating = true in config.toml.",
        "If holo doctor exited non-zero, grant Screen Recording and Accessibility, then re-run.",
    ]
    if holo["holo"] == "missing":
        notes.insert(0, "Holo missing: install HoloDesktop before demo_open_repo. Dummy kinds still work.")
    if not (cfg.browser or "").strip():
        notes.append(
            'Holo kinds use {browser} from config. Ask which app (menu-bar name), then: '
            'private-desk setup --browser "Google Chrome"'
        )
    if local != "reachable":
        notes.extend(boot_notes(cfg.holo_base_url))
    ok = True
    exit_code = 0
    if strict and (not holo_ok or holo["permissions"] != "ok"):
        ok = False
        exit_code = 5
    return {
        "protocol": PROTOCOL,
        "ok": ok,
        "checks": checks,
        "notes": notes,
        "exit_code": exit_code,
    }
