"""Loopback Chrome DevTools for chrome://dino. Never bind 0.0.0.0."""

from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse, urlunparse

from private_desk.runners import RunnerError

SNAPSHOT_JS = """
(() => {
  const r = window.Runner && Runner.instance_;
  if (!r) return {ready: false};
  const obs = (r.horizon && r.horizon.obstacles)
    ? r.horizon.obstacles.map((o) => ({
        type: (o.typeConfig && o.typeConfig.type) || "UNKNOWN",
        x: o.xPos,
        y: o.yPos,
        width: o.width,
      }))
    : [];
  const near = obs[0] || null;
  const out = {
    ready: true,
    playing: !!r.playing,
    crashed: !!r.crashed,
    speed: r.currentSpeed,
    distance: r.distanceRan,
    grounded: !!(r.tRex && !r.tRex.jumping),
    jumping: !!(r.tRex && r.tRex.jumping),
    ducking: !!(r.tRex && r.tRex.ducking),
    obstacles: obs.slice(0, 4),
    nearest_type: near ? near.type : null,
    nearest_x: near ? near.x : null,
    nearest_y: near ? near.y : null,
    nearest_width: near ? near.width : null,
    started: !!(r.playing || r.activated || (r.distanceRan || 0) > 0),
    runningTime: r.runningTime || 0,
  };
  // Freeze only after the run has actually left the start screen.
  if ((r.distanceRan || 0) > 0) r.playing = false;
  return out;
})()
"""

RESUME_JS = """
(() => {
  const r = window.Runner && Runner.instance_;
  if (!r || r.crashed) return;
  r.paused = false;
  r.activated = true;
  r.time = (typeof performance !== "undefined" && performance.now)
    ? performance.now()
    : Date.now();
  if (typeof r.setPlayStatus === "function") r.setPlayStatus(true);
  else r.playing = true;
  r.updatePending = false;
  if (typeof r.scheduleNextUpdate === "function") r.scheduleNextUpdate();
  else if (typeof r.update === "function") r.update();
})()
"""

START_JS = """
(() => {
  const r = window.Runner && Runner.instance_;
  if (!r || !r.tRex || r.crashed) return {ok: false};
  // Automation windows often lose focus; blur pauses the runner.
  r.onVisibilityChange = function() {};
  r.paused = false;
  if (typeof r.loadSounds === "function") {
    try { r.loadSounds(); } catch (e) {}
  }
  if (typeof r.setPlayStatus === "function") r.setPlayStatus(true);
  else r.playing = true;
  // Skip the CSS intro (horizon does not move until startGame).
  if (typeof r.startGame === "function") {
    try { r.startGame(); } catch (e) {}
  }
  r.activated = true;
  r.playingIntro = false;
  if (r.tRex) r.tRex.playingIntro = false;
  r.updatePending = false;
  const now = (typeof performance !== "undefined" && performance.now)
    ? performance.now()
    : Date.now();
  r.time = now - 16;
  if (typeof r.update === "function") r.update();
  if (!r.tRex.jumping && !r.tRex.ducking && typeof r.tRex.startJump === "function") {
    r.tRex.startJump(r.currentSpeed || 6);
  }
  if (typeof r.scheduleNextUpdate === "function") r.scheduleNextUpdate();
  return {ok: true, playing: !!r.playing, distance: r.distanceRan || 0};
})()
"""

JUMP_JS = """
(() => {
  const r = window.Runner && Runner.instance_;
  if (!r || !r.tRex || r.crashed) return;
  if (r.tRex.ducking && typeof r.tRex.setDuck === "function") r.tRex.setDuck(false);
  if (!r.tRex.jumping && typeof r.tRex.startJump === "function") {
    r.tRex.startJump(r.currentSpeed || 6);
  }
})()
"""

DUCK_ON_JS = """
(() => {
  const r = window.Runner && Runner.instance_;
  if (!r || !r.tRex || typeof r.tRex.setDuck !== "function") return;
  r.tRex.setDuck(true);
})()
"""

DUCK_OFF_JS = """
(() => {
  const r = window.Runner && Runner.instance_;
  if (!r || !r.tRex || typeof r.tRex.setDuck !== "function") return;
  r.tRex.setDuck(false);
})()
"""


