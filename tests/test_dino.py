import json
import time

from private_desk.api import get_job, list_kinds, start_job
from private_desk.dino_cdp import FakeDinoGame, START_JS, loopback_ws_url, wait_for_devtools_ws
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


def test_start_js_skips_intro_and_blur_pause():
    assert "startGame" in START_JS
    assert "onVisibilityChange" in START_JS
    assert "playingIntro" in START_JS
