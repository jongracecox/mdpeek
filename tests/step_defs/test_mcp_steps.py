"""Steps for the MCP tool features.

The tool is called with JSON arguments, as an MCP client sends them, so the
feature files stay independent of the language the tool is written in.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from mdpeek.mcp import ToolError, Toolset

FIXTURES = Path(__file__).parent.parent / "fixtures"

scenarios("../mcp_features")


@dataclass
class Call:
    root: Path | None = None
    options: dict[str, Any] = field(default_factory=dict)
    text: str | None = None
    error: str | None = None
    files_before: set[Path] = field(default_factory=set)


@pytest.fixture
def call() -> Call:
    return Call()


@pytest.fixture
def workdir(tmp_path, monkeypatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


@given(parsers.parse('a docs directory from the fixture "{name}"'))
def docs_directory(call: Call, workdir: Path, name: str) -> None:
    call.root = workdir / "docs"
    shutil.copytree(FIXTURES / name, call.root)


@given(parsers.parse('a file outside the docs directory linked as "{link}"'))
def outside_link(call: Call, workdir: Path, link: str) -> None:
    assert call.root is not None
    secret = workdir / "secret.md"
    secret.write_text("# Secret\n")
    os.symlink(secret, call.root / link)


@given("the tool is configured without SQL")
def without_sql(call: Call) -> None:
    call.options["sql"] = False


@given("the tool is configured without a docs directory")
def without_docs(call: Call) -> None:
    call.root = None


@given("the tool is configured to return errors as text")
def errors_as_text(call: Call) -> None:
    call.options["errors"] = "return"


@when(parsers.parse("the agent calls the tool with {arguments}"))
def agent_calls(call: Call, workdir: Path, arguments: str) -> None:
    call.files_before = set(workdir.rglob("*"))
    toolset = Toolset(docs_dir=call.root, **call.options)
    try:
        call.text = toolset.call_sync(**json.loads(arguments))
    except ToolError as exc:
        call.error = str(exc)


def _text(call: Call) -> str:
    assert call.error is None, f"the call failed: {call.error}"
    assert call.text is not None
    return call.text


@then("the result is:")
def result_is(call: Call, docstring: str) -> None:
    assert _text(call) == docstring + "\n"


@then("the result starts with:")
def result_starts_with(call: Call, docstring: str) -> None:
    assert _text(call).startswith(docstring)


@then(parsers.parse('the result contains "{text}"'))
def result_contains(call: Call, text: str) -> None:
    assert text in _text(call)


@then(parsers.parse('the result ends with the note "{note}"'))
def result_note(call: Call, note: str) -> None:
    assert _text(call).endswith(f"note: {note}\n")


@then("the call fails")
def call_fails_plainly(call: Call) -> None:
    assert call.error is not None, f"the call succeeded: {call.text!r}"


@then(parsers.parse('the call fails with a message containing "{text}"'))
def call_fails(call: Call, text: str) -> None:
    assert call.error is not None, f"the call succeeded: {call.text!r}"
    assert text in call.error


@then("no new file was created")
def no_new_file(call: Call, workdir: Path) -> None:
    assert set(workdir.rglob("*")) == call.files_before