class DinoGame(Protocol):
    def snapshot(self) -> dict[str, Any]: ...
    def start_run(self) -> None: ...
    def tap_jump(self) -> None: ...
    def set_duck(self, on: bool) -> None: ...
    def resume(self) -> None: ...
    def close(self) -> None: ...


class FakeDinoGame:
    """CI / PRIVATE_DESK_FAKE_RUNNER: a cactus approaches; a jump clears it."""

    def __init__(self) -> None:
        self.x = 220.0
        self.speed = 6.0
        self.distance = 0.0
        self.jumping = False
        self.crashed = False
        self.ducking = False
        self.jumps = 0

    def snapshot(self) -> dict[str, Any]:
        if self.jumping:
            self.x += 40
            self.jumping = False
            if self.x > 180:
                self.x = 220.0
        else:
            self.x -= self.speed * 8
        self.distance += self.speed
        if self.x < 20 and not self.jumping:
            self.crashed = True
        near = None if self.x > 400 else {
            "type": "CACTUS_SMALL",
            "x": self.x,
            "y": 100,
            "width": 17,
        }
        return {
            "ready": True,
            "playing": True,
            "crashed": self.crashed,
            "speed": self.speed,
            "distance": self.distance,
            "grounded": not self.jumping,
            "jumping": self.jumping,
            "ducking": self.ducking,
            "obstacles": [near] if near else [],
            "nearest_type": None if not near else near["type"],
            "nearest_x": None if not near else near["x"],
            "nearest_y": None if not near else near["y"],
        }

    def start_run(self) -> None:
        return

    def tap_jump(self) -> None:
        if not self.jumping:
            self.jumping = True
            self.jumps += 1

    def set_duck(self, on: bool) -> None:
        self.ducking = on

    def resume(self) -> None:
        return

    def close(self) -> None:
        return


class _Cdp:
    def __init__(self, ws_url: str) -> None:
        try:
            from websocket import create_connection
        except ImportError as exc:
            raise RunnerError(
                "runtime_unavailable",
                "websocket-client is not installed. pip install 'private-desk[dino]'.",
            ) from exc
        parsed = urlparse(ws_url)
        origin = f"http://127.0.0.1:{parsed.port}" if parsed.port else "http://127.0.0.1"
        last: Exception | None = None
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                self.ws = create_connection(ws_url, timeout=5, origin=origin)
                break
            except Exception as exc:
                last = exc
                time.sleep(0.2)
        else:
            print(f"cdp websocket failed: {type(last).__name__}", file=sys.stderr)
            raise RunnerError(
                "runtime_unavailable",
                "Could not attach to chrome://dino on loopback CDP.",
            ) from last
        self._n = 0
        self.session_id: str | None = None

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        self._n += 1
        ident = self._n
        payload: dict[str, Any] = {"id": ident, "method": method, "params": params}
        if self.session_id and not method.startswith("Target."):
            payload["sessionId"] = self.session_id
        self.ws.send(json.dumps(payload))
        while True:
            raw = self.ws.recv()
            msg = json.loads(raw)
            if msg.get("id") != ident:
                continue
            if msg.get("error"):
                raise RunnerError("model_error", "Chrome DevTools call failed.")
            return msg.get("result") or {}

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


def wait_for_devtools_ws(profile: Path, timeout_s: float = 20.0) -> str:
    """Browser websocket Chrome wrote to DevToolsActivePort. Loopback IPv4 only."""
    path = profile / "DevToolsActivePort"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            lines = [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]
            port = int(lines[0])
            ws_path = lines[1] if len(lines) > 1 else ""
        except (OSError, ValueError, IndexError):
            time.sleep(0.1)
            continue
        if not (0 < port < 65536) or not ws_path.startswith("/"):
            time.sleep(0.1)
            continue
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=1)
            sock.close()
        except OSError:
            time.sleep(0.1)
            continue
        return f"ws://127.0.0.1:{port}{ws_path}"
    raise RunnerError("runtime_unavailable", "Could not attach to chrome://dino on loopback CDP.")


