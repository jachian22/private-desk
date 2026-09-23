import subprocess
from pathlib import Path

import pytest

from private_desk.launch import open_dino_chrome, open_https
from private_desk.runners import RunnerError


def test_open_https_chrome_makes_a_new_window(monkeypatch):
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("private_desk.launch.subprocess.run", fake_run)
    open_https("Google Chrome", "https://github.com/jachian22/private-desk", settle_s=0)
    assert seen[0][0] == "/usr/bin/osascript"
    script = seen[0][-1]
    assert "make new window" in script
    assert "github.com/jachian22/private-desk" in script
    assert seen[1][0] == "/usr/bin/osascript"
    assert "desktopBounds" in seen[1][-1]


def test_open_https_unknown_app_uses_open(monkeypatch):
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("private_desk.launch.subprocess.run", fake_run)
    open_https("Firefox", "https://example.com", settle_s=0)
    assert seen[0][:3] == ["/usr/bin/open", "-a", "Firefox"]
    assert any("desktopBounds" in " ".join(cmd) for cmd in seen)


def test_open_https_isolated_chromium(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIVATE_DESK_HOME", str(tmp_path))
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("private_desk.launch.subprocess.run", fake_run)
    open_https("Google Chrome", "https://github.com/example", settle_s=0, isolated=True)
    assert seen[0][0:3] == ["/usr/bin/open", "-na", "Google Chrome"]
    joined = " ".join(seen[0])
    assert "--user-data-dir=" in joined
    assert "--new-window" in seen[0]
    assert "https://github.com/example" in seen[0]
    assert all(cmd[0] != "/usr/bin/osascript" for cmd in seen)


def test_open_https_isolated_reuse_skips_new_window(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIVATE_DESK_HOME", str(tmp_path))
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("private_desk.launch.subprocess.run", fake_run)
    monkeypatch.setattr("private_desk.launch.isolated_browser_pids", lambda profile=None: [])
    open_https(
        "Google Chrome",
        "https://github.com/example",
        settle_s=0,
        isolated=True,
        reuse=True,
    )
    assert "--new-window" not in seen[0]
    assert "https://github.com/example" in seen[0]


def test_open_https_isolated_reuse_skips_when_job_chrome_already_open(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIVATE_DESK_HOME", str(tmp_path))
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("private_desk.launch.subprocess.run", fake_run)
    monkeypatch.setattr("private_desk.launch.isolated_browser_pids", lambda profile=None: [99])
    open_https(
        "Google Chrome",
        "https://github.com/example",
        settle_s=0,
        isolated=True,
        reuse=True,
    )
    assert seen == []


def test_close_job_browser_only_isolated(monkeypatch):
    killed: list[int] = []
    remaining = {4242, 4243}

    def fake_pids(profile=None):
        return list(remaining)

    def fake_kill(pid, sig):
        killed.append(pid)
        remaining.discard(pid)

    monkeypatch.setattr("private_desk.launch.isolated_browser_pids", fake_pids)
    monkeypatch.setattr("private_desk.launch.os.kill", fake_kill)
    from private_desk.launch import close_job_browser

    close_job_browser(isolated=False)
    assert killed == []
    close_job_browser(isolated=True)
    assert killed == [4242, 4243]


def test_open_https_skips_empty_and_rejects_non_http(monkeypatch):
    monkeypatch.setattr(
        "private_desk.launch.subprocess.run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not open")),
    )
    open_https("Safari", "", settle_s=0)
    with pytest.raises(RunnerError) as exc:
        open_https("Safari", "file:///etc/passwd", settle_s=0)
    assert exc.value.code == "kind_denied"
    with pytest.raises(RunnerError) as exc:
        open_https("Google Chrome", "chrome://dino", settle_s=0)
    assert exc.value.code == "kind_denied"


def test_open_dino_chrome_loopback_isolated_profile(isolated, monkeypatch):
    seen: list[list[str]] = []
    binary = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    def fake_popen(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("private_desk.launch.close_dino_browser", lambda: None)
    monkeypatch.setattr(
        "private_desk.launch.chromium_macos_binary",
        lambda _app: Path(binary),
    )
    monkeypatch.setattr("private_desk.launch.subprocess.Popen", fake_popen)
    open_dino_chrome("Google Chrome", settle_s=0)
    cmd = seen[0]
    assert cmd[0] == binary
    assert "--remote-debugging-address=127.0.0.1" in cmd
    assert "--remote-debugging-port=0" in cmd
    assert "0.0.0.0" not in " ".join(cmd)
    assert "chrome://dino/" in cmd
    assert "--new-window" in cmd
    assert not any(part.startswith("--app=") for part in cmd)
    assert "--force-device-scale-factor=1" not in cmd
    assert not any(part.startswith("--window-size=") for part in cmd)
    assert "about:blank" not in cmd
    blob = " ".join(cmd)
    assert "dino-launch-profile" in blob
    assert "holo-launch-profile" not in blob


def test_open_dino_chrome_rejects_safari(isolated):
    with pytest.raises(RunnerError) as exc:
        open_dino_chrome("Safari", settle_s=0)
    assert exc.value.code == "kind_denied"
