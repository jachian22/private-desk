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


def _on_instance(body: str) -> str:
    return "function() {\n  const r = this;\n" + body + "\n}"


def _on_window(body: str) -> str:
    return (
        "(() => {\n"
        "  const w = (typeof document !== 'undefined' && document.defaultView) || window;\n"
        "  const r = w.Runner && (w.Runner.instance_\n"
        "    || (typeof w.Runner.getInstance === 'function' && w.Runner.getInstance()));\n"
        + body
        + "\n})()"
    )


def handler_object_ids(payload: dict[str, Any]) -> list[str]:
    """CDP DOMDebugger.getEventListeners → handler objectIds (Runner is one of them)."""
    out: list[str] = []
    for listener in payload.get("listeners") or []:
        if not isinstance(listener, dict):
            continue
        handler = listener.get("handler") or {}
        if not isinstance(handler, dict):
            continue
        oid = handler.get("objectId")
        if isinstance(oid, str) and oid:
            out.append(oid)
    return out


# Current Chrome intern is an ES module: no window.Runner. The instance is
# document's keydown listener (startListening adds the Runner itself).
_PICK_RUNNER = """
  const R = w.Runner;
  if (!R) return false;
  let inst = R.instance_ || (typeof R.getInstance === 'function' ? R.getInstance() : null);
  if (!inst && typeof R === 'function') {
    try { inst = new R('.interstitial-wrapper'); } catch (e) {}
  }
  return !!(inst && inst.tRex);
"""

RUNNER_READY_JS = _on_window(_PICK_RUNNER)
INSTANCE_IS_RUNNER_JS = "function() { return !!(this && this.tRex); }"

FIND_RUNNER_CLI_JS = """
(() => {
  if (typeof getEventListeners !== 'function') return null;
  const nodes = [document];
  if (typeof window !== 'undefined') nodes.push(window);
  const canvas = document.querySelector('canvas');
  const wrap = document.querySelector('.interstitial-wrapper');
  if (canvas) nodes.push(canvas);
  if (wrap) nodes.push(wrap);
  for (const node of nodes) {
    if (!node) continue;
    const map = getEventListeners(node) || {};
    for (const list of Object.values(map)) {
      for (const item of list || []) {
        const listener = item && item.listener;
        if (listener && listener.tRex) return listener;
      }
    }
  }
  return null;
})()
"""

PROBE_JS = """
(() => {
  const w = (typeof document !== 'undefined' && document.defaultView) || window;
  return {
    href: String(w.location.href),
    runner: typeof w.Runner,
    instance: !!(w.Runner && (w.Runner.instance_ || (typeof w.Runner.getInstance === 'function' && w.Runner.getInstance()))),
    canvas: document.querySelectorAll('canvas').length,
    wrap: !!document.querySelector('.interstitial-wrapper'),
    scripts: document.scripts.length,
  };
})()
"""


def is_dino_url(url: str) -> bool:
    blob = (url or "").lower()
    return any(part in blob for part in ("dino", "chromewebdata", "neterror", "offline"))


