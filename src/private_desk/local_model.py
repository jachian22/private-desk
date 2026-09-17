"""Loopback OpenAI-compatible model probe. llama.cpp is a pet: we never spawn it."""

from __future__ import annotations

import urllib.error
import urllib.request

# H Company Mac recipe + --host 127.0.0.1. Do not bind 0.0.0.0.
# https://hub.hcompany.ai/holo-desktop-cli/how-to/run-a-local-model-server
# -hf is unambiguous (--hf can match --hf-repo/--hf-file/--hf-token).
LLAMA_SERVER_BOOT = (
    "llama-server -hf Hcompany/Holo-3.1-35B-A3B-GGUF --host 127.0.0.1 "
    "--n-gpu-layers 999 --ctx-size 65536 --batch-size 16384 --ubatch-size 2048 "
    "--flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 "
    "--image-min-tokens 1024 --ctx-checkpoints 8 --cache-ram 32768 "
    "--kv-unified --threads 16"
)

def probe_local_model(url: str) -> str:
    """GET {base}/models. Returns reachable | unreachable. Never starts a server."""
    try:
        req = urllib.request.Request(url.rstrip("/") + "/models", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            resp.read(256)
        return "reachable"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return "unreachable"


def boot_notes(holo_base_url: str) -> list[str]:
    return [
        "Local model is not running.",
        f"Bank and session-canary kinds need llama-server at {holo_base_url}.",
        "private-desk will not start it for you. Copy-paste:",
        LLAMA_SERVER_BOOT,
    ]


def unavailable_message(holo_base_url: str) -> str:
    return (
        f"Local model is not running at {holo_base_url}. "
        "Start llama-server yourself (private-desk will not spawn it): "
        f"{LLAMA_SERVER_BOOT}"
    )
