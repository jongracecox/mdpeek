import pytest

from mdpeek import Document, Engine
from mdpeek import engines as engines_module
from mdpeek import tables as tables_module
from mdpeek.engines import (
    EngineUnavailable,
    QueryError,
    TableUnavailable,
    resolve_engine,
    run_query,
)

ENGINES = [
    Engine.SQLITE,
    pytest.param(
        Engine.DUCKDB,
        marks=pytest.mark.skipif(
            not engines_module.duckdb_available(), reason="duckdb extra not installed"
        ),
    ),
]

TEXT = """# Items
| ID | Item Name | Qty | Price | Note |
|----|-----------|-----|-------|------|
| 1 | bolt | 100 | 0.25 | |
| 2 | nut | 250 | 0.1 | spare |
| 3 | washer | 75 | 0.05 | |

## Suppliers
| item_id | supplier |
|---------|----------|
| 1 | Acme |
| 2 | Bolt Co |
"""


@pytest.fixture
def doc() -> Document:
    return Document.from_text(TEXT)


@pytest.mark.parametrize("engine", ENGINES)
def test_typed_columns_and_aggregates(doc, engine):
    result = doc.query(
        "select count(*) as n, sum(qty) as total_qty, max(price) as top from t1", engine
    )
    assert result.engine is engine
    assert result.columns == ["n", "total_qty", "top"]
    assert result.rows == [[3, 425, 0.25]]


@pytest.mark.parametrize("engine", ENGINES)
def test_join_and_nulls(doc, engine):
    result = doc.query(
        "select t1.item_name, t2.supplier, t1.note from t1 "
        "left join t2 on t2.item_id = t1.id order by t1.id",
        engine,
    )
    assert result.rows == [
        ["bolt", "Acme", None],
        ["nut", "Bolt Co", "spare"],
        ["washer", None, None],
    ]


@pytest.mark.parametrize("engine", ENGINES)
def test_section_scope_limits_tables(doc, engine):
    result = doc.query("select count(*) from t2", engine, sections=["S1.1"])
    assert result.rows == [[2]]
    with pytest.raises(QueryError, match="SQL error"):
        doc.query("select * from t1", engine, sections=["S1.1"])


@pytest.mark.parametrize("engine", ENGINES)
def test_empty_table_has_columns(engine):
    doc = Document.from_text("| a | b |\n|---|---|\n")
    assert doc.query("select count(*) from t1", engine).rows == [[0]]


@pytest.mark.parametrize("engine", ENGINES)
def test_failed_table_is_skipped_and_reported(monkeypatch, engine):
    def hook(table):
        if table.id == "T1":
            raise ValueError("bad table")

    monkeypatch.setattr(tables_module, "build_hook", hook)
    doc = Document.from_text(TEXT)
    result = doc.query("select count(*) from t2", engine)
    assert [t.id for t in result.skipped] == ["T1"]
    with pytest.raises(TableUnavailable, match="T1 could not be parsed: bad table"):
        doc.query("select * from t1", engine)


def test_sqlite_and_duckdb_agree(doc):
    if not engines_module.duckdb_available():
        pytest.skip("duckdb extra not installed")
    sql = "select item_name, qty * price as value from t1 order by value desc"
    assert doc.query(sql, "sqlite").rows == doc.query(sql, "duckdb").rows


class TestResolveEngine:
    def test_explicit_sqlite(self):
        assert resolve_engine("sqlite", env={}) is Engine.SQLITE

    def test_auto_prefers_duckdb_when_installed(self, monkeypatch):
        monkeypatch.setattr(engines_module, "duckdb_available", lambda: True)
        assert resolve_engine(Engine.AUTO, env={}) is Engine.DUCKDB

    def test_auto_falls_back_to_sqlite(self, monkeypatch):
        monkeypatch.setattr(engines_module, "duckdb_available", lambda: False)
        assert resolve_engine(Engine.AUTO, env={}) is Engine.SQLITE

    def test_env_overrides_auto(self, monkeypatch):
        monkeypatch.setattr(engines_module, "duckdb_available", lambda: True)
        assert resolve_engine(Engine.AUTO, env={"MDPEEK_ENGINE": "SQLite"}) is Engine.SQLITE

    def test_explicit_overrides_env(self):
        assert resolve_engine("sqlite", env={"MDPEEK_ENGINE": "duckdb"}) is Engine.SQLITE

    def test_missing_duckdb_is_an_error(self, monkeypatch):
        monkeypatch.setattr(engines_module, "duckdb_available", lambda: False)
        with pytest.raises(EngineUnavailable, match=r"mdpeek\[duckdb\]"):
            resolve_engine("duckdb", env={})
        with pytest.raises(EngineUnavailable):
            resolve_engine(Engine.AUTO, env={"MDPEEK_ENGINE": "duckdb"})

    def test_invalid_env_value(self):
        with pytest.raises(ValueError, match="invalid Engine 'bogus'"):
            resolve_engine(Engine.AUTO, env={"MDPEEK_ENGINE": "bogus"})


