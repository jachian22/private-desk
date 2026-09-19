import json
import time

from private_desk.api import get_job, list_kinds, start_job
from private_desk.dino_cdp import FakeDinoGame, START_JS, is_dino_url, loopback_ws_url, prefer_page_targets, wait_for_devtools_ws
from private_desk.dino_session import CLEAR_DISTANCE
from private_desk.jev.client import VercelGatewayJevClient
from private_desk.jev.dino import jev_dino_buttons, mix_dino, public_dino_state, scripted_dino_buttons
from private_desk.kinds import load_kinds


def test_dino_kind_is_not_holo(isolated):
    kind = load_kinds()["demo_dino"]
    assert kind.runner == "dino"
    assert kind.may_need_you is True
    assert kind.launch_url == "chrome://dino"
    listed = list_kinds().payload["kinds"]
    item = next(k for k in listed if k["id"] == "demo_dino")
    assert "prompt" not in item
    assert item["may_need_you"] is True


def test_dino_start_without_key_fails_closed(isolated):
    result = start_job("demo_dino", {}, None)
    assert result.ok is False
    assert result.payload["error"]["code"] == "jev_unavailable"


def test_dino_safari_denied(isolated, monkeypatch):
    from private_desk.config import load_config, save_config

    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    cfg = load_config()
    cfg.browser = "Safari"
    save_config(cfg)
    result = start_job("demo_dino", {}, None)
    assert result.ok is False
    assert result.payload["error"]["code"] == "kind_denied"


def test_dino_safari_denied_with_gateway_key(isolated, monkeypatch):
    from private_desk.config import load_config, save_config

    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gw-test")
    cfg = load_config()
    cfg.browser = "Safari"
    save_config(cfg)
    result = start_job("demo_dino", {}, None)
    assert result.ok is False
    assert result.payload["error"]["code"] == "kind_denied"
    assert "gw-test" not in json.dumps(result.payload)


def test_dino_fake_runner_succeeds(isolated, monkeypatch):
    monkeypatch.setenv("PRIVATE_DESK_FAKE_RUNNER", "ok")
    result = start_job("demo_dino", {}, "dino-fake-1")
    assert result.ok
    job_id = result.payload["job"]["job_id"]
    deadline = time.time() + 8.0
    last = None
    while time.time() < deadline:
        last = get_job(job_id).payload["job"]
        if last["state"] != "running":
            break
        time.sleep(0.05)
    assert last is not None
    assert last["state"] == "succeeded"
    assert last["kind"] == "demo_dino"
    assert last["artifacts"]["files"] == ["run.json"]
    assert last["summary"] is None


def test_scripted_dino_jumps_for_close_cactus():
    buttons = scripted_dino_buttons(
        {
            "grounded": True,
            "speed": 6,
            "nearest_type": "CACTUS_SMALL",
            "nearest_x": 80,
            "nearest_y": 100,
        }
    )
    assert buttons.jump is True
    assert buttons.duck is False


def test_scripted_dino_ducks_high_bird():
    buttons = scripted_dino_buttons(
        {
            "grounded": True,
            "speed": 8,
            "nearest_type": "PTERODACTYL",
            "nearest_x": 90,
            "nearest_y": 50,
        }
    )
    assert buttons.duck is True
    assert buttons.jump is False


def test_mix_dino_no_jump_in_air():
    buttons = mix_dino(0.99, 0.1, grounded=False)
    assert buttons.jump is False


def test_public_dino_state_has_no_pixels():
    raw = {
        "playing": True,
        "crashed": False,
        "speed": 7.2,
        "distance": 40,
        "grounded": True,
        "screenshot": "SHOULD_NOT_LEAK",
        "obstacles": [{"type": "CACTUS_SMALL", "x": 100, "y": 90, "width": 17, "image": "nope"}],
        "nearest_type": "CACTUS_SMALL",
        "nearest_x": 100,
        "nearest_y": 90,
    }
    public = public_dino_state(raw)
    blob = str(public)
    assert "screenshot" not in public
    assert "SHOULD_NOT_LEAK" not in blob
    assert "image" not in blob
    assert public["nearest_x"] == 100


