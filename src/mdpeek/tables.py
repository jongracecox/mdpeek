"""GFM tables: extraction, typing, summaries and row/column selection.

Only tables at the top block level are extracted (as with headings, a table
inside a blockquote or list item stays plain content). Table IDs ``T1..Tn``
run through the whole document in order.

Recoverable problems are fixed and recorded as warnings: ragged rows are
padded or truncated to the header width (as GFM does), and control or
invalid characters are removed. A table that cannot be built at all keeps its
ID and gets an ``error`` instead, so numbering never shifts.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from markdown_it.token import Token

from mdpeek.options import OnTableError, coerce

Value = int | float | str | None

INTEGER, REAL, TEXT = "INTEGER", "REAL", "TEXT"

_INT_RE = re.compile(r"^[+-]?\d+$")
_REAL_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_REPLACEMENT = "�"
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")

#: Test hook: called with each table after it is built; raising marks the
#: table as failed. Lets the error path be tested deterministically.
build_hook: Callable[[Table], None] | None = None


class TableNotFound(KeyError):
    """Raised when a table ID does not exist in the document."""

    def __init__(self, table_id: str, available: list[str]) -> None:
        self.table_id = table_id
        self.available = available
        hint = f"; available: {', '.join(available)}" if available else "; no tables"
        super().__init__(f"no table {table_id!r}{hint}")

    def __str__(self) -> str:
        return str(self.args[0])


class SelectionError(ValueError):
    """Raised for an invalid row range or unknown column."""


@dataclass
class TableSettings:
    """How tables are shown in view and full output."""

    summaries: bool = True
    max_cols: int = 6
    max_rows: int = 10
    header_max_chars: int = 80
    on_error: OnTableError | str = OnTableError.SHOW

    def __post_init__(self) -> None:
        self.on_error = coerce(OnTableError, self.on_error)


@dataclass(eq=False)
class Table:
    """A GFM table and where it sits in the document."""

    id: str
    section_id: str
    start: int
    end: int
    """Source line span (half-open)."""
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    sql_names: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def n_cols(self) -> int:
        return len(self.headers)

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    @property
    def sql_name(self) -> str:
        """The table's name in SQL queries (``t1`` for ``T1``)."""
        return self.id.lower()

    def typed_rows(self) -> list[list[Value]]:
        """Rows with values converted to their column's inferred type."""
        return [
            [_convert(cell, kind) for cell, kind in zip(row, self.types, strict=True)]
            for row in self.rows
        ]

    def to_records(self) -> list[dict[str, Value]]:
        """Typed rows as dicts keyed by SQL column name."""
        return [dict(zip(self.sql_names, row, strict=True)) for row in self.typed_rows()]


def build_tables(
    tokens: Sequence[Token], lines: list[str], section_of: Callable[[int], str]
) -> list[Table]:
    """Extract top-level tables from a markdown-it token stream."""
    tables: list[Table] = []
    for i, token in enumerate(tokens):
        if token.type != "table_open" or token.level != 0 or token.map is None:
            continue
        start, end = token.map
        table = Table(id=f"T{len(tables) + 1}", section_id=section_of(start), start=start, end=end)
        try:
            _fill(table, tokens, i, lines)
            if build_hook is not None:
                build_hook(table)
        except Exception as exc:  # any failure becomes a table error, never a crash
            table.error = str(exc) or type(exc).__name__
        tables.append(table)
    return tables


def _fill(table: Table, tokens: Sequence[Token], open_index: int, lines: list[str]) -> None:
    rows: list[tuple[int, list[str]]] = []
    current: list[str] | None = None
    row_line = 0
    for token in tokens[open_index + 1 :]:
        if token.type == "table_close":
            break
        if token.type == "tr_open":
            current = []
            row_line = token.map[0] if token.map else row_line
        elif token.type == "inline" and current is not None:
            current.append(token.content)
        elif token.type == "tr_close" and current is not None:
            rows.append((row_line, current))
            current = None
    if not rows:
        raise ValueError("table has no header row")

    cleaned_cells = 0
    clean_rows: list[list[str]] = []
    for _, cells in rows:
        clean: list[str] = []
        for cell in cells:
            fixed = _CONTROL_RE.sub("", cell).replace(_REPLACEMENT, "").strip()
            cleaned_cells += fixed != cell.strip()
            clean.append(fixed)
        clean_rows.append(clean)

    table.headers = clean_rows[0]
    table.rows = clean_rows[1:]
    width = len(table.headers)
    ragged = sum(_raw_cell_count(lines[line]) != width for line, _ in rows[1:])
    if ragged:
        table.warnings.append(f"{ragged} ragged row{'s' if ragged != 1 else ''} fixed")
    if cleaned_cells:
        plural = "s" if cleaned_cells != 1 else ""
        table.warnings.append(f"bad characters removed from {cleaned_cells} cell{plural}")
    table.sql_names = sql_names(table.headers)
    table.types = [infer_type(row[i] for row in table.rows) for i in range(width)]


