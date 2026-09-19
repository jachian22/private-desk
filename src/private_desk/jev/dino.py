"""Jev questions for chrome://dino. No pixels. Threshold 0.5."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from private_desk.jev.client import TypeSafeJevClient, _noul_of

NOUL_THRESHOLD = 0.5

DINO_QUESTIONS = {
    "jump": {
        "type": "noul",
        "instructions": (
            "Jump now. True if grounded and a cactus (or low obstacle) is close "
            "enough that waiting will hit it. False if airborne, too far, or ducking is better."
        ),
    },
    "duck": {
        "type": "noul",
        "instructions": (
            "Duck now. True if a high pterodactyl is on a collision path. "
            "False for cacti or when a jump is the right move."
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
    return {
        "playing": bool(raw.get("playing")),
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


def jev_dino_buttons(client: TypeSafeJevClient, state: dict[str, Any]) -> DinoButtons:
    public = public_dino_state(state)
    response = client.ask_response(public, DINO_QUESTIONS)
    jump = _noul_of(response, "jump")
    duck = _noul_of(response, "duck")
    return mix_dino(jump, duck, grounded=bool(public.get("grounded")))
