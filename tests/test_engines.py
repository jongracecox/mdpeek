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
