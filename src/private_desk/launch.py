"""Open an https URL in the configured browser before Holo. Holo should not hunt the Dock."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from private_desk import paths
from private_desk.runners import RunnerError

OPEN_BIN = "/usr/bin/open"
SETTLE_S = 3.0
_DEFAULT_APP = frozenset({"", "the default web browser", "default"})
_CHROMIUM = ("chrome", "chromium", "edge", "brave", "arc", "vivaldi", "opera")
ISOLATED_PROFILE = "holo-launch-profile"


def isolated_profile_dir() -> Path:
    return paths.data_dir() / ISOLATED_PROFILE


def _osa_literal(name: str) -> str:
    return name.replace("\\", "\\\\").replace('"', '\\"')


def _front_window_script(app: str, url: str, *, reuse: bool) -> str | None:
    """New window on the current Space, or navigate the front window on resume."""
    key = app.lower()
    a = _osa_literal(app)
    u = _osa_literal(url)
    if any(name in key for name in _CHROMIUM):
        if reuse:
            return (
                f'tell application "{a}"\n'
                "  activate\n"
                "  if (count of windows) is 0 then make new window\n"
                f'  set URL of active tab of front window to "{u}"\n'
                "end tell"
            )
        return (
            f'tell application "{a}"\n'
            "  activate\n"
            "  make new window\n"
            f'  set URL of active tab of front window to "{u}"\n'
            "end tell"
        )
    if "safari" in key:
        if reuse:
            return (
                f'tell application "{a}"\n'
                "  activate\n"
                "  if (count of documents) is 0 then make new document\n"
                f'  set URL of document 1 to "{u}"\n'
                "end tell"
            )
        return (
            f'tell application "{a}"\n'
            "  activate\n"
            f'  make new document with properties {{URL:"{u}"}}\n'
            "end tell"
        )
    return None


def _pin_front_window_script(app: str) -> str:
    """Move the front window onto the main desktop (the display Holo typically captures)."""
    a = _osa_literal(app)
    return (
        'tell application "Finder"\n'
        "  set desktopBounds to bounds of window of desktop\n"
        "end tell\n"
        f'tell application "{a}"\n'
        "  activate\n"
        "  if (count of windows) is 0 then return\n"
        "  try\n"
        "    set miniaturized of window 1 to false\n"
        "  end try\n"
        "  set bounds of window 1 to desktopBounds\n"
        "end tell"
    )


def pin_front_window(app: str) -> None:
    name = (app or "").strip()
    if not name or name.lower() in _DEFAULT_APP:
        return
    subprocess.run(
        ["/usr/bin/osascript", "-e", _pin_front_window_script(name)],
        check=False,
        capture_output=True,
        timeout=15,
    )


def _open_isolated_chromium(name: str, url: str, *, reuse: bool) -> None:
    """Job Chrome: separate user-data-dir so we can quit it without the daily browser."""
    profile = isolated_profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    # After login the window is already on the repo. Passing the URL again
    # opens a duplicate tab, then close_job_browser kills the whole profile.
    if reuse and isolated_browser_pids(profile):
        return
    cmd = [
        OPEN_BIN,
        "-na",
        name,
        "--args",
        f"--user-data-dir={profile}",
        "--no-first-run",
    ]
    if not reuse:
        cmd.append("--new-window")
    cmd.append(url)
    subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        timeout=30,
    )


def open_https(
    app: str,
    url: str,
    *,
    settle_s: float = SETTLE_S,
    isolated: bool = False,
    reuse: bool = False,
) -> None:
    url = (url or "").strip()
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RunnerError("kind_denied", "launch_url must be an http(s) URL.")
    name = (app or "").strip()
    try:
        if isolated and any(tag in name.lower() for tag in _CHROMIUM):
            _open_isolated_chromium(name, url, reuse=reuse)
        else:
            script = (
                _front_window_script(name, url, reuse=reuse)
                if name.lower() not in _DEFAULT_APP
                else None
            )
            opened = False
            if script:
                result = subprocess.run(
                    ["/usr/bin/osascript", "-e", script],
                    check=False,
                    capture_output=True,
                    timeout=30,
                )
                opened = result.returncode == 0
            if not opened:
                _open_fallback(name, url)
            pin_front_window(name)
    except FileNotFoundError as exc:
        raise RunnerError("runtime_unavailable", "macOS open/osascript is missing.") from exc
    except subprocess.CalledProcessError as exc:
        raise RunnerError(
            "model_error",
            f"Could not open the URL in {name or 'the default browser'}.",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RunnerError("timeout", "Timed out opening the browser.") from exc
    if settle_s > 0:
        time.sleep(settle_s)


def isolated_browser_pids(profile: Path | None = None) -> list[int]:
    needle = str(profile or isolated_profile_dir())
    try:
        proc = subprocess.run(
            ["pgrep", "-f", needle],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    pids: list[int] = []
    me = os.getpid()
    for token in proc.stdout.split():
        try:
            pid = int(token)
        except ValueError:
            continue
        if pid != me:
            pids.append(pid)
    return pids


def close_job_browser(*, isolated: bool) -> None:
    """Quit only the job Chrome (isolated profile). Never the daily browser."""
    if not isolated:
        return
    for pid in isolated_browser_pids():
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            continue


def _open_fallback(name: str, url: str) -> None:
    cmd = [OPEN_BIN]
    if name.lower() not in _DEFAULT_APP:
        cmd.extend(["-a", name])
    cmd.append(url)
    subprocess.run(cmd, check=True, capture_output=True, timeout=30)
    if name.lower() not in _DEFAULT_APP:
        subprocess.run(
            [
                "/usr/bin/osascript",
                "-e",
                f'tell application "{_osa_literal(name)}" to activate',
            ],
            check=False,
            capture_output=True,
            timeout=10,
        )
