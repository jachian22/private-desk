"""Open an https URL in the configured browser before Holo. Holo should not hunt the Dock."""

from __future__ import annotations

import subprocess
import time
from urllib.parse import urlparse

from private_desk import paths
from private_desk.runners import RunnerError

OPEN_BIN = "/usr/bin/open"
SETTLE_S = 3.0
_DEFAULT_APP = frozenset({"", "the default web browser", "default"})
_CHROMIUM = ("chrome", "chromium", "edge", "brave", "arc", "vivaldi", "opera")


def _osa_literal(name: str) -> str:
    return name.replace("\\", "\\\\").replace('"', '\\"')


def _front_window_script(app: str, url: str) -> str | None:
    """New window on the current Space. `open -a URL` often adds a tab on another Space."""
    key = app.lower()
    a = _osa_literal(app)
    u = _osa_literal(url)
    if any(name in key for name in _CHROMIUM):
        return (
            f'tell application "{a}"\n'
            "  activate\n"
            "  make new window\n"
            f'  set URL of active tab of front window to "{u}"\n'
            "end tell"
        )
    if "safari" in key:
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


def _open_isolated_chromium(name: str, url: str) -> None:
    """New process + profile so the window is not glued to Chrome's other Space."""
    profile = paths.data_dir() / "holo-launch-profile"
    profile.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            OPEN_BIN,
            "-na",
            name,
            "--args",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--new-window",
            url,
        ],
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
            _open_isolated_chromium(name, url)
        else:
            script = _front_window_script(name, url) if name.lower() not in _DEFAULT_APP else None
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
