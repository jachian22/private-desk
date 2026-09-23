from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STARTER = (ROOT / "STARTER.md").read_text()


def test_starter_prompt_covers_ladder_and_friction():
    for needle in (
        "Paste this into Cursor",
        "demo_dummy_files",
        "demo_open_repo",
        "demo_dino",
        "PYTHONPATH=src",
        "~/.zprofile",
        "~/.zshrc",
        "Local Computer",
        "App Management",
        "Full Disk Access",
        "holo install",
        "npx vercel ai-gateway setup",
        "which private-desk",
        "Do not start demo_dino from Cursor",
        "onboarding.next",
    ):
        assert needle in STARTER