def test_run_query_without_tables():
    assert run_query([], "select 1 as one", "sqlite").rows == [[1]]


MIXED_DOC = "| value | label |\n|---|---|\n| 1.5 | a |\n| 2 | b |\n| 10 or more | c |\n"


def test_type_hints_name_mentioned_mixed_columns():
    tables = Document.from_text(MIXED_DOC).tables
    hints = engines_module.type_hints(tables, "select * from t1 where VALUE > 3", Engine.DUCKDB)
    assert hints == [
        "hint: t1.value is TEXT because 1 of its 3 values is not numeric "
        "(e.g. '10 or more'); compare numbers with try_cast(value AS DOUBLE)"
    ]
    assert engines_module.type_hints(tables, "select label from t1", Engine.DUCKDB) == []
    sqlite_hint = engines_module.type_hints(tables, "select value from t1", Engine.SQLITE)
    assert sqlite_hint[0].endswith("CAST(value AS REAL)")


def test_type_error_message_gets_hints():
    tables = Document.from_text(MIXED_DOC).tables
    error = engines_module._query_error(
        Exception("Binder Error: Cannot compare values of type VARCHAR and type INTEGER_LITERAL"),
        [],
        tables,
        "select * from t1 where value > 3",
        Engine.DUCKDB,
    )
    assert str(error).splitlines()[1].startswith("hint: t1.value is TEXT")


def test_other_errors_get_no_hints():
    tables = Document.from_text(MIXED_DOC).tables
    error = engines_module._query_error(
        Exception("Parser Error: syntax error"), [], tables, "select value from", Engine.DUCKDB
    )
    assert str(error) == "SQL error: Parser Error: syntax error"


def test_duckdb_comparison_on_mixed_column_explains_itself():
    if not engines_module.duckdb_available():
        pytest.skip("duckdb extra not installed")
    doc = Document.from_text(MIXED_DOC)
    with pytest.raises(QueryError, match=r"hint: t1\.value is TEXT"):
        doc.query("select * from t1 where value > 3", "duckdb")
    rows = doc.query("select label from t1 where try_cast(value as double) > 1.8", "duckdb").rows
    assert rows == [["b"]]


QUOTED_DOC = "| Order ID | Unit Price ($) |\n|---|---|\n| 1 | 9.5 |\n| 2 | 3 |\n"


def test_quoted_identifiers_skip_string_literals():
    sql = 'select "a ""b""", ' + "'not \"this\"', \"c\" from t1 where x = 'it''s'"
    assert engines_module._quoted_identifiers(sql) == ['a "b"', "c"]


@pytest.mark.parametrize("strict", [True, False], ids=["sqlite-config", "text-check"])
def test_sqlite_rejects_unknown_double_quoted_names(monkeypatch, strict):
    if strict and not engines_module._strict_double_quotes(
        engines_module.sqlite3.connect(":memory:")
    ):
        pytest.skip("this Python's sqlite3 cannot switch off double-quoted strings")
    if not strict:
        monkeypatch.setattr(engines_module, "_strict_double_quotes", lambda connection: False)
    doc = Document.from_text(QUOTED_DOC)
    with pytest.raises(QueryError) as exc:
        doc.query('select "Order ID" from t1', "sqlite")
    lines = str(exc.value).splitlines()
    assert lines[0].startswith('SQL error: no such column: "Order ID"')
    assert lines[1] == 'hint: "Order ID" is a header; in SQL, use its column name t1.order_id'
    # quoted real names, table names and aliases still work
    sql = 'select "order_id", "unit_price" * 2 as "Double" from "t1" order by "Double" desc'
    assert doc.query(sql, "sqlite").rows == [[1, 19.0], [2, 6.0]]


