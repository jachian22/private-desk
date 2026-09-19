"""Jev questions for chrome://dino. No pixels. Threshold 0.5."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Protocol

from private_desk.jev.client import JevUnavailable, _noul_of

NOUL_THRESHOLD = 0.5
# Intern nearest_x: cactus spawns ~600. Jump window is much closer.
# Asking from spawn burned Gateway and jumped into empty space (gw10).
JEV_ASK_X = 220.0
# If evaluate 429s inside this band, jump locally so the cactus is not free.
JEV_SAVE_X = 180.0

DINO_QUESTIONS = {
    "jump": {
        "type": "noul",
        "instructions": (
            "Should T-Rex jump this frame? State has nearest_type, nearest_x "
            "(pixels ahead), nearest_width, speed, grounded, jumping. "
            "True only if a jump this frame is how we clear the nearest obstacle. "
            "False if already jumping, or if a duck is the right move."
        ),
    },
    "duck": {
        "type": "noul",
        "instructions": (
            "Should T-Rex duck this frame? True only for a high bird. "
            "False for cacti."
        ),
    },
}


@dataclass
class DinoButtons:
    jump: bool
    duck: bool
    jump_noul: float
    duck_noul: float


def public_dino_state(raw: dict[str, Any]) -> dict[str, Any]:
    """Strip anything that is not numbers/enums. Never images."""
    obstacles = []
    for item in (raw.get("obstacles") or [])[:4]:
        if not isinstance(item, dict):
            continue
        obstacles.append(
            {
                "type": str(item.get("type") or "UNKNOWN"),
                "x": item.get("x"),
                "y": item.get("y"),
                "width": item.get("width"),
            }
        )
    speed = float(raw.get("speed") or 0)
    nearest_x = raw.get("nearest_x")
    eta = None
    if nearest_x is not None and speed > 0:
        eta = float(nearest_x) / speed
    started = bool(raw.get("playing")) or bool(raw.get("started")) or float(raw.get("distance") or 0) > 0
    return {
        "playing": started,
        "crashed": bool(raw.get("crashed")),
        "speed": speed,
        "distance": raw.get("distance"),
        "grounded": bool(raw.get("grounded")),
        "jumping": bool(raw.get("jumping")),
        "ducking": bool(raw.get("ducking")),
        "nearest_type": raw.get("nearest_type"),
        "nearest_x": nearest_x,
        "nearest_y": raw.get("nearest_y"),
        "eta_frames": eta,
        "obstacles": obstacles,
    }


def mix_dino(jump_noul: float, duck_noul: float, *, grounded: bool) -> DinoButtons:
    jump = jump_noul >= NOUL_THRESHOLD and grounded
    duck = duck_noul >= NOUL_THRESHOLD and not jump
    return DinoButtons(jump=jump, duck=duck, jump_noul=jump_noul, duck_noul=duck_noul)


def obstacle_on_screen(state: dict[str, Any]) -> bool:
    if state.get("nearest_x") is not None:
        return True
    return bool(state.get("obstacles"))


def _nearest_x(state: dict[str, Any]) -> float | None:
    raw = state.get("nearest_x")
    if raw is None:
        return None
    return float(raw)


def _is_bird(state: dict[str, Any]) -> bool:
    return "PTERO" in str(state.get("nearest_type") or "").upper()


def should_ask_jev(state: dict[str, Any]) -> bool:
    if bool(state.get("jumping")):
        return False
    x = _nearest_x(state)
    if x is None:
        return False
    return x <= JEV_ASK_X


def close_enough_to_save(state: dict[str, Any]) -> bool:
    if not bool(state.get("grounded")) or _is_bird(state):
        return False
    x = _nearest_x(state)
    return x is not None and x <= JEV_SAVE_X


def scripted_dino_buttons(state: dict[str, Any]) -> DinoButtons:
    """Jump when a ground obstacle is close; duck high birds. No API."""
    grounded = bool(state.get("grounded"))
    speed = float(state.get("speed") or 6)
    nearest_x = state.get("nearest_x")
    kind = str(state.get("nearest_type") or "")
    y = state.get("nearest_y")
    jump_n = 0.1
    duck_n = 0.1
    if nearest_x is not None:
        horizon = 70 + speed * 12
        close = float(nearest_x) < horizon
        bird_high = "PTERODACTYL" in kind.upper() and y is not None and float(y) < 75
        if bird_high and close:
            duck_n = 0.9
        elif close and grounded:
            jump_n = 0.9
    return mix_dino(jump_n, duck_n, grounded=grounded)


class DinoJev(Protocol):
    def ask_response(self, state: dict[str, Any], questions: dict[str, Any]) -> Any: ...


def jev_dino_buttons(client: DinoJev, state: dict[str, Any]) -> DinoButtons:
    public = public_dino_state(state)
    response = client.ask_response(public, DINO_QUESTIONS)
    jump = _noul_of(response, "jump")
    duck = _noul_of(response, "duck")
    return mix_dino(jump, duck, grounded=bool(public.get("grounded")))


def live_dino_buttons(client: DinoJev, state: dict[str, Any]) -> DinoButtons:
    """Ask Jev in the close band. Airborne/far ticks skip. 429 near a cactus jumps locally."""
    grounded = bool(state.get("grounded"))
    idle = mix_dino(0.1, 0.1, grounded=grounded)
    if not obstacle_on_screen(state):
        return idle
    if not should_ask_jev(state):
        print(
            f"dino jev skip jumping={bool(state.get('jumping'))} "
            f"nearest_x={state.get('nearest_x')} type={state.get('nearest_type')}",
            file=sys.stderr,
        )
        return idle
    last_exc: JevUnavailable | None = None
    for _ in range(2):
        try:
            buttons = jev_dino_buttons(client, state)
            print(
                f"dino jev noul_jump={buttons.jump_noul:.2f} noul_duck={buttons.duck_noul:.2f} "
                f"do_jump={buttons.jump} grounded={grounded} jumping={bool(state.get('jumping'))} "
                f"nearest_x={state.get('nearest_x')} type={state.get('nearest_type')}",
                file=sys.stderr,
            )
            return buttons
        except JevUnavailable as exc:
            last_exc = exc
    if close_enough_to_save(state):
        buttons = scripted_dino_buttons(state)
        print(
            f"dino jev failed {last_exc.message if last_exc else 'unavailable'} "
            f"save jump={buttons.jump} nearest_x={state.get('nearest_x')}",
            file=sys.stderr,
        )
        return buttons
    print(
        f"dino jev failed {last_exc.message if last_exc else 'unavailable'} "
        f"nearest_x={state.get('nearest_x')}",
        file=sys.stderr,
    )
    return idle