def loopback_ws_url(ws: str) -> str:
    """Force IPv4 loopback. Chrome often advertises ws://localhost which resolves to ::1."""
    parsed = urlparse(ws)
    if not parsed.port:
        return ws
    return urlunparse(parsed._replace(netloc=f"127.0.0.1:{parsed.port}"))


class ChromeDinoGame:
    def __init__(self, ws_url: str) -> None:
        self.cdp = _Cdp(ws_url)
        self.cdp.session_id = None
        created = self.cdp.call("Target.createTarget", url="chrome://dino")
        target_id = created.get("targetId")
        if not target_id:
            raise RunnerError("runtime_unavailable", "Could not open a chrome://dino tab.")
        self._attach(target_id)
        self._ducking = False
        self._wait_for_runner()
        try:
            self.cdp.call("Page.bringToFront")
        except RunnerError:
            pass
        self._await_run_started()

    def _browser_call(self, method: str, **params: Any) -> dict[str, Any]:
        prev = self.cdp.session_id
        self.cdp.session_id = None
        try:
            return self.cdp.call(method, **params)
        finally:
            self.cdp.session_id = prev

    def _attach(self, target_id: str) -> None:
        attached = self._browser_call("Target.attachToTarget", targetId=target_id, flatten=True)
        self.cdp.session_id = attached.get("sessionId")
        self.cdp.call("Runtime.enable")
        self.cdp.call("Page.enable")

    def _dino_target_id(self) -> str | None:
        infos = self._browser_call("Target.getTargets").get("targetInfos") or []
        for item in infos:
            url = str(item.get("url") or "")
            if item.get("type") == "page" and "dino" in url:
                return str(item.get("targetId") or "") or None
        return None

    def _eval(self, expression: str) -> Any:
        result = self.cdp.call(
            "Runtime.evaluate",
            expression=expression,
            returnByValue=True,
        )
        if result.get("exceptionDetails"):
            print("cdp eval failed", file=sys.stderr)
            return None
        return (result.get("result") or {}).get("value")

    def _wait_for_runner(self) -> None:
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if self._eval(
                "!!(window.Runner && Runner.instance_ && Runner.instance_.tRex)"
            ):
                return
            target_id = self._dino_target_id()
            if target_id:
                self._attach(target_id)
            time.sleep(0.15)
        raise RunnerError("model_error", "chrome://dino did not finish loading.")

    def _press_space(self) -> None:
        for kind in ("rawKeyDown", "keyUp"):
            payload: dict[str, Any] = {
                "type": kind,
                "key": " ",
                "code": "Space",
                "windowsVirtualKeyCode": 32,
                "nativeVirtualKeyCode": 32,
            }
            if kind == "rawKeyDown":
                payload["text"] = " "
            self.cdp.call("Input.dispatchKeyEvent", **payload)
        self._eval(START_JS)

    def start_run(self) -> None:
        self._press_space()

    def _await_run_started(self) -> None:
        deadline = time.time() + 10.0
        while time.time() < deadline:
            snap = self.snapshot()
            if snap.get("ready") and float(snap.get("distance") or 0) > 0:
                self.resume()
                return
            if not snap.get("ready"):
                target_id = self._dino_target_id()
                if target_id:
                    self._attach(target_id)
            self.start_run()
            time.sleep(0.25)
        raise RunnerError("model_error", "chrome://dino stayed on the start screen.")

    def snapshot(self) -> dict[str, Any]:
        value = self._eval(SNAPSHOT_JS)
        if not isinstance(value, dict):
            return {"ready": False}
        return value

    def tap_jump(self) -> None:
        self._eval(JUMP_JS)
        self._ducking = False

    def set_duck(self, on: bool) -> None:
        if on:
            self._eval(DUCK_ON_JS)
            self._ducking = True
        else:
            self._eval(DUCK_OFF_JS)
            self._ducking = False

    def resume(self) -> None:
        try:
            self.cdp.call("Page.bringToFront")
        except RunnerError:
            pass
        self._eval(RESUME_JS)

    def close(self) -> None:
        self.set_duck(False)
        self.cdp.close()
