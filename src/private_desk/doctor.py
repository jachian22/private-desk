from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Any

from private_desk.config import load_config, typesafe_status
from private_desk.local_model import boot_notes, probe_local_model

PROTOCOL = "private-desk/v0"

_SKIP_COMM = frozenset(
    {
        "zsh",
        "bash",
        "sh",
        "fish",
        "dash",
        "login",
        "launchd",
        "python",
        "python3",
        "pytest",
        "uv",
        "private-desk",
    }
)

_APP_MARKERS: tuple[tuple[str, str], ...] = (
    ("cursor.app", "Cursor"),
    ("iterm", "iTerm"),
    ("terminal.app", "Terminal"),
    ("warp.app", "Warp"),
    ("ghostty", "Ghostty"),
    ("visual studio code", "Visual Studio Code"),
    ("code.app", "Visual Studio Code"),
    ("alacritty", "Alacritty"),
    ("kitty.app", "kitty"),
)


def _which(name: str) -> str | None:
    return shutil.which(name)


def _process_row(pid: int) -> tuple[str, int, str] | None:
    try:
        proc = subprocess.run(
            ["ps", "-p", str(pid), "-ww", "-o", "ppid=,comm=,command="],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    line = proc.stdout.strip()
    if proc.returncode != 0 or not line:
        return None
    parts = line.split(None, 2)
    if len(parts) < 2:
        return None
    try:
        ppid = int(parts[0])
    except ValueError:
        return None
    comm = parts[1]
    command = parts[2] if len(parts) > 2 else ""
    return comm, ppid, command


def _friendly_app(comm: str, command: str) -> str | None:
    blob = f"{comm} {command}".lower()
    for marker, label in _APP_MARKERS:
        if marker in blob:
            return label
    stem = comm.rsplit("/", 1)[-1].lower()
    if stem.startswith("python") or stem in _SKIP_COMM:
        return None
    return None


def spawn_parent_app(start_pid: int | None = None) -> str | None:
    """App that spawned this CLI (Terminal, Cursor, iTerm, …). Not a config field."""
    pid = start_pid if start_pid is not None else os.getppid()
    seen: set[int] = set()
    while pid and pid > 1 and pid not in seen:
        seen.add(pid)
        row = _process_row(pid)
        if not row:
            return None
        comm, ppid, command = row
        label = _friendly_app(comm, command)
        if label:
            return label
        pid = ppid
    return None


def screen_recording_note(parent: str | None) -> str:
    if parent:
        return (
            f"Screen Recording: grant to hai-agent-runtime and {parent} "
            "(whatever actually ran private-desk this time). Accessibility too."
        )
    return (
        "Screen Recording: grant to hai-agent-runtime and the app that ran "
        "private-desk (Terminal, Cursor, iTerm, …). Accessibility too."
    )


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
    parent = spawn_parent_app()
    cli_on_path = "ok" if _which("private-desk") else "missing"
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
        "spawn_parent": parent or "unknown",
        "cli_on_path": cli_on_path,
        "dummy_kinds": "ok" if dummy_ok else "fail",
        "holo_kinds": "ok" if holo_ok else "blocked",
        "typesafe": typesafe_status(cfg),
    }
    notes = [
        "demo_dummy_files does not need Holo. Missing holo is not a doctor failure.",
        "Public demos demo_open_repo, demo_star_repo, and demo_post_x use hosted Holo (screens go to H Company).",
        "demo_dino is not Holo: Jev sees Runner numbers, code taps keys over loopback CDP. Needs Chromium + Jev (Vercel AI Gateway or TypeSafe).",
        "demo_dino on macOS Sequoia: App Management for the app that ran private-desk (Terminal, Cursor, …) so it can launch and quit the throwaway Chrome. Not Full Disk Access.",
        "Bank and session-canary kinds require local llama.cpp at holo_base_url.",
        "Holo never types passwords. Account kinds use browser + browser_profile from config (private-desk setup).",
        "demo_star_repo and demo_post_x need allow_mutating = true in config.toml.",
        "decide (Jev-gated asks) and demo_dino need Jev: AI_GATEWAY_API_KEY, `npx vercel ai-gateway setup` (macOS Keychain), or TYPESAFE_API_KEY. Dummy and mapped start still work without it.",
        screen_recording_note(parent),
    ]
    if holo["holo"] == "missing":
        notes.insert(0, "Holo missing: install HoloDesktop before demo_open_repo. Dummy kinds still work.")
    if not (cfg.browser or "").strip():
        notes.append(
            'Holo kinds use {browser} from config. Ask which app (menu-bar name), then: '
            'private-desk setup --browser "Google Chrome"'
        )
    if cli_on_path != "ok":
        notes.append(
            "private-desk is not on PATH. Put the repo .venv/bin on PATH in ~/.zprofile and ~/.zshrc. "
            "A Bot that cannot find the command should stop, not set PYTHONPATH=src."
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
