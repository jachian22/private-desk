"""Keep src/ importable. macOS marks some pip editable .pth files UF_HIDDEN; CPython skips them."""

from __future__ import annotations

import os
import stat
import sysconfig
from pathlib import Path


def src_dir() -> Path:
    # src/private_desk/pythonpath.py → src/
    return Path(__file__).resolve().parents[1]


def _clear_hidden(path: Path) -> None:
    uf = getattr(stat, "UF_HIDDEN", 0)
    if not uf or not hasattr(os, "chflags"):
        return
    try:
        flags = os.lstat(path).st_flags
        if flags & uf:
            os.chflags(path, flags & ~uf)
    except OSError:
        pass


def persist_src_pth() -> Path | None:
    """Write a fresh (not macOS-hidden) site-packages .pth so `python -m` works without PYTHONPATH."""
    src = src_dir()
    if not (src / "private_desk").is_dir():
        return None
    try:
        dest = Path(sysconfig.get_path("purelib")) / "private_desk_src.pth"
        # Overwriting an existing hidden file keeps UF_HIDDEN. Replace it.
        dest.unlink(missing_ok=True)
        dest.write_text(str(src) + "\n")
        _clear_hidden(dest)
        for pth in dest.parent.glob("*.pth"):
            name = pth.name.lower()
            if "private_desk" in name or name.startswith("__editable__"):
                _clear_hidden(pth)
        return dest
    except OSError:
        return None


def apply_worker_pythonpath(env: dict[str, str]) -> dict[str, str]:
    """Forked workers do not inherit a console-script sys.path hack."""
    src = str(src_dir())
    existing = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p and p != src]
    env["PYTHONPATH"] = os.pathsep.join([src, *existing])
    return env
