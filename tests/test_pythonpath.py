import os
import stat

from private_desk.pythonpath import apply_worker_pythonpath, persist_src_pth, src_dir


def test_src_dir_points_at_package():
    assert (src_dir() / "private_desk" / "cli.py").is_file()


def test_worker_pythonpath_puts_src_first():
    env = apply_worker_pythonpath({"PYTHONPATH": "/tmp/other"})
    parts = env["PYTHONPATH"].split(os.pathsep)
    assert parts[0] == str(src_dir())
    assert "/tmp/other" in parts


def test_persist_src_pth_replaces_hidden_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "private_desk.pythonpath.sysconfig.get_path",
        lambda _name: str(tmp_path),
    )
    dest = tmp_path / "private_desk_src.pth"
    dest.write_text("stale\n")
    hidden = getattr(stat, "UF_HIDDEN", 0)
    if hidden and hasattr(os, "chflags"):
        os.chflags(dest, os.lstat(dest).st_flags | hidden)
        assert dest.stat().st_flags & hidden
    out = persist_src_pth()
    assert out == dest
    assert src_dir().as_posix() in dest.read_text()
    assert "stale" not in dest.read_text()
    if hidden:
        assert (dest.stat().st_flags & hidden) == 0
