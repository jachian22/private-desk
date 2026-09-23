from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_human_guide_lives_in_the_docs_repo():
    readme = (ROOT / "README.md").read_text()
    assert "github.com/jachian22/private-desk-docs" in readme
    assert not (ROOT / "docs" / "docs.json").exists()
