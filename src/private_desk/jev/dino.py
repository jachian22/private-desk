"""Jev questions for chrome://dino. No pixels. Threshold 0.5."""

from __future__ import annotations

import sys
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol

from private_desk.jev.client import JevUnavailable, _noul_of

NOUL_THRESHOLD = 0.5
# Live intern: Jev RTT lets a cactus close ~200px. Do not wait on Jev inside this band.
REFLEX_X = 260.0
# Ask only while the cactus is still far enough that a Gateway wait leaves reflex time.
JEV_ASK_MIN = 380.0
JEV_ASK_MAX = 560.0
# After the wait, honor a Jev hop only if the cactus has closed into this band.
JEV_HOP_X = 300.0
# High birds: duck as soon as they enter the ask band. Do not wait on Jev.
BIRD_REFLEX_X = 400.0
JEV_SAVE_X = 180.0
LATE_JUMP_X = 140.0
LATE_JUMP_NOUL = 0.40
LATE_JUMP_LARGE_EXTRA = 40.0
# gw22: landed, asked Jev at 412, Gateway ate the cactus. Skip new asks after a hop.
LAND_SKIP_TICKS = 2

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
    if bool(state.get("jumping")) or not bool(state.get("grounded")):
        return False
    if _is_bird(state):
        return False
    x = _nearest_x(state)
    if x is None:
        return False
    return JEV_ASK_MIN < x <= JEV_ASK_MAX


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


def prefer_live_buttons(fresh: dict[str, Any], planned: DinoButtons) -> DinoButtons:
    """After a Jev wait, the intern has moved. Reflex wins; early hops stay down."""
    reflex = reflex_buttons(fresh)
    if reflex is not None:
        return reflex
    x = _nearest_x(fresh)
    if planned.jump and x is not None and x > JEV_HOP_X:
        return DinoButtons(
            jump=False,
            duck=planned.duck,
            jump_noul=planned.jump_noul,
            duck_noul=planned.duck_noul,
        )
    return planned


class LiveDinoLoop:
    """Reflex on the tick. Jev runs in the background and is applied only if still safe."""

    def __init__(self, client: DinoJev) -> None:
        self._client = client
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dino-jev")
        self._fut: Future[DinoButtons] | None = None
        self._was_jumping = False
        self._land_skip = 0

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _note_landing(self, state: dict[str, Any]) -> None:
        jumping = bool(state.get("jumping"))
        landed = self._was_jumping and not jumping
        if not jumping and self._land_skip > 0 and not landed:
            self._land_skip -= 1
        if landed:
            self._land_skip = LAND_SKIP_TICKS
            print("dino land skip asks", file=sys.stderr)
        self._was_jumping = jumping

    def _harvest(self, state: dict[str, Any]) -> DinoButtons | None:
        if self._fut is None or not self._fut.done():
            return None
        fut = self._fut
        self._fut = None
        try:
            planned = fut.result()
        except JevUnavailable as exc:
            print(
                f"dino jev async failed {exc.message} nearest_x={state.get('nearest_x')}",
                file=sys.stderr,
            )
            if close_enough_to_save(state):
                return scripted_dino_buttons(state)
            return None
        except Exception as exc:
            print(f"dino jev async error {exc}", file=sys.stderr)
            return None
        buttons = apply_late_jump(state, planned)
        buttons = prefer_live_buttons(state, buttons)
        print(
            f"dino jev async noul_jump={buttons.jump_noul:.2f} noul_duck={buttons.duck_noul:.2f} "
            f"do_jump={buttons.jump} do_duck={buttons.duck} "
            f"nearest_x={state.get('nearest_x')} type={state.get('nearest_type')}",
            file=sys.stderr,
        )
        return buttons

    def _kick(self, state: dict[str, Any]) -> None:
        if self._fut is not None:
            return
        if self._land_skip > 0:
            return
        if not should_ask_jev(state):
            return
        payload = dict(state)
        print(
            f"dino jev async kick nearest_x={state.get('nearest_x')} "
            f"type={state.get('nearest_type')}",
            file=sys.stderr,
        )
        self._fut = self._pool.submit(jev_dino_buttons, self._client, payload)

    def decide(self, state: dict[str, Any]) -> DinoButtons:
        grounded = bool(state.get("grounded"))
        idle = mix_dino(0.1, 0.1, grounded=grounded)
        self._note_landing(state)
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
        harvested = self._harvest(state)
        self._kick(state)
        if harvested is not None:
            return harvested
        return idle