def prefer_page_targets(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer a tab whose URL is dino; among the rest, try newer tabs first.

    Chrome starts on about:blank and often opens chrome://dino in a *second* tab.
    getTargets lists the blank first; reversing the non-dino pages tries that new tab.
    """
    dino: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for item in pages:
        if is_dino_url(str(item.get("url") or "")):
            dino.append(item)
        else:
            rest.append(item)
    rest.reverse()
    return dino + rest


_SNAPSHOT_BODY = """
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
  const raw = r.distanceRan || 0;
  // Intern scoreboard is distanceRan * 0.025. Raw 80 is a score of 2.
  const score = (r.distanceMeter && typeof r.distanceMeter.getActualDistance === 'function')
    ? r.distanceMeter.getActualDistance(raw)
    : Math.round(raw * 0.025);
  const out = {
    ready: true,
    crashed: !!r.crashed,
    speed: r.currentSpeed,
    distance: score,
    grounded: !!(r.tRex && !r.tRex.jumping),
    jumping: !!(r.tRex && r.tRex.jumping),
    ducking: !!(r.tRex && r.tRex.ducking),
    obstacles: obs.slice(0, 4),
    nearest_type: near ? near.type : null,
    nearest_x: near ? near.x : null,
    nearest_y: near ? near.y : null,
    nearest_width: near ? near.width : null,
    started: !!(r.playing || r.activated || raw > 0),
    runningTime: r.runningTime || 0,
    playing: !!(r.activated || r.playing || raw > 0),
  };
  return out;
"""

SNAPSHOT_JS = _on_instance(_SNAPSHOT_BODY)
SNAPSHOT_WINDOW_JS = _on_window(_SNAPSHOT_BODY)

# Place the 600x150 world from the left-top so T-Rex (x≈0) stays in the tab.
# Intern arcade: transform-origin top center, margin:auto, transition 400ms
# (that delay is why layout logs identity, then T-Rex clips on the left).
_PLACE_ARCADE = """
  if (!document.getElementById('pd-dino-place')) {
    const sheet = document.createElement('style');
    sheet.id = 'pd-dino-place';
    sheet.textContent = [
      '.arcade-mode .runner-container {',
      '  margin: 0 !important; left: 0 !important; right: auto !important;',
      '  transform-origin: left top !important; transition: none !important;',
      '  overflow: visible !important;',
      '}',
      '.arcade-mode .interstitial-wrapper {',
      '  overflow: visible !important; padding: 0 !important; margin: 0 !important;',
      '}',
      '.arcade-mode, .arcade-mode .runner-canvas { overflow: visible !important; }',
    ].join(' ');
    document.documentElement.appendChild(sheet);
  }
  const el = (r && r.containerEl) || document.querySelector('.runner-container');
  const wrap = document.querySelector('.interstitial-wrapper');
  if (wrap) {
    wrap.style.padding = '0';
    wrap.style.margin = '0';
    wrap.style.overflow = 'visible';
  }
  if (document.body) document.body.style.overflow = 'visible';
  function pdPlace(node) {
    if (!node) return;
    node.style.webkitAnimation = '';
    node.style.animation = '';
    node.style.transition = 'none';
    node.style.width = '600px';
    node.style.height = '150px';
    node.style.margin = '0';
    node.style.left = '0';
    node.style.right = 'auto';
    const padL = 48, padT = 24, padR = 48, padB = 24;
    const scale = Math.max(1, Math.min(
      (window.innerWidth - padL - padR) / 600,
      (window.innerHeight - padT - padB) / 150
    ));
    node.style.transformOrigin = 'left top';
    node.style.transform = 'translate(' + padL + 'px,' + padT + 'px) scale(' + scale + ')';
  }
  pdPlace(el);
  if (r) {
    r.setArcadeModeContainerScale = function() {
      pdPlace(r.containerEl || document.querySelector('.runner-container'));
    };
    if (!r._pdArcadeHook && typeof r.adjustDimensions === 'function') {
      const origAdj = r.adjustDimensions.bind(r);
      r.adjustDimensions = function() {
        origAdj();
        pdPlace(r.containerEl || document.querySelector('.runner-container'));
      };
      r._pdArcadeHook = true;
    }
  }
"""

_RESUME_BODY = """
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
""" + _PLACE_ARCADE + """
"""

RESUME_JS = _on_instance(_RESUME_BODY)
RESUME_WINDOW_JS = _on_window(_RESUME_BODY)

_START_BODY = """
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
  if (r.dimensions) {
    r.dimensions.WIDTH = 600;
    r.dimensions.HEIGHT = 150;
  }
""" + _PLACE_ARCADE + """
  r.activated = true;
  r.playingIntro = false;
  if (r.tRex) r.tRex.playingIntro = false;
  r.updatePending = false;
  const now = (typeof performance !== "undefined" && performance.now)
    ? performance.now()
    : Date.now();
  r.time = now - 16;
  if (typeof r.update === "function") r.update();
  if (typeof r.scheduleNextUpdate === "function") r.scheduleNextUpdate();
  return {ok: true, playing: !!r.playing, distance: r.distanceRan || 0};
"""

START_JS = _on_instance(_START_BODY)
START_WINDOW_JS = _on_window(_START_BODY)

_JUMP_BODY = """
  if (!r || !r.tRex || r.crashed) return;
  if (r.tRex.ducking && typeof r.tRex.setDuck === "function") r.tRex.setDuck(false);
  if (!r.tRex.jumping && typeof r.tRex.startJump === "function") {
    r.tRex.startJump(r.currentSpeed || 6);
  }
"""

JUMP_JS = _on_instance(_JUMP_BODY)
JUMP_WINDOW_JS = _on_window(_JUMP_BODY)

_DUCK_ON_BODY = """
  if (!r || !r.tRex || typeof r.tRex.setDuck !== "function") return;
  r.tRex.setDuck(true);
"""

DUCK_ON_JS = _on_instance(_DUCK_ON_BODY)
DUCK_ON_WINDOW_JS = _on_window(_DUCK_ON_BODY)

_DUCK_OFF_BODY = """
  if (!r || !r.tRex || typeof r.tRex.setDuck !== "function") return;
  r.tRex.setDuck(false);
"""

DUCK_OFF_JS = _on_instance(_DUCK_OFF_BODY)
DUCK_OFF_WINDOW_JS = _on_window(_DUCK_OFF_BODY)

_HOLD_BODY = """
  if (!r) return;
  r.paused = true;
  if (typeof r.setPlayStatus === "function") r.setPlayStatus(false);
  else r.playing = false;
  r.updatePending = false;
"""

HOLD_JS = _on_instance(_HOLD_BODY)
HOLD_WINDOW_JS = _on_window(_HOLD_BODY)

# chrome://dino is arcade-mode. Intro CSS leaves the runner at T-Rex width (44px);
# then arcade scales that sliver. Force the real 600x150 world, then place it.
LAYOUT_RESET_JS = """
function() {
  const r = this;
  if (r && r.dimensions) {
    r.dimensions.WIDTH = 600;
    r.dimensions.HEIGHT = 150;
  }
""" + _PLACE_ARCADE + """
  const canvas = (r && r.canvas) || document.querySelector('canvas');
  const runner = (r && r.containerEl) || document.querySelector('.runner-container');
  const rs = runner ? getComputedStyle(runner) : null;
  const box = runner ? runner.getBoundingClientRect() : null;
  return {
    dim: r && r.dimensions,
    canvas: canvas && {attrW: canvas.width, attrH: canvas.height, cssW: canvas.clientWidth, cssH: canvas.clientHeight},
    runner: runner && {w: runner.clientWidth, h: runner.clientHeight, transform: rs && rs.transform, origin: rs && rs.transformOrigin},
    rect: box && {x: box.x, y: box.y, w: box.width, h: box.height, right: box.right},
    arcade: !!(document.body && document.body.classList.contains('arcade-mode')),
    inner: {w: window.innerWidth, h: window.innerHeight},
  };
}
"""

LAYOUT_RESET_WINDOW_JS = """
(() => {
  const r = (typeof window !== 'undefined' && window.Runner && (window.Runner.instance_
    || (typeof window.Runner.getInstance === 'function' && window.Runner.getInstance()))) || null;
  if (r && r.dimensions) {
    r.dimensions.WIDTH = 600;
    r.dimensions.HEIGHT = 150;
  }
""" + _PLACE_ARCADE + """
  const canvas = document.querySelector('canvas');
  const runner = document.querySelector('.runner-container');
  const rs = runner ? getComputedStyle(runner) : null;
  return {
    dim: r && r.dimensions,
    canvas: canvas && {attrW: canvas.width, attrH: canvas.height, cssW: canvas.clientWidth, cssH: canvas.clientHeight},
    runner: runner && {w: runner.clientWidth, h: runner.clientHeight, transform: rs && rs.transform},
    arcade: !!(document.body && document.body.classList.contains('arcade-mode')),
    inner: {w: window.innerWidth, h: window.innerHeight},
  };
})()
"""


class DinoGame(Protocol):
    def snapshot(self) -> dict[str, Any]: ...
    def start_run(self) -> None: ...
    def tap_jump(self) -> None: ...
    def set_duck(self, on: bool) -> None: ...
    def resume(self) -> None: ...
    def hold(self) -> None: ...
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

    def hold(self) -> None:
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
        self._contexts: dict[int, str | None] = {}

    def _handle_event(self, msg: dict[str, Any]) -> None:
        method = msg.get("method")
        params = msg.get("params") or {}
        sid = msg.get("sessionId")
        if method == "Runtime.executionContextCreated":
            ctx = params.get("context") or {}
            cid = ctx.get("id")
            if cid is not None:
                self._contexts[int(cid)] = sid
        elif method == "Runtime.executionContextDestroyed":
            cid = params.get("executionContextId")
            if cid is not None:
                self._contexts.pop(int(cid), None)
        elif method == "Runtime.executionContextsCleared":
            drop = [cid for cid, owner in self._contexts.items() if owner == sid]
            for cid in drop:
                self._contexts.pop(cid, None)

    def _read_msg(self) -> dict[str, Any]:
        return json.loads(self.ws.recv())

    def drain_events(self, wait_s: float = 0.15) -> None:
        self.ws.settimeout(max(wait_s, 0.05))
        deadline = time.time() + wait_s
        try:
            while time.time() < deadline:
                try:
                    msg = self._read_msg()
                except Exception:
                    break
                if msg.get("id") is None:
                    self._handle_event(msg)
        finally:
            self.ws.settimeout(5)

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        self._n += 1
        ident = self._n
        payload: dict[str, Any] = {"id": ident, "method": method, "params": params}
        if self.session_id and not method.startswith("Target."):
            payload["sessionId"] = self.session_id
        self.ws.send(json.dumps(payload))
        while True:
            msg = self._read_msg()
            if msg.get("id") is None:
                self._handle_event(msg)
                continue
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
        self._ducking = False
        self._runner_oid: str | None = None
        self._open_dino_page()
        self._wait_for_runner()
        try:
            self.cdp.call("Page.bringToFront")
        except RunnerError:
            pass
        self._await_run_started()
        self._reset_layout()

    def _browser_call(self, method: str, **params: Any) -> dict[str, Any]:
        prev = self.cdp.session_id
        self.cdp.session_id = None
        try:
            return self.cdp.call(method, **params)
        finally:
            self.cdp.session_id = prev

    def _page_targets(self) -> list[dict[str, Any]]:
        try:
            infos = self._browser_call("Target.getTargets").get("targetInfos") or []
        except RunnerError:
            return []
        return [item for item in infos if item.get("type") in {"page", "iframe", "webview"}]

    def _attach(self, target_id: str) -> None:
        attached = self._browser_call("Target.attachToTarget", targetId=target_id, flatten=True)
        self.cdp.session_id = attached.get("sessionId")
        self.cdp.call("Runtime.enable")
        self.cdp.call("Page.enable")
        self.cdp.drain_events()

    def _try_attach(self, target_id: str) -> bool:
        try:
            self._attach(target_id)
            return True
        except RunnerError:
            return False

    def _dino_target_id(self) -> str | None:
        for item in self._page_targets():
            if is_dino_url(str(item.get("url") or "")):
                return str(item.get("targetId") or "") or None
        return None

    def _eval(self, expression: str, *, context_id: int | None = None) -> Any:
        params: dict[str, Any] = {
            "expression": expression,
            "returnByValue": True,
        }
        if context_id is not None:
            params["contextId"] = context_id
        try:
            result = self.cdp.call("Runtime.evaluate", **params)
        except RunnerError:
            return None
        if result.get("exceptionDetails"):
            return None
        return (result.get("result") or {}).get("value")

    def _eval_remote(self, expression: str, *, include_cli: bool = False) -> str | None:
        params: dict[str, Any] = {"expression": expression, "returnByValue": False}
        if include_cli:
            params["includeCommandLineAPI"] = True
        try:
            result = self.cdp.call("Runtime.evaluate", **params)
        except RunnerError:
            return None
        if result.get("exceptionDetails"):
            return None
        remote = result.get("result") or {}
        if remote.get("subtype") == "null":
            return None
        oid = remote.get("objectId")
        return str(oid) if oid else None

    def _eval_on_document(self, expression: str) -> Any:
        """Run in the intern's window. Default Runtime.evaluate can miss page JS on chrome-error://."""
        try:
            doc = self.cdp.call("Runtime.evaluate", expression="document", returnByValue=False)
        except RunnerError:
            return None
        object_id = (doc.get("result") or {}).get("objectId")
        if not object_id:
            return None
        fn = "function() { return (" + expression + "); }"
        ok, value = self._call_on(str(object_id), fn)
        return value if ok else None

    def _eval_anywhere(self, expression: str) -> Any:
        last = self._eval_on_document(expression)
        if last is True:
            return last
        if isinstance(last, dict) and (
            last.get("ready") or last.get("ok") or last.get("instance") or last.get("canvas") or last.get("wrap")
        ):
            return last
        ids: list[int | None] = [None]
        ids.extend(
            cid
            for cid, sid in self.cdp._contexts.items()
            if sid in (None, self.cdp.session_id)
        )
        for cid in ids:
            value = self._eval(expression) if cid is None else self._eval(expression, context_id=cid)
            last = value if value is not None else last
            if last is True:
                return last
            if isinstance(last, dict) and (
                last.get("ready") or last.get("ok") or last.get("instance") or last.get("canvas") or last.get("wrap")
            ):
                return last
        return last

    def _call_on(self, object_id: str, function_declaration: str) -> tuple[bool, Any]:
        try:
            result = self.cdp.call(
                "Runtime.callFunctionOn",
                objectId=object_id,
                functionDeclaration=function_declaration,
                returnByValue=True,
            )
        except RunnerError:
            return False, None
        if result.get("exceptionDetails"):
            return False, None
        return True, (result.get("result") or {}).get("value")

    def _listener_ids(self, object_id: str) -> list[str]:
        try:
            payload = self.cdp.call("DOMDebugger.getEventListeners", objectId=object_id)
        except RunnerError:
            return []
        return handler_object_ids(payload)

    def _dom_resolve(self, selector: str | None = None) -> str | None:
        try:
            tree = self.cdp.call("DOM.getDocument", depth=0, pierce=True)
        except RunnerError:
            return None
        node_id = (tree.get("root") or {}).get("nodeId")
        if not node_id:
            return None
        if selector:
            try:
                found = self.cdp.call("DOM.querySelector", nodeId=node_id, selector=selector)
            except RunnerError:
                return None
            node_id = found.get("nodeId")
            if not node_id:
                return None
        try:
            remote = self.cdp.call("DOM.resolveNode", nodeId=node_id)
        except RunnerError:
            return None
        oid = (remote.get("object") or {}).get("objectId")
        return str(oid) if oid else None

    def _node_object_ids(self) -> list[str]:
        ids: list[str] = []
        seen: set[str] = set()
        for oid in (
            self._eval_remote("document"),
            self._eval_remote("window"),
            self._eval_remote("document.querySelector('canvas')"),
            self._eval_remote("document.querySelector('.interstitial-wrapper')"),
            self._dom_resolve(),
            self._dom_resolve("canvas"),
            self._dom_resolve(".interstitial-wrapper"),
        ):
            if oid and oid not in seen:
                seen.add(oid)
                ids.append(oid)
        return ids

    def _oid_is_runner(self, oid: str) -> bool:
        ok, value = self._call_on(oid, INSTANCE_IS_RUNNER_JS)
        return bool(ok and value)

    def _resolve_runner(self) -> str | None:
        if self._runner_oid and self._oid_is_runner(self._runner_oid):
            return self._runner_oid
        self._runner_oid = None
        seen: set[str] = set()
        for node_id in self._node_object_ids():
            for oid in self._listener_ids(node_id):
                if oid in seen:
                    continue
                seen.add(oid)
                if self._oid_is_runner(oid):
                    self._runner_oid = oid
                    return oid
        cli = self._eval_remote(FIND_RUNNER_CLI_JS, include_cli=True)
        if cli and self._oid_is_runner(cli):
            self._runner_oid = cli
            return cli
        return None

    def _with_runner(self, instance_js: str, window_js: str) -> Any:
        oid = self._runner_oid
        if oid:
            ok, value = self._call_on(oid, instance_js)
            if ok:
                return value
            self._runner_oid = None
        oid = self._resolve_runner()
        if oid:
            ok, value = self._call_on(oid, instance_js)
            if ok:
                return value
        return self._eval_anywhere(window_js)

    def _runner_ready(self) -> bool:
        if self._resolve_runner():
            return True
        return bool(self._eval_anywhere(RUNNER_READY_JS))

    def _close_extra_pages(self, keep: str) -> None:
        for item in self._page_targets():
            tid = str(item.get("targetId") or "")
            url = str(item.get("url") or "")
            if not tid or tid == keep:
                continue
            if item.get("type") != "page":
                continue
            if is_dino_url(url):
                continue
            try:
                self._browser_call("Target.closeTarget", targetId=tid)
            except RunnerError:
                continue

    def _open_dino_page(self) -> None:
        deadline = time.time() + 8.0
        dino_id = ""
        while time.time() < deadline and not dino_id:
            pages = prefer_page_targets(self._page_targets())
            dino_id = next(
                (
                    str(item.get("targetId") or "")
                    for item in pages
                    if is_dino_url(str(item.get("url") or ""))
                ),
                "",
            )
            if dino_id:
                break
            time.sleep(0.15)
        if not dino_id:
            created = self._browser_call("Target.createTarget", url="chrome://dino/")
            dino_id = str(created.get("targetId") or "") or ""
        if not dino_id:
            raise RunnerError("runtime_unavailable", "Could not open a chrome://dino tab.")
        if not self._try_attach(dino_id):
            raise RunnerError("runtime_unavailable", "Could not attach to chrome://dino on loopback CDP.")
        self._close_extra_pages(dino_id)

    def _wait_for_runner(self) -> None:
        deadline = time.time() + 20.0
        last_note = 0.0
        while time.time() < deadline:
            pages = prefer_page_targets(self._page_targets())
            probes: list[Any] = []
            for item in pages:
                tid = str(item.get("targetId") or "")
                if not tid or not self._try_attach(tid):
                    continue
                probe = self._eval_anywhere(PROBE_JS)
                probes.append(probe)
                if self._runner_ready():
                    try:
                        self.cdp.call("Page.bringToFront")
                    except RunnerError:
                        pass
                    return
            if time.time() - last_note >= 1.0:
                found = "yes" if self._runner_oid else "no"
                print(f"dino tabs={probes!r} runner_oid={found}", file=sys.stderr)
                last_note = time.time()
            time.sleep(0.15)
        raise RunnerError("model_error", "chrome://dino did not finish loading.")

    def _press_space(self) -> None:
        # Space also jumps. startGame() is enough to leave the title screen.
        self._with_runner(START_JS, START_WINDOW_JS)

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
                for item in prefer_page_targets(self._page_targets()):
                    tid = str(item.get("targetId") or "")
                    if tid and self._try_attach(tid) and self._runner_ready():
                        break
            self.start_run()
            time.sleep(0.25)
        raise RunnerError("model_error", "chrome://dino stayed on the start screen.")

    def snapshot(self) -> dict[str, Any]:
        value = self._with_runner(SNAPSHOT_JS, SNAPSHOT_WINDOW_JS)
        if not isinstance(value, dict):
            return {"ready": False}
        return value

    def tap_jump(self) -> None:
        self._with_runner(JUMP_JS, JUMP_WINDOW_JS)
        self._ducking = False

    def set_duck(self, on: bool) -> None:
        if on:
            self._with_runner(DUCK_ON_JS, DUCK_ON_WINDOW_JS)
            self._ducking = True
        else:
            self._with_runner(DUCK_OFF_JS, DUCK_OFF_WINDOW_JS)
            self._ducking = False

    def resume(self) -> None:
        try:
            self.cdp.call("Page.bringToFront")
        except RunnerError:
            pass
        self._with_runner(RESUME_JS, RESUME_WINDOW_JS)

    def _reset_layout(self) -> None:
        layout = self._with_runner(LAYOUT_RESET_JS, LAYOUT_RESET_WINDOW_JS)
        print(f"dino layout={layout!r}", file=sys.stderr)

    def hold(self) -> None:
        deadline = time.time() + 2.5
        while time.time() < deadline:
            snap = self.snapshot()
            if snap.get("crashed") or not snap.get("jumping"):
                break
            time.sleep(0.05)
        self._with_runner(HOLD_JS, HOLD_WINDOW_JS)

    def close(self) -> None:
        self.set_duck(False)
        self.cdp.close()
