from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def mini_pdf() -> Path:
    return FIXTURES / "studypack_mini.pdf"


@pytest.fixture
def real_pack() -> Path:
    path = FIXTURES / "local" / "biol2040.pdf"
    if not path.exists():
        pytest.skip("real pack not present")
    return path


@pytest.fixture(autouse=True)
def _storyteller_env(monkeypatch, tmp_path):
    monkeypatch.setenv("STORYTELLER_HOME", str(tmp_path))
    monkeypatch.setenv("STORYTELLER_VOICE", "stub")


@pytest.fixture
def plain_pdf() -> Path:
    return FIXTURES / "plain_report.pdf"