def test_wait_for_devtools_ws_reads_file(tmp_path, monkeypatch):
    (tmp_path / "DevToolsActivePort").write_text("9333\n/devtools/browser/abc\n")

    class _Sock:
        def close(self) -> None:
            return None

    monkeypatch.setattr("private_desk.dino_cdp.socket.create_connection", lambda *a, **k: _Sock())
    assert wait_for_devtools_ws(tmp_path, timeout_s=1.0) == "ws://127.0.0.1:9333/devtools/browser/abc"


def test_is_dino_url():
    assert is_dino_url("chrome://dino/")
    assert is_dino_url("chrome-error://chromewebdata/")
    assert not is_dino_url("about:blank")
    assert not is_dino_url("https://github.com/")


def test_prefer_page_targets_new_tab_over_startup_blank():
    pages = [
        {"targetId": "blank", "url": "about:blank", "type": "page"},
        {"targetId": "dino", "url": "chrome://dino/", "type": "page"},
    ]
    ordered = prefer_page_targets(pages)
    assert [p["targetId"] for p in ordered] == ["dino", "blank"]
    blanks = prefer_page_targets(
        [
            {"targetId": "first", "url": "about:blank"},
            {"targetId": "second", "url": "about:blank"},
        ]
    )
    assert [p["targetId"] for p in blanks] == ["second", "first"]


def test_loopback_ws_url_forces_ipv4():
    assert loopback_ws_url("ws://localhost:9222/devtools/page/1") == "ws://127.0.0.1:9222/devtools/page/1"
    assert loopback_ws_url("ws://[::1]:9222/devtools/page/1") == "ws://127.0.0.1:9222/devtools/page/1"
    assert loopback_ws_url("ws://127.0.0.1:9222/devtools/page/1") == "ws://127.0.0.1:9222/devtools/page/1"


def test_fake_dino_scripted_clears_distance():
    game = FakeDinoGame()
    snap = {}
    for _ in range(40):
        snap = game.snapshot()
        if snap.get("crashed"):
            break
        buttons = scripted_dino_buttons(snap)
        if buttons.jump:
            game.tap_jump()
        elif buttons.duck:
            game.set_duck(True)
        else:
            game.set_duck(False)
        if float(snap.get("distance") or 0) >= CLEAR_DISTANCE:
            break
    assert snap.get("crashed") is False
    assert float(snap.get("distance") or 0) >= CLEAR_DISTANCE


def test_gateway_dino_boolean_maps_to_jump(isolated):
    def fake_post(url, headers, body, timeout):
        payload = json.loads(body)
        assert payload["questions"]["jump"]["type"] == "boolean"
        assert payload["questions"]["duck"]["type"] == "boolean"
        return {
            "answers": {
                "jump": {"type": "boolean", "probability": 0.8},
                "duck": {"type": "boolean", "probability": 0.1},
            }
        }

    client = VercelGatewayJevClient("gw-secret", post=fake_post)
    buttons = jev_dino_buttons(
        client,
        {"grounded": True, "speed": 6, "nearest_x": 40, "nearest_type": "CACTUS_SMALL"},
    )
    assert buttons.jump is True
    assert buttons.duck is False
    assert buttons.jump_noul == 0.8


def test_late_jump_when_weak_noul_and_cactus_is_close():
    from private_desk.jev.dino import apply_late_jump, mix_dino

    state = {
        "grounded": True,
        "jumping": False,
        "nearest_x": 100,
        "nearest_type": "cactusSmall",
    }
    weak = mix_dino(0.46, 0.05, grounded=True)
    assert weak.jump is False
    late = apply_late_jump(state, weak)
    assert late.jump is True


def test_late_jump_saves_gw12_small_cactus():
    from private_desk.jev.dino import apply_late_jump, mix_dino

    # gw12: 0.47 at 122, then crash on the next tick.
    state = {
        "grounded": True,
        "jumping": False,
        "nearest_x": 122,
        "nearest_type": "cactusSmall",
    }
    assert apply_late_jump(state, mix_dino(0.47, 0.06, grounded=True)).jump is True


