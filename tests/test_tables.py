import pytest

from mdpeek import Document, OnTableError
from mdpeek import tables as tables_module
from mdpeek.tables import (
    SelectionError,
    TableNotFound,
    TableSettings,
    parse_row_range,
    resolve_columns,
    should_summarise,
    summary,
)


@pytest.fixture
def doc(fixture_text) -> Document:
    return Document.from_text(fixture_text("tables.md"))


def test_only_top_level_gfm_tables_are_extracted(doc):
    assert [(t.id, t.section_id) for t in doc.tables] == [
        ("T1", "S1"),
        ("T2", "S1.1"),
        ("T3", "S1.2"),
        ("T4", "S1.3"),
    ]


def test_cells_are_unescaped_and_cleaned(doc):
    t4 = doc.table("t4")
    assert t4.rows[0] == ["pipe", "a | b", "`x|y`"]
    assert t4.rows[1] == ["ctrl", "badchar", "ok"]
    assert t4.warnings == ["2 ragged rows fixed", "bad characters removed from 1 cell"]


def test_ragged_rows_are_padded_and_truncated(doc):
    t4 = doc.table("T4")
    assert t4.rows[2] == ["short", "", ""]
    assert t4.rows[3] == ["long", "1", "2"]


def test_types_and_typed_rows(doc):
    t2 = doc.table("T2")
    assert t2.types == ["INTEGER", "TEXT", "REAL"]
    assert t2.typed_rows()[0] == [1, "item 1", 1.5]
    assert t2.to_records()[0] == {"id": 1, "label": "item 1", "ratio": 1.5}


def test_empty_cells_become_none():
    doc = Document.from_text("| a | b |\n|---|---|\n| 1 | |\n| | x |\n")
    assert doc.tables[0].types == ["INTEGER", "TEXT"]
    assert doc.tables[0].typed_rows() == [[1, None], [None, "x"]]


def test_sql_names_from_headers(doc):
    assert doc.table("T3").sql_names[:2] == ["col_1", "col_2"]


def test_sql_names_convert_accents_to_ascii():
    doc = Document.from_text("| Café / Bar | Ñame | 日本 |\n|---|---|---|\n| a | b | c |\n")
    assert doc.tables[0].sql_names == ["cafe_bar", "name", "col_3"]


def test_summary_uses_sql_names_unless_raw():
    doc = Document.from_text("| Item Name | Qty |\n|---|---|\n| a | 1 |\n")
    table = doc.tables[0]
    assert summary(table, TableSettings()).endswith(": item_name, qty")
    assert summary(table, TableSettings(raw_column_names=True)).endswith(": Item Name, Qty")


def test_unknown_table_lists_available(doc):
    with pytest.raises(TableNotFound, match="no table 'T9'; available: T1, T2, T3, T4"):
        doc.table("T9")


def test_unknown_table_without_tables():
    with pytest.raises(TableNotFound, match="no tables"):
        Document.from_text("# A\n").table("T1")


def test_tables_in_scope(doc):
    assert [t.id for t in doc.tables_in(["S1.1", "S1.3"])] == ["T2", "T4"]
    assert [t.id for t in doc.tables_in(["S1"])] == ["T1", "T2", "T3", "T4"]
    assert len(doc.tables_in()) == 4


@pytest.mark.parametrize(
    ("table_id", "expected"),
    [
        ("T1", "[T1] 2×2: key, value"),
        ("T2", "[T2] 3×30: id, label, ratio"),
        ("T3", "[T3] 10×1"),
    ],
)
def test_summary_lines(doc, table_id, expected):
    assert summary(doc.table(table_id), TableSettings()) == expected


def test_summary_drops_long_headers():
    headers = " | ".join(["a_very_long_column_name_here"] * 4)
    doc = Document.from_text(f"| {headers} |\n|---|---|---|---|\n| 1 | 2 | 3 | 4 |\n")
    assert summary(doc.tables[0], TableSettings()) == "[T1] 4×1"
    assert summary(doc.tables[0], TableSettings(header_max_chars=200)).startswith(
        "[T1] 4×1: a_very"
    )


def test_summary_with_section_and_warnings(doc):
    assert summary(doc.table("T4"), TableSettings(), with_section=True) == (
        "[T4] S1.3 3×4: name, note, code (2 ragged rows fixed; bad characters removed from 1 cell)"
    )


def test_thresholds(doc):
    settings = TableSettings()
    assert not should_summarise(doc.table("T1"), settings)
    assert should_summarise(doc.table("T2"), settings)  # rows
    assert should_summarise(doc.table("T3"), settings)  # cols
    assert not should_summarise(doc.table("T2"), TableSettings(summaries=False))
    assert should_summarise(doc.table("T1"), TableSettings(max_rows=1))


