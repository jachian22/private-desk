from __future__ import annotations

import os
from pathlib import Path

import pytest

from private_desk import paths


@pytest.fixture
def desk_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "config").mkdir(parents=True)
    (home / "data").mkdir(parents=True)
    monkeypatch.setenv("PRIVATE_DESK_HOME", str(home))
    monkeypatch.setenv(
        "PRIVATE_DESK_PUBLIC_KINDS",
        str(Path(__file__).resolve().parents[1] / "kinds"),
    )
    monkeypatch.delenv("PRIVATE_DESK_FAKE_RUNNER", raising=False)
    return home


@pytest.fixture
def isolated(desk_home):
    # Import after env is set so paths resolve under tmp home.
    return desk_home