def _raw_cell_count(line: str) -> int:
    """Count the cells written on a source row (before GFM pads or truncates)."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    return len(_UNESCAPED_PIPE_RE.split(text))


def sql_names(headers: Sequence[str]) -> list[str]:
    """Lowercase snake_case column names, unique and safe for SQL.

    >>> sql_names(["Owner Name", "owner-name", "2nd", "", "ID"])
    ['owner_name', 'owner_name_2', 'c_2nd', 'col_4', 'id']
    """
    names: list[str] = []
    seen: dict[str, int] = {}
    for index, header in enumerate(headers, start=1):
        base = re.sub(r"[^0-9a-z]+", "_", header.lower()).strip("_") or f"col_{index}"
        if base[0].isdigit():
            base = f"c_{base}"
        name = base
        if name in seen:
            seen[base] += 1
            name = f"{base}_{seen[base]}"
        seen.setdefault(name, 1)
        names.append(name)
    return names


def infer_type(cells: Any) -> str:
    """INTEGER or REAL if every non-empty cell parses as one, else TEXT.

    >>> infer_type(["1", "", "-3"]), infer_type(["1", "2.5"]), infer_type(["1", "x"])
    ('INTEGER', 'REAL', 'TEXT')
    """
    values = [cell for cell in cells if cell != ""]
    if not values:
        return TEXT
    if all(_INT_RE.match(v) for v in values):
        return INTEGER
    if all(_REAL_RE.match(v) for v in values):
        return REAL
    return TEXT


def _convert(cell: str, kind: str) -> Value:
    if cell == "":
        return None
    if kind == INTEGER:
        return int(cell)
    if kind == REAL:
        return float(cell)
    return cell


def summary(table: Table, settings: TableSettings, *, with_section: bool = False) -> str:
    """One-line description of a table, e.g. ``[T1] table 4 cols × 32 rows: a, b``."""
    where = f" {table.section_id}" if with_section else ""
    if not table.ok:
        return f"[{table.id}!]{where} table not parsed: {table.error}"
    text = (
        f"[{table.id}]{where} table {_plural(table.n_cols, 'col')} × {_plural(table.n_rows, 'row')}"
    )
    joined = ", ".join(table.headers)
    if table.n_cols <= settings.max_cols and len(joined) <= settings.header_max_chars:
        text += f": {joined}"
    if table.warnings:
        text += f" ({'; '.join(table.warnings)})"
    return text


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def should_summarise(table: Table, settings: TableSettings) -> bool:
    """Whether view/full output replaces this table with its summary line."""
    if not table.ok:
        return True
    return settings.summaries and (
        table.n_cols > settings.max_cols or table.n_rows > settings.max_rows
    )


def parse_row_range(spec: str, total: int) -> range:
    """Turn a 1-based inclusive spec (``5``, ``10-30``, ``10-``, ``-5``) into indexes.

    >>> parse_row_range("2-3", 10), parse_row_range("8-", 10), parse_row_range("-2", 10)
    (range(1, 3), range(7, 10), range(0, 2))
    """
    match = re.fullmatch(r"\s*(\d*)\s*(-?)\s*(\d*)\s*", spec)
    if not match or not (match.group(1) or match.group(3)):
        raise SelectionError(f"invalid row range {spec!r}; use N, A-B, A- or -B")
    first, dash, last = match.groups()
    start = int(first) if first else 1
    stop = (int(last) if last else total) if dash else start
    if start < 1 or stop < start:
        raise SelectionError(f"invalid row range {spec!r}")
    return range(start - 1, min(stop, total))


def resolve_columns(table: Table, wanted: Sequence[str]) -> list[int]:
    """Indexes for column names given as SQL names or original headers."""
    lookup: dict[str, int] = {}
    for index, (name, header) in enumerate(zip(table.sql_names, table.headers, strict=True)):
        lookup.setdefault(name, index)
        lookup.setdefault(header.strip().lower(), index)
    indexes: list[int] = []
    for column in wanted:
        key = column.strip().lower()
        if key not in lookup:
            raise SelectionError(
                f"{table.id} has no column {column!r}; columns: {', '.join(table.sql_names)}"
            )
        indexes.append(lookup[key])
    return indexes
