"""Exclusive desktop lock via flock. Released when the worker process exits."""

from __future__ import annotations

import json
import os
from typing import Any

from private_desk import paths

try:
    import fcntl
except ImportError:  # pragma: no cover - v1 is macOS/Linux
    fcntl = None  # type: ignore[assignment]


class DesktopLock:
    """Holds LOCK_EX on desktop.lock. Parent must detach(); worker must close()."""

    def __init__(self, fd: int) -> None:
        self.fd = fd

    @classmethod
    def try_acquire(cls, job_id: str) -> DesktopLock | None:
        if fcntl is None:
            raise RuntimeError("fcntl.flock is required (macOS/Linux).")
        paths.data_dir().mkdir(parents=True, exist_ok=True)
        fd = os.open(str(paths.lock_path()), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return None
        lock = cls(fd)
        lock.write_meta(job_id, 0)
        return lock

    @classmethod
    def inherit(cls, fd: int) -> DesktopLock:
        return cls(fd)

    def write_meta(self, job_id: str, pid: int) -> None:
        payload = json.dumps({"job_id": job_id, "pid": pid}) + "\n"
        os.lseek(self.fd, 0, os.SEEK_SET)
        os.ftruncate(self.fd, 0)
        os.write(self.fd, payload.encode())
        os.fsync(self.fd)

    def detach_parent(self) -> None:
        """Close this process's fd without LOCK_UN so the child keeps the flock."""
        os.close(self.fd)

    def close(self) -> None:
        if fcntl is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            except OSError:
                pass
        try:
            os.close(self.fd)
        except OSError:
            pass


def lock_meta() -> dict[str, Any] | None:
    p = paths.lock_path()
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
