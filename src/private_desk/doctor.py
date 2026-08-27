from __future__ import annotations

import platform
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any

from private_desk.config import load_config

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
    permissions = "ok" if proc.returncode == 0 else "unknown"
    return {
        "holo": "ok",
        "permissions": permissions,
        "holo_doctor": "ran",
        "holo_doctor_exit": proc.returncode,
    }


def _local_model(url: str) -> str:
    try:
        req = urllib.request.Request(url.rstrip("/") + "/models", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            resp.read(256)
        return "reachable"
    except (urllib.error.URLError, TimeoutError, OSError):
        return "unreachable"


def run_doctor(*, strict: bool = False) -> dict[str, Any]:
    cfg = load_config()
    holo = _holo_doctor(cfg.holo_bin)
    local = _local_model(cfg.holo_base_url)
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
        "dummy_kinds": "ok" if dummy_ok else "fail",
        "holo_kinds": "ok" if holo_ok else "blocked",
    }
    notes = [
        "demo_dummy_files does not need Holo. Missing holo is not a doctor failure.",
        "Public demos demo_open_repo and demo_star_repo use hosted Holo (screens go to H Company).",
        "Bank and session-canary kinds require local llama.cpp at holo_base_url.",
        "Holo never types passwords. Log into sites in the private-desk Chrome profile first.",
        "demo_star_repo needs allow_mutating = true in config.toml.",
        "If holo doctor exited non-zero, grant Screen Recording and Accessibility, then re-run.",
    ]
    if holo["holo"] == "missing":
        notes.insert(0, "Holo missing: install HoloDesktop before demo_open_repo. Dummy kinds still work.")
    ok = True
    exit_code = 0
    if strict and (not holo_ok or holo["permissions"] == "os_permission"):
        ok = False
        exit_code = 5
    return {
        "protocol": PROTOCOL,
        "ok": ok,
        "checks": checks,
        "notes": notes,
        "exit_code": exit_code,
    }
