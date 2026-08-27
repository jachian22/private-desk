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
