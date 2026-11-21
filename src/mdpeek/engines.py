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

**Safe mode** (``safe=True``) is for queries written by someone other than
the user, such as a model calling an MCP tool. It allows only read-only
queries: sqlite runs under an allow-list authoriser (``SELECT``, reads,
functions, recursive CTEs; ``ATTACH``, ``PRAGMA`` and writes are refused),
and DuckDB checks the statement type and runs with external access off. A
query is stopped after ``timeout`` seconds (default 10 in safe mode).
"""

from __future__ import annotations

import importlib.util
import os
import re
import sqlite3
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from mdpeek.options import Engine, coerce
from mdpeek.tables import INTEGER, REAL, Table

ENV_VAR = "MDPEEK_ENGINE"

SAFE_TIMEOUT = 10.0
"""Seconds a safe-mode query may run when no ``timeout`` is given."""

READ_ONLY_MESSAGE = "only read-only queries are allowed (SELECT or WITH ... SELECT)"

_SQLITE_ALLOWED = frozenset(
    {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        getattr(sqlite3, "SQLITE_RECURSIVE", 33),
    }
)
_PROGRESS_STEPS = 10_000

_MISSING_TABLE_RE = re.compile(
    r"no such table: (\w+)|Table with name (\w+) does not exist", re.IGNORECASE
)
_DUCKDB_TYPES = {INTEGER: "BIGINT", REAL: "DOUBLE"}
_TYPE_ERROR_RE = re.compile(
    r"Cannot compare values of type|No function matches|Conversion Error|Could not convert"
    r"|explicit cast|datatype mismatch",
    re.IGNORECASE,
)
_UNKNOWN_COLUMN_RE = re.compile(r"no such column|Referenced column .* not found", re.IGNORECASE)
_ALIAS_RE = re.compile(r'\bAS\s+(?:"((?:[^"]|"")+)"|(\w+))', re.IGNORECASE)
_CAST_HINT = {
    Engine.DUCKDB: "try_cast({column} AS DOUBLE)",
    Engine.SQLITE: "CAST({column} AS REAL)",
}


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
    notes: list[str] = field(default_factory=list)
    """Warnings about the query that didn't stop it running."""
    more: bool = False
    """More rows were available than ``max_rows``; ``total`` counts only those kept."""

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
        raise EngineUnavailable(
            "the duckdb engine is not installed; reinstall mdpeek with the duckdb extra, "
            "e.g. uv tool install 'mdpeek[duckdb]' or pip install 'mdpeek[duckdb]'"
        )
    return engine


def run_query(
    tables: Sequence[Table],
    sql: str,
    engine: Engine | str = Engine.AUTO,
    env: Mapping[str, str] | None = None,
    *,
    safe: bool = False,
    timeout: float | None = None,
    max_rows: int | None = None,
) -> QueryResult:
    """Load ``tables`` and run ``sql``. Raises :class:`QueryError` on failure.

    ``safe`` allows only read-only queries (see the module docs). ``timeout``
    stops a query after that many seconds. ``max_rows`` keeps at most that many
    rows and sets :attr:`QueryResult.more` when there were more.
    """
    chosen = resolve_engine(engine, env)
    loaded = [t for t in tables if t.ok]
    skipped = [t for t in tables if not t.ok]
    limits = _Limits(safe, SAFE_TIMEOUT if timeout is None and safe else timeout, max_rows)
    try:
        if chosen is Engine.DUCKDB:
            columns, rows = _run_duckdb(loaded, sql, limits)
        else:
            columns, rows = _run_sqlite(loaded, sql, limits)
    except Exception as exc:
        if isinstance(exc, (QueryError, EngineUnavailable)):
            raise
        raise _query_error(exc, skipped, loaded, sql, chosen, limits) from exc
    more = max_rows is not None and len(rows) > max_rows
    if more:
        rows = rows[:max_rows]
    # sqlite compares TEXT with numbers without complaint, so warn instead.
    notes = type_hints(loaded, sql, chosen, label="note") if chosen is Engine.SQLITE else []
    return QueryResult(columns, rows, chosen, skipped, notes, more)


@dataclass(frozen=True)
class _Limits:
    safe: bool = False
    timeout: float | None = None
    max_rows: int | None = None

    def fetch(self, cursor: Any) -> list[list[Any]]:
        """All rows, or ``max_rows + 1`` so the caller can tell there were more."""
        fetched = (
            cursor.fetchall() if self.max_rows is None else cursor.fetchmany(self.max_rows + 1)
        )
        return [list(row) for row in fetched]


def _query_error(
    exc: Exception,
    skipped: Sequence[Table],
    loaded: Sequence[Table],
    sql: str,
    engine: Engine,
    limits: _Limits | None = None,
) -> QueryError:
    message = str(exc).strip()
    if (
        limits is not None
        and limits.safe
        and re.search(r"not authorized|authorization denied", message, re.IGNORECASE)
    ):
        return QueryError(READ_ONLY_MESSAGE)
    if (
        limits is not None
        and limits.timeout is not None
        and re.search(r"\binterrupt", message, re.IGNORECASE)
    ):
        return QueryError(f"query stopped after {limits.timeout:g}s")
    match = _MISSING_TABLE_RE.search(message)
    if match:
        name = (match.group(1) or match.group(2)).lower()
        for table in skipped:
            if table.sql_name == name:
                return TableUnavailable(f"{table.id} could not be parsed: {table.error}")
    hints = type_hints(loaded, sql, engine) if _TYPE_ERROR_RE.search(message) else []
    if _UNKNOWN_COLUMN_RE.search(message):
        hints += column_name_hints(loaded, sql)
    return QueryError("\n".join([f"SQL error: {message}", *hints]))


