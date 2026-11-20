"""Shared, language-neutral steps for the CLI feature files.

Keep step wording free of Python specifics: a future Rust CLI runs the same
``.feature`` files with its own step definitions.
"""

from __future__ import annotations

import io
import shlex
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from mdpeek import cache as cache_module
from mdpeek import tables as tables_module
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
    path = workdir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(docstring + "\n", encoding="utf-8")


@given(parsers.parse('a file "{name}" containing:'))
def any_file(workdir: Path, name: str, docstring: str) -> None:
    markdown_file(workdir, name, docstring)


@given(parsers.parse('an empty directory "{name}"'))
def empty_directory(workdir: Path, name: str) -> None:
    (workdir / name).mkdir(parents=True, exist_ok=True)


@given(parsers.parse('the fixture directory "{fixture}" as "{name}"'))
def fixture_directory(workdir: Path, fixture: str, name: str) -> None:
    shutil.copytree(FIXTURES / fixture, workdir / name)


@given("a markdown file containing:")
def default_markdown_file(workdir: Path, docstring: str) -> None:
    markdown_file(workdir, "doc.md", docstring)


@given(parsers.parse('the fixture "{fixture}" as "{name}"'))
def fixture_file(workdir: Path, fixture: str, name: str) -> None:
    (workdir / name).write_bytes((FIXTURES / fixture).read_bytes())


@given(parsers.parse('table "{table_id}" cannot be parsed'))
def table_cannot_be_parsed(table_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(table) -> None:
        if table.id == table_id:
            raise ValueError("simulated parse failure")

    monkeypatch.setattr(tables_module, "build_hook", fail)


@given(parsers.parse('a URL "{path}" serving:'))
@given(parsers.parse('the URL "{path}" now serves:'))
def url_serving(http_server, path: str, docstring: str) -> None:
    http_server.serve(path, docstring + "\n")


@given(parsers.parse('the time is "{moment}"'))
def the_time_is(moment: str, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = datetime.strptime(moment, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
    monkeypatch.setattr(cache_module, "now", lambda: frozen)


@when(parsers.parse('I run "{command}"'))
def run_command(
    workdir: Path,
    result: Result,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    if "{server}" in command:
        command = command.replace("{server}", request.getfixturevalue("http_server").url)
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


@then(parsers.re(r"the server received (?P<count>\d+) requests?"))
def server_received(http_server, count: str) -> None:
    assert len(http_server.requests) == int(count), http_server.requests


@then(parsers.parse('the last request had the header "{name}: {value}"'))
def last_request_header(http_server, name: str, value: str) -> None:
    assert http_server.requests[-1]["headers"].get(name) == value


@then(parsers.parse('no cached file contains "{text}"'))
def no_cached_file_contains(isolated_cache: Path, text: str) -> None:
    files = list(isolated_cache.iterdir())
    assert files, "expected something in the cache"
    assert all(text not in f.read_text(encoding="utf-8") for f in files)


@then(parsers.parse('the output does not start with "{prefix}"'))
def output_does_not_start_with(result: Result, prefix: str) -> None:
    assert not result.stdout.startswith(prefix), result.stdout
