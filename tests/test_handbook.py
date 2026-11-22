"""The large handbook fixture: freshness, and what it must exercise."""

import importlib.util
import sys
from pathlib import Path

import pytest
from conftest import HANDBOOK, read_fixture

from mdpeek import Document

# The eval script reads TOML; tomllib arrived in Python 3.11.
tomllib = pytest.importorskip("tomllib")

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


def test_committed_handbook_matches_the_generator():
    assert _load_script("gen_handbook").build() == read_fixture(HANDBOOK), (
        "handbook.md is stale: run `uv run python scripts/gen_handbook.py`"
    )


def test_handbook_exercises_the_edge_cases():
    doc = Document.from_path(HANDBOOK)
    sections = list(doc.walk())
    titles = [s.title for s in sections]
    assert len(doc.lines) > 4000
    assert max(s.level for s in sections) == 6
    assert titles.count("Overview") >= 8  # duplicate titles
    assert "Architecture / Design" in titles  # slash
    assert "2. Fixes / Workarounds" in titles  # self-numbered
    assert {"Appendix", "Glossary"} <= set(titles)  # setext
    assert not any("not a heading" in t or "comment" in t for t in titles)
    assert doc.sections[0].is_preamble  # front matter + preamble
    by_shape = {(t.n_cols, t.n_rows) for t in doc.tables}
    assert (6, 320) in by_shape  # deep
    assert (24, 40) in by_shape  # wide
    assert any(t.warnings for t in doc.tables)  # ragged


def test_every_eval_scenario_finds_its_answer():
    eval_script = _load_script("eval")
    config = tomllib.loads((eval_script.SCENARIOS).read_text(encoding="utf-8"))
    for scenario in config["scenario"]:
        outcome = eval_script.run_scenario(HANDBOOK, scenario)
        assert outcome.failures == [], (scenario["name"], outcome.failures)