def column_name_hints(tables: Sequence[Table], sql: str) -> list[str]:
    """Hints mapping original headers used in ``sql`` to their SQL names."""
    hints: list[str] = []
    for name in dict.fromkeys(_quoted_identifiers(sql)):
        matches = [
            f"{table.sql_name}.{column}"
            for table in tables
            for header, column in zip(table.headers, table.sql_names, strict=True)
            if header.strip().lower() == name.lower() and column != name.lower()
        ]
        if matches:
            hints.append(
                f'hint: "{name}" is a header; in SQL, use its column name {" or ".join(matches)}'
            )
    return hints


def type_hints(tables: Sequence[Table], sql: str, engine: Engine, label: str = "hint") -> list[str]:
    """Hints (or notes) for partly numeric TEXT columns that ``sql`` mentions."""
    hints: list[str] = []
    for table in tables:
        for index in table.mixed_columns():
            column = table.sql_names[index]
            if not re.search(rf"\b{re.escape(column)}\b", sql, re.IGNORECASE):
                continue
            stats = table.stats[index]
            other = stats.non_empty - stats.numeric
            verb = "is" if other == 1 else "are"
            cast = _CAST_HINT[engine].format(column=column)
            hints.append(
                f"{label}: {table.sql_name}.{column} is TEXT because {other} of its "
                f"{stats.non_empty} values {verb} not numeric (e.g. {stats.sample_text!r}); "
                f"compare numbers with {cast}"
            )
    return hints


def _quoted_identifiers(sql: str) -> list[str]:
    """Double-quoted names in ``sql``, skipping single-quoted string literals."""
    names: list[str] = []
    i = 0
    while i < len(sql):
        quote = sql[i]
        if quote not in "'\"":
            i += 1
            continue
        j = i + 1
        text = []
        while j < len(sql):
            if sql[j] == quote:
                if j + 1 < len(sql) and sql[j + 1] == quote:  # doubled quote escapes itself
                    text.append(quote)
                    j += 2
                    continue
                break
            text.append(sql[j])
            j += 1
        if quote == '"':
            names.append("".join(text))
        i = j + 1
    return names


def _check_quoted_names(tables: Sequence[Table], sql: str) -> None:
    """Reject double-quoted names that sqlite would silently read as strings.

    Python 3.12+ switches this sqlite behaviour off instead (see
    :func:`_strict_double_quotes`); this check covers older versions.
    """
    known = {t.sql_name for t in tables}
    known |= {name for t in tables for name in t.sql_names}
    known |= {
        (m.group(1) or m.group(2)).replace('""', '"').lower() for m in _ALIAS_RE.finditer(sql)
    }
    for name in _quoted_identifiers(sql):
        if name.lower() not in known:
            raise sqlite3.OperationalError(f'no such column: "{name}"')


def _strict_double_quotes(connection: sqlite3.Connection) -> bool:
    """Make sqlite treat "x" only as an identifier. False if unsupported."""
    setconfig = getattr(connection, "setconfig", None)
    flag = getattr(sqlite3, "SQLITE_DBCONFIG_DQS_DML", None)
    if setconfig is None or flag is None:
        return False
    setconfig(flag, False)
    return True


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sqlite_authorizer(action: int, *_: object) -> int:
    return sqlite3.SQLITE_OK if action in _SQLITE_ALLOWED else sqlite3.SQLITE_DENY


def _run_sqlite(
    tables: Sequence[Table], sql: str, limits: _Limits | None = None
) -> tuple[list[str], list[list[Any]]]:
    limits = limits or _Limits()
    connection = sqlite3.connect(":memory:")
    try:
        if not _strict_double_quotes(connection):
            _check_quoted_names(tables, sql)
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
        connection.commit()
        if limits.safe:
            connection.set_authorizer(_sqlite_authorizer)
        if limits.timeout is not None:
            deadline = time.monotonic() + limits.timeout
            connection.set_progress_handler(lambda: time.monotonic() > deadline, _PROGRESS_STEPS)
        cursor = connection.execute(sql)
        names = [d[0] for d in cursor.description or []]
        return names, limits.fetch(cursor)
    finally:
        connection.close()


def _run_duckdb(
    tables: Sequence[Table], sql: str, limits: _Limits | None = None
) -> tuple[list[str], list[list[Any]]]:
    import duckdb  # ty: ignore[import-not-found]  (optional extra)

    limits = limits or _Limits()
    config: dict[str, Any] = {"enable_external_access": False} if limits.safe else {}
    connection = duckdb.connect(":memory:", config=config)
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
        if limits.safe:
            connection.execute("SET lock_configuration = true")
            statements = connection.extract_statements(sql)
            if any(st.type != duckdb.StatementType.SELECT for st in statements):
                raise QueryError(READ_ONLY_MESSAGE)
        timer = None
        if limits.timeout is not None:
            timer = threading.Timer(limits.timeout, connection.interrupt)
            timer.start()
        try:
            cursor = connection.execute(sql)
            names = [d[0] for d in cursor.description or []]
            return names, limits.fetch(cursor)
        finally:
            if timer is not None:
                timer.cancel()
    finally:
        connection.close()
