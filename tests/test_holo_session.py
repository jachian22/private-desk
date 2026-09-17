import asyncio

from private_desk import jobs
from private_desk.holo_session import _pause_conflict, _pause_for_human
from private_desk.kinds import load_kinds


class _Conflict(Exception):
    def __init__(self) -> None:
        super().__init__("409 Conflict")
        self.response = type("R", (), {"status_code": 409})()


class _Client:
    def __init__(self, *, pause_exc: Exception | None = None) -> None:
        self.pause_exc = pause_exc
        self.paused = False
        self.resumed = False
        self.cancelled = False

    async def pause(self, _session_id: str) -> None:
        if self.pause_exc:
            raise self.pause_exc
        self.paused = True

    async def resume(self, _session_id: str) -> None:
        self.resumed = True

    async def cancel(self, _session_id: str) -> None:
        self.cancelled = True


async def _not_cancelled() -> bool:
    return False


def test_pause_conflict_detects_409():
    assert _pause_conflict(_Conflict()) is True
    assert _pause_conflict(RuntimeError("nope")) is False


def test_answer_409_still_sets_needs_you_and_skips_resume(isolated):
    """Live bug: Holo answered NEEDS_YOU, pause 409'd, job failed instead of waiting."""
    kind = load_kinds()["demo_star_repo"]
    job = jobs.new_job(
        kind=kind.id,
        risk=kind.risk,
        inference="hosted",
        idempotency_key="star-409",
    )
    jobs.resume_path(job["job_id"]).write_text("resume\n")
    seen = {}

    class Client(_Client):
        async def pause(self, _session_id: str) -> None:
            loaded = jobs.load_job(job["job_id"])
            seen["state"] = loaded["state"]
            seen["code"] = (loaded.get("user_action") or {}).get("code")
            seen["next"] = (loaded.get("user_action") or {}).get("next")
            raise _Conflict()

    client = Client()
    alive = asyncio.run(
        _pause_for_human(client, "sess", job, kind, "needs_login", _not_cancelled)
    )
    assert alive is False
    assert seen["state"] == "needs_you"
    assert seen["code"] == "needs_login"
    assert seen["next"] == "resume"
    assert client.resumed is False
    loaded = jobs.load_job(job["job_id"])
    assert loaded["state"] == "running"
    assert loaded["user_action"] is None


def test_pause_success_resumes_session(isolated):
    kind = load_kinds()["demo_star_repo"]
    job = jobs.new_job(
        kind=kind.id,
        risk=kind.risk,
        inference="hosted",
        idempotency_key="star-pause",
    )
    jobs.resume_path(job["job_id"]).write_text("resume\n")
    client = _Client()
    alive = asyncio.run(
        _pause_for_human(client, "sess", job, kind, "needs_login", _not_cancelled)
    )
    assert alive is True
    assert client.paused is True
    assert client.resumed is True
    loaded = jobs.load_job(job["job_id"])
    assert loaded["state"] == "running"


def test_pause_reopens_launch_url_after_resume(isolated, monkeypatch):
    kind = load_kinds()["demo_star_repo"]
    job = jobs.new_job(
        kind=kind.id,
        risk=kind.risk,
        inference="hosted",
        idempotency_key="star-reopen",
    )
    jobs.resume_path(job["job_id"]).write_text("resume\n")
    opened: list[tuple[str, str, bool]] = []

    def fake_open(app: str, url: str, *, isolated: bool = False, settle_s: float = 0) -> None:
        opened.append((app, url, isolated))

    monkeypatch.setattr("private_desk.holo_session.open_https", fake_open)
    client = _Client()
    asyncio.run(
        _pause_for_human(
            client,
            "sess",
            job,
            kind,
            "needs_login",
            _not_cancelled,
            browser="Google Chrome",
            launch_url="https://github.com/jachian22/private-desk",
            isolated=False,
        )
    )
    assert opened == [
        ("Google Chrome", "https://github.com/jachian22/private-desk", False)
    ]
    assert client.resumed is True
