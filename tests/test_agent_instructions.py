"""The agent guide's examples must run against the test fixtures."""

import re
import shlex
from pathlib import Path

import pytest

from mdpeek.cli import agent_instructions, main

FIXTURES = Path(__file__).parent / "fixtures"
SOURCES = {  # the placeholder source in each example -> the fixture it runs on
    "doc.md": FIXTURES / "large" / "handbook.md",
    "docs/": FIXTURES / "library",
}
EXAMPLES = [
    line
    for line in agent_instructions().splitlines()
    if line.startswith("mdpeek ") and line.split()[1] in SOURCES
]


def test_guide_has_examples() -> None:
    assert {line.split()[1] for line in EXAMPLES} == set(SOURCES)
    assert len(EXAMPLES) >= 15


@pytest.mark.parametrize("example", EXAMPLES)
def test_example_runs(example: str, capsys: pytest.CaptureFixture[str]) -> None:
    command = re.sub(r"\s+#\s.*$", "", example)  # PATH#ID is not a comment
    argv = shlex.split(command)[1:]
    argv[0] = str(SOURCES[argv[0]])
    assert main(argv) == 0, capsys.readouterr().err
    assert capsys.readouterr().out


def test_guide_stays_compact() -> None:
    assert len(agent_instructions()) < 3500
