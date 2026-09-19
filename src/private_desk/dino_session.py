"""Jev plays chrome://dino. Holo is not in this loop."""

from __future__ import annotations

import os
import time
from typing import Any

from private_desk import jobs
from private_desk.config import Config, typesafe_api_key
from private_desk.dino_cdp import ChromeDinoGame, DinoGame, FakeDinoGame, wait_for_devtools_ws
from private_desk.jev.client import JevUnavailable, TypeSafeJevClient
from private_desk.jev.dino import jev_dino_buttons, scripted_dino_buttons
from private_desk.kinds import Kind
from private_desk.launch import (
    close_dino_browser,
    dino_profile_dir,
    is_chromium_app,
    open_dino_chrome,
)
from private_desk.runners import RunnerError, artifact_dir_for, artifacts_payload

CLEAR_DISTANCE = 80.0
TICK_S = 0.08


def _cancelled(job: dict[str, Any]) -> bool:
    if jobs.cancel_path(job["job_id"]).is_file():
        return True
    current = jobs.load_job(job["job_id"])
    return bool(current and current.get("state") == "cancelled")


def _play(job: dict[str, Any], kind: Kind, game: DinoGame, decide) -> dict[str, Any]:
    ducking = False
    jumps = 0
    last: dict[str, Any] = {}
    deadline = time.time() + kind.max_time_s
    for n in range(1, kind.max_steps + 1):
        if _cancelled(job):
            raise RunnerError("cancelled", "Job cancelled.")
        if time.time() > deadline:
            raise RunnerError("timeout", "Hit max_time_s.")
        snap = game.snapshot()
        last = snap
        job["step"] = {
            "id": "playing",
            "label": "Playing chrome://dino",
            "n": n,
            "of": kind.max_steps,
        }
        jobs.write_job(job)
        jobs.heartbeat(job)
        if not snap.get("ready"):
            game.start_run()
            game.resume()
            time.sleep(0.15)
            continue
        if float(snap.get("distance") or 0) < 1 and not snap.get("crashed"):
            game.start_run()
            game.resume()
            time.sleep(TICK_S)
            continue
        if snap.get("crashed"):
            dist = float(snap.get("distance") or 0)
            if dist >= CLEAR_DISTANCE:
                return {"distance": dist, "jumps": jumps, "cleared": True, "crashed": True}
            raise RunnerError("model_error", "Dino crashed before clearing the first obstacles.")
        buttons = decide(snap)
        if buttons.jump:
            game.tap_jump()
            jumps += 1
            if ducking:
                game.set_duck(False)
                ducking = False
        elif buttons.duck:
            game.set_duck(True)
            ducking = True
        elif ducking:
            game.set_duck(False)
            ducking = False
        game.resume()
        time.sleep(TICK_S)
        dist = float(snap.get("distance") or 0)
        if dist >= CLEAR_DISTANCE:
            return {"distance": dist, "jumps": jumps, "cleared": True, "crashed": False}
    dist = float(last.get("distance") or 0)
    if dist >= CLEAR_DISTANCE:
        return {"distance": dist, "jumps": jumps, "cleared": True, "crashed": False}
    raise RunnerError("timeout", "Hit max_steps before clearing chrome://dino.")


def run_dino(job: dict[str, Any], kind: Kind, cfg: Config, params: dict[str, Any]) -> dict[str, Any]:
    fake = os.environ.get("PRIVATE_DESK_FAKE_RUNNER")
    artifact_dir = artifact_dir_for(kind, cfg, params)
    if fake:
        game: DinoGame = FakeDinoGame()
        _play(job, kind, game, scripted_dino_buttons)
        game.close()
        (artifact_dir / "run.json").write_text("{}\n")
        return artifacts_payload(artifact_dir, ["run.json"])

    browser = (cfg.browser or "").strip()
    if not is_chromium_app(browser):
        raise RunnerError(
            "kind_denied",
            'demo_dino needs a Chromium browser. private-desk setup --browser "Google Chrome"',
        )
    key = typesafe_api_key(cfg)
    if not key:
        raise RunnerError("jev_unavailable", "TypeSafe API key is not configured.")
    client = TypeSafeJevClient(key)
    game = None
    try:
        open_dino_chrome(browser)
        ws = wait_for_devtools_ws(dino_profile_dir())
        game = ChromeDinoGame(ws)
        _play(job, kind, game, lambda snap: jev_dino_buttons(client, snap))
        (artifact_dir / "run.json").write_text("{}\n")
        return artifacts_payload(artifact_dir, ["run.json"])
    except JevUnavailable as exc:
        raise RunnerError("jev_unavailable", exc.message) from exc
    finally:
        if game is not None:
            game.close()
        close_dino_browser()
