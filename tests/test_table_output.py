import json

import pytest

from mdpeek import Document
from mdpeek import tables as tables_module
from mdpeek.table_output import (
    DEFAULT_LIMIT,
    PREVIEW_ROWS,
    render_table,
    render_table_list,
    select,
    truncation_note,
)
from mdpeek.tables import TableSettings


@pytest.fixture
def doc(fixture_text) -> Document:
    return Document.from_text(fixture_text("tables.md"))


def test_preview_by_default(doc):
    sel = select(doc.table("T2"))
    assert len(sel.rows) == PREVIEW_ROWS
    assert sel.truncated
    assert truncation_note(sel) == (
        "mdpeek: T2: showing 5 of 30 rows (use --rows, --limit or --full)"
    )


def test_full_shows_every_row(doc):
    sel = select(doc.table("T2"), full=True, limit=3)
    assert len(sel.rows) == 30
    assert truncation_note(sel) is None


def test_explicit_rows_use_the_default_limit():
    rows = "\n".join(f"| {i} |" for i in range(80))
    table = Document.from_text(f"| n |\n|---|\n{rows}\n").tables[0]
    assert len(select(table, rows="1-80").rows) == DEFAULT_LIMIT
    assert len(select(table, cols=["n"], limit=7).rows) == 7


def test_preview_respects_a_smaller_limit(doc):
    assert len(select(doc.table("T2"), limit=2).rows) == 2


def test_markdown_block_has_header_schema_and_rows(doc):
    out = render_table(select(doc.table("T2"), rows="2"), "md")
    assert out == (
        "[T2] S1.1 table 3 cols × 30 rows\n"
        "columns: id INTEGER, label TEXT, ratio REAL\n"
        "| id | label | ratio |\n|---|---|---|\n| 2 | item 2 | 2.5 |\n"
    )


def test_sql_names_by_default_and_originals_on_request():
    doc = Document.from_text("| Owner Name | N |\n|---|---|\n| a | 1 |\n")
    default = render_table(select(doc.tables[0]), "md").splitlines()
    assert default[1:3] == ["columns: owner_name TEXT, n INTEGER", "| owner_name | n |"]
    raw = render_table(select(doc.tables[0]), "md", raw_column_names=True).splitlines()
    # case-only differences are not repeated in quotes
    assert raw[1:3] == ['columns: owner_name TEXT ("Owner Name"), n INTEGER', "| Owner Name | N |"]


def test_json_object(doc):
    data = json.loads(render_table(select(doc.table("T2"), rows="1", cols=["ratio"]), "json"))
    assert data == {
        "id": "T2",
        "section": "S1.1",
        "columns": ["ratio"],
        "names": ["ratio"],
        "types": ["REAL"],
        "rows": [[1.5]],
        "total": 30,
        "shown": 1,
        "warnings": [],
    }


def test_csv_is_plain_data(doc):
    assert render_table(select(doc.table("T1")), "csv") == "key,value\na,1\nb,2\n"


def test_list_lines_and_json(doc):
    settings = TableSettings()
    lines = render_table_list(doc.tables, settings, "md").splitlines()
    assert lines[0] == "[T1] S1 table 2 cols × 2 rows: key, value"
    objects = json.loads(render_table_list(doc.tables, settings, "json"))
    assert [o["id"] for o in objects] == ["T1", "T2", "T3", "T4"]
    assert objects[3]["warnings"] == ["2 ragged rows fixed", "bad characters removed from 1 cell"]
    assert len(render_table_list(doc.tables, settings, "jsonl").splitlines()) == 4


def test_failed_table_output(monkeypatch, fixture_text):
    monkeypatch.setattr(
        tables_module,
        "build_hook",
        lambda t: (_ for _ in ()).throw(RuntimeError("boom")) if t.id == "T1" else None,
    )
    doc = Document.from_text(fixture_text("tables.md"))
    out = render_table(select(doc.table("T1")), "md")
    assert out.splitlines()[:2] == ["[T1!] S1 table not parsed: boom", "| key | value |"]
    data = json.loads(render_table(select(doc.table("T1")), "json"))
    assert data["error"] == "boom"
    assert data["raw"].startswith("| key | value |\n")


def test_schema_flags_partly_numeric_text_columns():
    doc = Document.from_text("| value | label |\n|---|---|\n| 1.5 | a |\n| 10 or more | b |\n")
    out = render_table(select(doc.tables[0]), "md").splitlines()
    assert out[1] == "columns: value TEXT (1/2 numeric), label TEXT"