def test_duplicate_headers_share_one_hint():
    doc = Document.from_text("| Order ID | Order ID |\n|---|---|\n| 1 | 2 |\n")
    hints = engines_module.column_name_hints(doc.tables, 'select "Order ID" from t1')
    assert hints == [
        'hint: "Order ID" is a header; in SQL, use its column name t1.order_id or t1.order_id_2'
    ]


def test_sqlite_notes_on_partly_numeric_columns():
    doc = Document.from_text(MIXED_DOC)
    result = doc.query("select label from t1 where value > 1.8", "sqlite")
    assert result.notes == [
        "note: t1.value is TEXT because 1 of its 3 values is not numeric "
        "(e.g. '10 or more'); compare numbers with CAST(value AS REAL)"
    ]
    assert doc.query("select label from t1", "sqlite").notes == []


def test_duckdb_success_has_no_notes():
    if not engines_module.duckdb_available():
        pytest.skip("duckdb extra not installed")
    doc = Document.from_text(MIXED_DOC)
    assert doc.query("select value from t1", "duckdb").notes == []


def test_duckdb_unknown_header_gets_a_hint():
    if not engines_module.duckdb_available():
        pytest.skip("duckdb extra not installed")
    doc = Document.from_text(QUOTED_DOC)
    with pytest.raises(QueryError, match=r'hint: "Order ID" is a header.*t1\.order_id'):
        doc.query('select "Order ID" from t1', "duckdb")


def test_install_hint_does_not_assume_pip(monkeypatch):
    monkeypatch.setattr(engines_module, "duckdb_available", lambda: False)
    with pytest.raises(EngineUnavailable) as exc:
        resolve_engine("duckdb", env={})
    assert "uv tool install 'mdpeek[duckdb]'" in str(exc.value)
    assert "pip install 'mdpeek[duckdb]'" in str(exc.value)


# Safe mode: read-only queries for SQL written by someone other than the user.

UNSAFE = [
    "attach database '{dir}/x.db' as x",
    "vacuum into '{dir}/x.db'",
    "pragma table_info(t1)",
    "insert into t1 values (9, 'x', 1, 1, '')",
    "create table z (a int)",
    "copy t1 to '{dir}/x.csv'",
]


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("sql", UNSAFE)
def test_safe_mode_refuses_anything_but_reads(doc, engine, sql, tmp_path):
    with pytest.raises(QueryError):
        run_query(doc.tables, sql.format(dir=tmp_path), engine, safe=True)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("engine", ENGINES)
def test_safe_mode_names_the_rule(doc, engine):
    with pytest.raises(QueryError, match="only read-only queries"):
        run_query(doc.tables, "pragma table_info(t1)", engine, safe=True)


@pytest.mark.parametrize("engine", ENGINES)
def test_safe_mode_still_allows_joins_and_ctes(doc, engine):
    sql = (
        "with recursive c(n) as (select 1 union all select n + 1 from c where n < 2) "
        "select t1.item_name, t2.supplier, c.n from t1 join t2 on t1.id = t2.item_id "
        "join c on c.n = t1.id order by 1"
    )
    result = run_query(doc.tables, sql, engine, safe=True)
    assert result.rows == [["bolt", "Acme", 1], ["nut", "Bolt Co", 2]]


@pytest.mark.parametrize("engine", ENGINES)
def test_safe_mode_blocks_file_reads(engine, tmp_path):
    secret = tmp_path / "secret.csv"
    secret.write_text("a\n1\n")
    with pytest.raises(QueryError):
        run_query([], f"select * from read_csv('{secret}')", engine, safe=True)


@pytest.mark.parametrize("engine", ENGINES)
def test_timeout_stops_a_runaway_query(engine):
    sql = "with recursive c(n) as (select 1 union all select n + 1 from c) select count(*) from c"
    with pytest.raises(QueryError, match=r"query stopped after 0\.5s"):
        run_query([], sql, engine, timeout=0.5)


@pytest.mark.parametrize("engine", ENGINES)
def test_max_rows_keeps_the_first_rows_and_says_there_are_more(doc, engine):
    result = run_query(doc.tables, "select id from t1 order by id", engine, max_rows=2)
    assert result.rows == [[1], [2]]
    assert result.more
    assert not run_query(doc.tables, "select id from t1", engine, max_rows=3).more


def test_unsafe_mode_is_unchanged(doc):
    assert run_query(doc.tables, "pragma table_info(t2)", "sqlite").rows