def test_late_jump_large_cactus_gets_more_lead():
    from private_desk.jev.dino import apply_late_jump, mix_dino

    state = {
        "grounded": True,
        "jumping": False,
        "nearest_x": 154,
        "nearest_type": "cactusLarge",
    }
    assert apply_late_jump(state, mix_dino(0.42, 0.05, grounded=True)).jump is True


def test_late_jump_does_not_fire_when_cactus_is_still_far():
    from private_desk.jev.dino import apply_late_jump, mix_dino

    state = {
        "grounded": True,
        "jumping": False,
        "nearest_x": 220,
        "nearest_type": "cactusSmall",
    }
    weak = mix_dino(0.46, 0.05, grounded=True)
    assert apply_late_jump(state, weak).jump is False


def test_start_js_skips_intro_and_blur_pause():
    assert "startGame" in START_JS
    assert "onVisibilityChange" in START_JS
    assert "playingIntro" in START_JS
    assert "startJump" not in START_JS
    assert 'width = "600px"' in START_JS or "600px" in START_JS
    assert "pd-dino-place" in START_JS
    from private_desk.dino_cdp import RESUME_JS
    assert "pd-dino-place" in RESUME_JS


def test_reflex_jumps_without_jev_when_cactus_is_imminent():
    from private_desk.jev.dino import live_dino_buttons

    class Boom:
        def ask_response(self, state, questions):
            raise AssertionError("Jev must not block inside the reflex band")

    buttons = live_dino_buttons(
        Boom(),
        {
            "grounded": True,
            "jumping": False,
            "speed": 6,
            "nearest_x": 216,
            "nearest_type": "cactusLarge",
        },
    )
    assert buttons.jump is True


def test_reflex_ducks_high_bird():
    from private_desk.jev.dino import live_dino_buttons

    class Boom:
        def ask_response(self, state, questions):
            raise AssertionError("high bird should duck without Jev")

    buttons = live_dino_buttons(
        Boom(),
        {
            "grounded": True,
            "jumping": False,
            "nearest_x": 146,
            "nearest_y": 50,
            "nearest_type": "pterodactyl",
        },
    )
    assert buttons.duck is True
    assert buttons.jump is False


def test_reflex_ducks_high_bird_before_jev_band():
    from private_desk.jev.dino import live_dino_buttons

    class Boom:
        def ask_response(self, state, questions):
            raise AssertionError("gw19: do not wait on Jev for a high bird")

    buttons = live_dino_buttons(
        Boom(),
        {
            "grounded": True,
            "jumping": False,
            "nearest_x": 329,
            "nearest_y": 50,
            "nearest_type": "pterodactyl",
        },
    )
    assert buttons.duck is True
    assert buttons.jump is False


def test_low_bird_waits_then_jumps_locally():
    from private_desk.jev.dino import live_dino_buttons

    class Boom:
        def ask_response(self, state, questions):
            raise AssertionError("low bird is local, not Jev")

    wait = live_dino_buttons(
        Boom(),
        {
            "grounded": True,
            "jumping": False,
            "nearest_x": 329,
            "nearest_y": 100,
            "nearest_type": "pterodactyl",
        },
    )
    assert wait.jump is False
    assert wait.duck is False
    hop = live_dino_buttons(
        Boom(),
        {
            "grounded": True,
            "jumping": False,
            "nearest_x": 216,
            "nearest_y": 100,
            "nearest_type": "pterodactyl",
        },
    )
    assert hop.jump is True


def test_layout_reset_keeps_trex_on_screen():
    from private_desk.dino_cdp import LAYOUT_RESET_JS, LAYOUT_RESET_WINDOW_JS

    assert "left top" in LAYOUT_RESET_JS
    assert "padL" in LAYOUT_RESET_JS
    assert "margin = '0'" in LAYOUT_RESET_JS
    assert "pd-dino-place" in LAYOUT_RESET_JS
    assert "transition: none" in LAYOUT_RESET_JS
    assert "querySelector('.runner-container')" in LAYOUT_RESET_JS
    assert "querySelector('.runner-container')" in LAYOUT_RESET_WINDOW_JS


