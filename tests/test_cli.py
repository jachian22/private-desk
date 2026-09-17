from private_desk.cli import main


def test_cli_unknown_kind_exit_2(isolated, capsys):
    code = main(["start", "sync_chase"])
    assert code == 2
    out = capsys.readouterr().out
    assert "kind_denied" in out


def test_cli_kinds(isolated, capsys):
    code = main(["kinds"])
    assert code == 0
    out = capsys.readouterr().out
    assert "demo_dummy_files" in out
    assert "prompt" not in out or '"prompt"' not in out


def test_cli_bare_job_id_is_get(isolated, capsys, monkeypatch):
    monkeypatch.setenv("PRIVATE_DESK_FAKE_RUNNER", "ok")
    from private_desk.api import start_job

    started = start_job("demo_dummy_files", {}, "cli-bare-id")
    job_id = started.payload["job"]["job_id"]
    assert job_id.startswith("job_")
    code = main([job_id])
    assert code == 0
    out = capsys.readouterr().out
    assert job_id in out
    assert '"kind": "demo_dummy_files"' in out or "demo_dummy_files" in out
