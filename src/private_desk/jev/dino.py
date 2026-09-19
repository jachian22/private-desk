"""Jev questions for chrome://dino. No pixels. Threshold 0.5."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Protocol

from private_desk.jev.client import JevUnavailable, _noul_of

NOUL_THRESHOLD = 0.5
# Live intern: Jev RTT lets a cactus close ~200px. Do not wait on Jev inside this band.
REFLEX_X = 260.0
# Optional early Jev ask outside the reflex band.
JEV_ASK_X = 400.0
# High birds: duck as soon as they enter the ask band. Do not wait on Jev.
BIRD_REFLEX_X = 400.0
JEV_SAVE_X = 180.0
LATE_JUMP_X = 140.0
LATE_JUMP_NOUL = 0.40
LATE_JUMP_LARGE_EXTRA = 40.0

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
    # Live intern is not frozen. A Gateway round-trip closes ~200px, which is
    # how gw18–gw20 died (ask at 350, discard the hop, cactus arrives first).
    # Reflex handles jump/duck; Jev can come back once we freeze during asks.
    del state
    return False


def bird_is_high(state: dict[str, Any]) -> bool:
    y = state.get("nearest_y")
    if y is None:
        return True
    try:
        return float(y) < 75
    except (TypeError, ValueError):
        return True


def cactus_is_imminent(state: dict[str, Any]) -> bool:
    if bool(state.get("jumping")) or not bool(state.get("grounded")) or _is_bird(state):
        return False
    x = _nearest_x(state)
    return x is not None and x <= REFLEX_X


def bird_is_imminent(state: dict[str, Any]) -> bool:
    if bool(state.get("jumping")) or not _is_bird(state):
        return False
    x = _nearest_x(state)
    if x is None:
        return False
    if bird_is_high(state):
        return x <= BIRD_REFLEX_X
    return x <= REFLEX_X


def reflex_buttons(state: dict[str, Any]) -> DinoButtons | None:
    if bird_is_imminent(state):
        if bird_is_high(state):
            return mix_dino(0.1, 0.9, grounded=True)
        return mix_dino(0.9, 0.1, grounded=True)
    if cactus_is_imminent(state):
        return mix_dino(0.9, 0.1, grounded=True)
    return None


def close_enough_to_save(state: dict[str, Any]) -> bool:
    if not bool(state.get("grounded")) or _is_bird(state):
        return False
    x = _nearest_x(state)
    return x is not None and x <= JEV_SAVE_X


def apply_late_jump(state: dict[str, Any], buttons: DinoButtons) -> DinoButtons:
    """If Jev is weakly yes and the cactus is already late, jump."""
    if buttons.jump or bool(state.get("jumping")) or not bool(state.get("grounded")):
        return buttons
    if _is_bird(state):
        return buttons
    x = _nearest_x(state)
    if x is None or buttons.jump_noul < LATE_JUMP_NOUL:
        return buttons
    horizon = LATE_JUMP_X
    kind = str(state.get("nearest_type") or "").upper()
    if "LARGE" in kind:
        horizon += LATE_JUMP_LARGE_EXTRA
    width = state.get("nearest_width")
    if width is not None:
        try:
            horizon = max(horizon, LATE_JUMP_X + float(width))
        except (TypeError, ValueError):
            pass
    if x > horizon:
        return buttons
    return DinoButtons(
        jump=True,
        duck=False,
        jump_noul=buttons.jump_noul,
        duck_noul=buttons.duck_noul,
    )


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
    reflex = reflex_buttons(state)
    if reflex is not None:
        print(
            f"dino reflex jump={reflex.jump} duck={reflex.duck} "
            f"nearest_x={state.get('nearest_x')} nearest_y={state.get('nearest_y')} "
            f"type={state.get('nearest_type')}",
            file=sys.stderr,
        )
        return reflex
    if not should_ask_jev(state):
        print(
            f"dino jev skip jumping={bool(state.get('jumping'))} "
            f"nearest_x={state.get('nearest_x')} nearest_y={state.get('nearest_y')} "
            f"type={state.get('nearest_type')}",
            file=sys.stderr,
        )
        return idle
    last_exc: JevUnavailable | None = None
    try:
        buttons = jev_dino_buttons(client, state)
        buttons = apply_late_jump(state, buttons)
        x = _nearest_x(state)
        # gw18: Jev jumped at 377, still airborne for the next cactus.
        if buttons.jump and x is not None and x > REFLEX_X:
            buttons = DinoButtons(
                jump=False,
                duck=buttons.duck,
                jump_noul=buttons.jump_noul,
                duck_noul=buttons.duck_noul,
            )
        print(
            f"dino jev noul_jump={buttons.jump_noul:.2f} noul_duck={buttons.duck_noul:.2f} "
            f"do_jump={buttons.jump} do_duck={buttons.duck} grounded={grounded} "
            f"jumping={bool(state.get('jumping'))} nearest_x={state.get('nearest_x')} "
            f"nearest_y={state.get('nearest_y')} type={state.get('nearest_type')}",
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