def test_jev_asked_when_cactus_is_still_far():
    from types import SimpleNamespace

    from private_desk.jev.dino import live_dino_buttons

    class Capture:
        def __init__(self) -> None:
            self.called = False

        def ask_response(self, state, questions):
            self.called = True
            assert state.get("nearest_x") == 450
            return SimpleNamespace(
                nouls={
                    "jump": SimpleNamespace(noul=0.8),
                    "duck": SimpleNamespace(noul=0.1),
                }
            )

    client = Capture()
    buttons = live_dino_buttons(
        client,
        {"grounded": True, "speed": 6, "nearest_x": 450, "nearest_type": "CACTUS_SMALL"},
    )
    assert client.called is True
    assert buttons.jump is True


def test_jev_not_asked_in_mid_band():
    from private_desk.jev.dino import live_dino_buttons

    class Boom:
        def ask_response(self, state, questions):
            raise AssertionError("mid-band cactus should wait for reflex, not Jev")

    buttons = live_dino_buttons(
        Boom(),
        {"grounded": True, "speed": 6, "nearest_x": 320, "nearest_type": "CACTUS_SMALL"},
    )
    assert buttons.jump is False


def test_jev_jump_at_377_is_ignored():
    from types import SimpleNamespace

    from private_desk.jev.dino import live_dino_buttons

    class Capture:
        def ask_response(self, state, questions):
            return SimpleNamespace(
                nouls={
                    "jump": SimpleNamespace(noul=0.52),
                    "duck": SimpleNamespace(noul=0.05),
                }
            )

    buttons = live_dino_buttons(
        Capture(),
        {"grounded": True, "speed": 6, "nearest_x": 377, "nearest_type": "cactusSmall"},
    )
    assert buttons.jump is False


def test_prefer_live_buttons_drops_early_hop():
    from private_desk.jev.dino import mix_dino, prefer_live_buttons

    planned = mix_dino(0.8, 0.05, grounded=True)
    held = prefer_live_buttons(
        {"grounded": True, "jumping": False, "nearest_x": 420, "nearest_type": "cactusSmall"},
        planned,
    )
    assert held.jump is False
    hop = prefer_live_buttons(
        {"grounded": True, "jumping": False, "nearest_x": 280, "nearest_type": "cactusSmall"},
        planned,
    )
    assert hop.jump is True


def test_jev_skipped_when_cactus_is_far():
    from private_desk.jev.dino import live_dino_buttons

    class Boom:
        def ask_response(self, state, questions):
            raise AssertionError("Jev should not run while the cactus is far")

    buttons = live_dino_buttons(
        Boom(),
        {"grounded": True, "speed": 6, "nearest_x": 600, "nearest_type": "CACTUS_SMALL"},
    )
    assert buttons.jump is False


def test_jev_skipped_while_airborne():
    from private_desk.jev.dino import live_dino_buttons

    class Boom:
        def ask_response(self, state, questions):
            raise AssertionError("Jev should not run while jumping")

    buttons = live_dino_buttons(
        Boom(),
        {
            "grounded": False,
            "jumping": True,
            "speed": 6,
            "nearest_x": 160,
            "nearest_type": "CACTUS_SMALL",
        },
    )
    assert buttons.jump is False


def test_jev_idle_when_horizon_empty():
    from private_desk.jev.dino import live_dino_buttons

    class Boom:
        def ask_response(self, state, questions):
            raise AssertionError("Jev should not run on an empty horizon")

    buttons = live_dino_buttons(Boom(), {"grounded": True, "speed": 6})
    assert buttons.jump is False


def test_public_dino_state_playing_when_run_started():
    public = public_dino_state(
        {"playing": False, "distance": 12, "grounded": True, "speed": 6}
    )
    assert public["playing"] is True