def test_settings_coerce_error_policy():
    assert TableSettings(on_error="EXCLUDE").on_error is OnTableError.EXCLUDE
    with pytest.raises(ValueError):
        TableSettings(on_error="drop")


@pytest.fixture
def failing_t2(monkeypatch):
    def hook(table):
        if table.id == "T2":
            raise RuntimeError("forced failure")

    monkeypatch.setattr(tables_module, "build_hook", hook)


def test_failed_table_keeps_its_id(failing_t2, fixture_text):
    doc = Document.from_text(fixture_text("tables.md"))
    assert [t.id for t in doc.tables] == ["T1", "T2", "T3", "T4"]
    t2 = doc.table("T2")
    assert not t2.ok
    assert t2.error == "forced failure"
    assert summary(t2, TableSettings(), with_section=True) == (
        "[T2!] S1.1 not parsed: forced failure"
    )


@pytest.mark.parametrize(
    ("policy", "expected_start"),
    [
        ("show", ["[S1.1] Deep", "[T2!] not parsed: forced failure, raw text below", "| id"]),
        ("summary", ["[S1.1] Deep", "[T2!] not parsed: forced failure"]),
        ("exclude", ["[S1.1] Deep"]),
    ],
)
def test_failed_table_policies(failing_t2, fixture_text, policy, expected_start):
    doc = Document.from_text(fixture_text("tables.md"))
    out = doc.full(sections=["S1.1"], tables=TableSettings(on_error=policy)).splitlines()
    assert [line[: len(e)] for line, e in zip(out, expected_start, strict=False)] == expected_start
    expected_len = {"show": 2 + 32, "summary": 2, "exclude": 1}[policy]
    assert len(out) == expected_len


def test_view_replaces_large_tables_and_labels_small_ones(doc):
    out = doc.full(sections=["S1"], depth=1).splitlines()
    assert out[:4] == ["[S1] Tables", "Narrow table stays inline.", "", "[T1]"]
    assert doc.full(sections=["S1.1"]).splitlines() == [
        "[S1.1] Deep",
        "[T2] 3×30: id, label, ratio",
    ]


def test_no_summaries_shows_tables_verbatim(doc):
    out = doc.full(sections=["S1.1"], tables=TableSettings(summaries=False)).splitlines()
    assert out[1] == "[T2]"
    assert len(out) == 2 + 32


def test_structure_and_stubs_count_tables(doc):
    assert doc.structure(depth=1) == "[S1] Tables (6, 4 sub, 1 tbl)\n"
    assert "  [S1.1] Deep (32 ln, 1 tbl)" in doc.view().splitlines()


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("1", range(0, 1)),
        ("2-4", range(1, 4)),
        ("3-", range(2, 10)),
        ("-2", range(0, 2)),
        ("8-20", range(7, 10)),
        (" 5 - 6 ", range(4, 6)),
    ],
)
def test_row_ranges(spec, expected):
    assert parse_row_range(spec, 10) == expected


@pytest.mark.parametrize("spec", ["", "-", "a", "0", "5-2", "1-2-3"])
def test_invalid_row_ranges(spec):
    with pytest.raises(SelectionError):
        parse_row_range(spec, 10)


def test_resolve_columns_by_sql_name_or_header(doc):
    t3 = doc.table("T3")
    assert resolve_columns(t3, ["col_2", "COL 3"]) == [1, 2]
    with pytest.raises(SelectionError, match="T3 has no column 'nope'; columns: col_1"):
        resolve_columns(t3, ["nope"])


def test_table_inside_preamble_belongs_to_s0():
    doc = Document.from_text("| a |\n|---|\n| 1 |\n\n# A\n")
    assert doc.tables[0].section_id == "S0"


def test_invalid_utf8_file_is_cleaned(tmp_path):
    path = tmp_path / "bad.md"
    path.write_bytes(b"| a | b |\n|---|---|\n| caf\xe9 | x |\n")
    table = Document.from_path(path).tables[0]
    assert table.rows[0] == ["caf", "x"]
    assert table.warnings == ["bad characters removed from 1 cell"]


MIXED = "| value | label |\n|---|---|\n| 1.5 | a |\n| 2 | b |\n| | c |\n| 10 or more | d |\n"


def test_column_stats_and_mixed_columns():
    table = Document.from_text(MIXED).tables[0]
    assert table.types == ["TEXT", "TEXT"]
    assert table.stats[0].numeric == 2
    assert table.stats[0].non_empty == 3
    assert table.stats[0].sample_text == "10 or more"
    assert table.mixed_columns() == [0]


def test_numeric_and_pure_text_columns_are_not_mixed():
    table = Document.from_text("| n | t |\n|---|---|\n| 1 | x |\n| 2.5 | y |\n").tables[0]
    assert table.mixed_columns() == []
