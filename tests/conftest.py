from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
SMALL_FIXTURES = sorted((FIXTURES / "small").glob("*.md"))


def read_fixture(path: Path) -> str:
    """Read a fixture exactly, keeping its line endings."""
    return path.read_bytes().decode("utf-8")


@pytest.fixture
def fixture_text():
    def load(name: str) -> str:
        return read_fixture(FIXTURES / "small" / name)

    return load