def test_dino_gateway_flake_jumps_when_cactus_is_close():
    from private_desk.jev.client import JevUnavailable
    from private_desk.jev.dino import live_dino_buttons

    class Limited:
        def ask_response(self, state, questions):
            raise JevUnavailable("Vercel AI Gateway request failed (HTTP 429).")

    buttons = live_dino_buttons(
        Limited(),
        {"grounded": True, "speed": 6, "nearest_x": 40, "nearest_type": "CACTUS_SMALL"},
    )
    assert buttons.jump is True


def test_dino_gateway_flake_does_not_jump_when_far():
    from private_desk.jev.client import JevUnavailable
    from private_desk.jev.dino import live_dino_buttons

    class Limited:
        def ask_response(self, state, questions):
            raise JevUnavailable("Vercel AI Gateway request failed (HTTP 429).")

    buttons = live_dino_buttons(
        Limited(),
        {"grounded": True, "speed": 6, "nearest_x": 600, "nearest_type": "CACTUS_SMALL"},
    )
    assert buttons.jump is False


def test_snapshot_uses_intern_scoreboard_units():
    from private_desk.dino_cdp import SNAPSHOT_JS

    assert "getActualDistance" in SNAPSHOT_JS
    assert "0.025" in SNAPSHOT_JS
    assert "r.playing = false" not in SNAPSHOT_JS


def test_live_loop_does_not_block_on_jev():
    import time
    from types import SimpleNamespace

    from private_desk.jev.dino import LiveDinoLoop

    class Slow:
        def ask_response(self, state, questions):
            time.sleep(0.25)
            return SimpleNamespace(
                nouls={
                    "jump": SimpleNamespace(noul=0.8),
                    "duck": SimpleNamespace(noul=0.1),
                }
            )

    loop = LiveDinoLoop(Slow())
    try:
        far = {
            "grounded": True,
            "jumping": False,
            "speed": 6,
            "nearest_x": 450,
            "nearest_type": "cactusSmall",
        }
        first = loop.decide(far)
        assert first.jump is False
        t0 = time.time()
        mid = loop.decide(far)
        assert time.time() - t0 < 0.1
        assert mid.jump is False
        time.sleep(0.3)
        hop = loop.decide(
            {
                "grounded": True,
                "jumping": False,
                "speed": 6,
                "nearest_x": 280,
                "nearest_type": "cactusSmall",
            }
        )
        assert hop.jump is True
    finally:
        loop.close()


def test_live_loop_skips_jev_for_two_ticks_after_landing():
    from types import SimpleNamespace

    from private_desk.jev.dino import LiveDinoLoop

    class Capture:
        def __init__(self) -> None:
            self.n = 0

        def ask_response(self, state, questions):
            self.n += 1
            return SimpleNamespace(
                nouls={
                    "jump": SimpleNamespace(noul=0.8),
                    "duck": SimpleNamespace(noul=0.1),
                }
            )

    client = Capture()
    loop = LiveDinoLoop(client)
    try:
        air = {
            "grounded": False,
            "jumping": True,
            "speed": 6,
            "nearest_x": 450,
            "nearest_type": "cactusSmall",
        }
        land = {
            "grounded": True,
            "jumping": False,
            "speed": 6,
            "nearest_x": 412,
            "nearest_type": "cactusSmall",
        }
        loop.decide(air)
        loop.decide(land)
        loop.decide(land)
        assert client.n == 0
        loop.decide(
            {
                "grounded": True,
                "jumping": False,
                "speed": 6,
                "nearest_x": 450,
                "nearest_type": "cactusSmall",
            }
        )
        deadline = time.time() + 1.0
        while client.n == 0 and time.time() < deadline:
            time.sleep(0.02)
        assert client.n == 1
    finally:
        loop.close()


def test_handler_object_ids_reads_cdp_listeners():
    from private_desk.dino_cdp import handler_object_ids

    ids = handler_object_ids(
        {
            "listeners": [
                {"type": "keydown", "handler": {"objectId": "runner-1", "className": "Runner"}},
                {"type": "keydown", "handler": {"type": "function"}},
                {"type": "load"},
            ]
        }
    )
    assert ids == ["runner-1"]
