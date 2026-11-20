"""Shared, language-neutral steps for the CLI feature files.

Keep step wording free of Python specifics: a future Rust CLI runs the same
``.feature`` files with its own step definitions.
"""

from __future__ import annotations

import io
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from mdpeek.cli import main

FIXTURES = Path(__file__).parent.parent / "fixtures"

scenarios("../features")


@dataclass
class Result:
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None


@pytest.fixture
def result() -> Result:
    return Result()


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _normalise(text: str) -> str:
    """Strip trailing whitespace per line and trailing blank lines."""
    return "\n".join(line.rstrip() for line in text.rstrip("\n").split("\n"))


@given(parsers.parse('a markdown file "{name}" containing:'))
def markdown_file(workdir: Path, name: str, docstring: str) -> None:
    (workdir / name).write_text(docstring + "\n", encoding="utf-8")


@given("a markdown file containing:")
def default_markdown_file(workdir: Path, docstring: str) -> None:
    markdown_file(workdir, "doc.md", docstring)


@given(parsers.parse('the fixture "{fixture}" as "{name}"'))
def fixture_file(workdir: Path, fixture: str, name: str) -> None:
    (workdir / name).write_bytes((FIXTURES / fixture).read_bytes())


@when(parsers.parse('I run "{command}"'))
def run_command(
    workdir: Path, result: Result, command: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv = shlex.split(command)
    assert argv[0] == "mdpeek", f"commands must start with 'mdpeek': {command!r}"
    stdout, stderr = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    try:
        result.exit_code = main(argv[1:])
    except SystemExit as exc:  # argparse errors and --version
        result.exit_code = exc.code if isinstance(exc.code, int) else 1
    result.stdout, result.stderr = stdout.getvalue(), stderr.getvalue()


@then("the output is:")
def output_is(result: Result, docstring: str) -> None:
    assert _normalise(result.stdout) == _normalise(docstring), (
        f"actual output:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@then("the output contains:")
def output_contains(result: Result, docstring: str) -> None:
    assert _normalise(docstring) in _normalise(result.stdout), result.stdout


@then("the output is empty")
def output_is_empty(result: Result) -> None:
    assert result.stdout == "", result.stdout


@then("stderr contains:")
def stderr_contains(result: Result, docstring: str) -> None:
    assert _normalise(docstring) in _normalise(result.stderr), result.stderr


@then(parsers.parse("the exit code is {code:d}"))
def exit_code_is(result: Result, code: int) -> None:
    assert result.exit_code == code, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
