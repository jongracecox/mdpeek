"""SQL over a document's tables.

Each table that parsed is loaded into an in-memory database as ``t1``,
``t2``, … with its inferred column types, then the query runs against them.

Engines:

- **sqlite** (standard library, always available)
- **duckdb** (optional: ``pip install mdpeek[duckdb]``), imported only when used

``Engine.AUTO`` picks DuckDB when it is installed, otherwise sqlite. The
``MDPEEK_ENGINE`` environment variable overrides AUTO; an explicit engine
overrides both. Asking for DuckDB when it is missing is an error, never a
silent fallback.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from mdpeek.options import Engine, coerce
from mdpeek.tables import INTEGER, REAL, Table

ENV_VAR = "MDPEEK_ENGINE"

_MISSING_TABLE_RE = re.compile(
    r"no such table: (\w+)|Table with name (\w+) does not exist", re.IGNORECASE
)
_DUCKDB_TYPES = {INTEGER: "BIGINT", REAL: "DOUBLE"}


class QueryError(ValueError):
    """The query failed (syntax error, unknown column, ...)."""


class TableUnavailable(QueryError):
    """The query used a table that could not be parsed."""


class EngineUnavailable(RuntimeError):
    """The requested engine is not installed."""


@dataclass
class QueryResult:
    """Columns and rows returned by a query, and which engine ran it."""

    columns: list[str]
    rows: list[list[Any]]
    engine: Engine
    skipped: list[Table] = field(default_factory=list)
    """Tables left out of the database because they failed to parse."""

    @property
    def total(self) -> int:
        return len(self.rows)


def duckdb_available() -> bool:
    return importlib.util.find_spec("duckdb") is not None


def resolve_engine(
    engine: Engine | str = Engine.AUTO, env: Mapping[str, str] | None = None
) -> Engine:
    """The concrete engine (SQLITE or DUCKDB) to use for ``engine``."""
    engine = coerce(Engine, engine)
    if engine is Engine.AUTO:
        configured = (os.environ if env is None else env).get(ENV_VAR, "").strip()
        if configured:
            engine = coerce(Engine, configured)
    if engine is Engine.AUTO:
        return Engine.DUCKDB if duckdb_available() else Engine.SQLITE
    if engine is Engine.DUCKDB and not duckdb_available():
        raise EngineUnavailable("the duckdb engine needs: pip install 'mdpeek[duckdb]'")
    return engine


def run_query(
    tables: Sequence[Table],
    sql: str,
    engine: Engine | str = Engine.AUTO,
    env: Mapping[str, str] | None = None,
) -> QueryResult:
    """Load ``tables`` and run ``sql``. Raises :class:`QueryError` on failure."""
    chosen = resolve_engine(engine, env)
    loaded = [t for t in tables if t.ok]
    skipped = [t for t in tables if not t.ok]
    try:
        if chosen is Engine.DUCKDB:
            columns, rows = _run_duckdb(loaded, sql)
        else:
            columns, rows = _run_sqlite(loaded, sql)
    except Exception as exc:
        if isinstance(exc, (QueryError, EngineUnavailable)):
            raise
        raise _query_error(exc, skipped) from exc
    return QueryResult(columns, rows, chosen, skipped)


def _query_error(exc: Exception, skipped: Sequence[Table]) -> QueryError:
    message = str(exc).strip()
    match = _MISSING_TABLE_RE.search(message)
    if match:
        name = (match.group(1) or match.group(2)).lower()
        for table in skipped:
            if table.sql_name == name:
                return TableUnavailable(f"{table.id} could not be parsed: {table.error}")
    return QueryError(f"SQL error: {message}")


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _run_sqlite(tables: Sequence[Table], sql: str) -> tuple[list[str], list[list[Any]]]:
    connection = sqlite3.connect(":memory:")
    try:
        for table in tables:
            columns = ", ".join(
                f"{_quote(name)} {kind}"
                for name, kind in zip(table.sql_names, table.types, strict=True)
            )
            connection.execute(f"CREATE TABLE {_quote(table.sql_name)} ({columns})")
            placeholders = ", ".join("?" * table.n_cols)
            connection.executemany(
                f"INSERT INTO {_quote(table.sql_name)} VALUES ({placeholders})",
                table.typed_rows(),
            )
        cursor = connection.execute(sql)
        names = [d[0] for d in cursor.description or []]
        return names, [list(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def _run_duckdb(tables: Sequence[Table], sql: str) -> tuple[list[str], list[list[Any]]]:
    import duckdb  # ty: ignore[import-not-found]  (optional extra)

    connection = duckdb.connect(":memory:")
    try:
        for table in tables:
            columns = ", ".join(
                f"{_quote(name)} {_DUCKDB_TYPES.get(kind, 'VARCHAR')}"
                for name, kind in zip(table.sql_names, table.types, strict=True)
            )
            connection.execute(f"CREATE TABLE {_quote(table.sql_name)} ({columns})")
            if table.rows:
                placeholders = ", ".join("?" * table.n_cols)
                connection.executemany(
                    f"INSERT INTO {_quote(table.sql_name)} VALUES ({placeholders})",
                    table.typed_rows(),
                )
        cursor = connection.execute(sql)
        names = [d[0] for d in cursor.description or []]
        return names, [list(row) for row in cursor.fetchall()]
    finally:
        connection.close()
