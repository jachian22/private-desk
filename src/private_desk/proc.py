"""Process-group kill: SIGTERM, wait, SIGKILL."""

from __future__ import annotations

import os
import signal
import time


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def kill_tree(pid: int, *, wait_s: float = 2.0) -> None:
    if pid <= 0:
        return
    _signal(pid, signal.SIGTERM)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if not pid_alive(pid):
            _reap(pid)
            return
        time.sleep(0.05)
    _signal(pid, signal.SIGKILL)
    deadline = time.time() + 1.0
    while time.time() < deadline:
        if not pid_alive(pid):
            break
        time.sleep(0.05)
    _reap(pid)


def _signal(pid: int, sig: int) -> None:
    try:
        os.killpg(pid, sig)
        return
    except OSError:
        pass
    try:
        os.kill(pid, sig)
    except OSError:
        pass


def _reap(pid: int) -> None:
    try:
        os.waitpid(pid, os.WNOHANG)
    except OSError:
        pass
