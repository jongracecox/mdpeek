"""Show tables on demand: selection of rows and columns, and formatting.

Used by ``mdpeek --table`` / ``--tables``. Text formats (md, csv, tsv) show
cells exactly as written; JSON formats use typed values.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from mdpeek.formats import format_rows, to_json
from mdpeek.options import Format, coerce
from mdpeek.tables import Table, TableSettings, parse_row_range, resolve_columns, summary

PREVIEW_ROWS = 5
DEFAULT_LIMIT = 50
_NO_HEADER_NAMES = TableSettings(header_max_chars=-1)


@dataclass
class Selection:
    """Which rows and columns of a table to show."""

    table: Table
    columns: list[int]
    rows: list[int]
    """Row indexes to show, after any limit."""
    matched: int
    """Rows matched before the limit was applied."""

    @property
    def truncated(self) -> bool:
        return len(self.rows) < self.matched


def select(
    table: Table,
    rows: str | None = None,
    cols: Sequence[str] | None = None,
    limit: int | None = None,
    full: bool = False,
) -> Selection:
    """Pick rows and columns.

    With no ``rows``, ``cols`` or ``full`` this is a preview of the first
    few rows. ``full`` lifts the row limit. Raises
    :class:`~mdpeek.tables.SelectionError` for a bad range or column.
    """
    columns = resolve_columns(table, cols) if cols else list(range(table.n_cols))
    picked = list(parse_row_range(rows, table.n_rows) if rows else range(table.n_rows))
    if full:
        cap = len(picked)
    elif rows or cols:
        cap = DEFAULT_LIMIT if limit is None else limit
    else:
        cap = min(PREVIEW_ROWS, limit) if limit is not None else PREVIEW_ROWS
    return Selection(table, columns, picked[:cap], len(picked))


def render_table(
    selection: Selection,
    fmt: Format | str,
    *,
    schema: bool = True,
    raw_column_names: bool = False,
) -> str:
    """One table's output. A failed table shows its error and raw text.

    Columns are shown by their SQL names unless ``raw_column_names``.
    """
    fmt = coerce(Format, fmt)
    table = selection.table
    if not table.ok:
        return _failed(table, fmt)

    shown = table.display_headers(raw_column_names)
    headers = [shown[i] for i in selection.columns]
    if fmt in (Format.JSON, Format.JSONL):
        names = [table.sql_names[i] for i in selection.columns]
        typed = table.typed_rows()
        values = [[typed[r][c] for c in selection.columns] for r in selection.rows]
        if fmt is Format.JSONL:
            return format_rows(headers, values, fmt, keys=names)
        return to_json(_json_object(table, selection, headers, names, values))

    cells = [[table.rows[r][c] for c in selection.columns] for r in selection.rows]
    data = format_rows(headers, cells, fmt)
    if fmt is not Format.MD:
        return data
    lines = [summary(table, _NO_HEADER_NAMES, with_section=True)]
    if schema:
        specs = (_column_spec(table, i, raw_column_names) for i in selection.columns)
        lines.append("columns: " + ", ".join(specs))
    return "\n".join(lines) + "\n" + data


def truncation_note(selection: Selection) -> str | None:
    """A note for stderr when rows were held back by the limit."""
    if not selection.truncated:
        return None
    return (
        f"mdpeek: {selection.table.id}: showing {len(selection.rows)} of "
        f"{selection.matched} rows (use --rows, --limit or --full)"
    )


def render_table_list(tables: Sequence[Table], settings: TableSettings, fmt: Format | str) -> str:
    """One line (or JSON object) per table, for ``--tables`` with no data flags."""
    fmt = coerce(Format, fmt)
    if fmt in (Format.JSON, Format.JSONL):
        objects = [_describe(t, settings.raw_column_names) for t in tables]
        if fmt is Format.JSONL:
            return "".join(to_json(o) for o in objects)
        return to_json(objects)
    return "".join(summary(t, settings, with_section=True) + "\n" for t in tables)


def _column_spec(table: Table, index: int, raw_column_names: bool) -> str:
    name, header = table.sql_names[index], table.headers[index]
    spec = f"{name} {table.types[index]}"
    if index in table.mixed_columns():
        stats = table.stats[index]
        spec += f" ({stats.numeric}/{stats.non_empty} numeric)"
    if not raw_column_names or header.strip().lower() == name:
        return spec
    return f'{spec} ("{header}")'


def _json_object(
    table: Table,
    selection: Selection,
    headers: list[str],
    names: list[str],
    values: list[list[Any]],
) -> dict[str, Any]:
    return {
        "id": table.id,
        "section": table.section_id,
        "columns": headers,
        "names": names,
        "types": [table.types[i] for i in selection.columns],
        "rows": values,
        "total": table.n_rows,
        "shown": len(values),
        "warnings": table.warnings,
    }


def _describe(table: Table, raw_column_names: bool) -> dict[str, Any]:
    return {
        "id": table.id,
        "section": table.section_id,
        "cols": table.n_cols,
        "rows": table.n_rows,
        "columns": table.display_headers(raw_column_names),
        "names": table.sql_names,
        "types": table.types,
        "warnings": table.warnings,
        "error": table.error,
    }


def _failed(table: Table, fmt: Format) -> str:
    raw = table.raw_text
    if fmt in (Format.JSON, Format.JSONL):
        return to_json(
            {"id": table.id, "section": table.section_id, "error": table.error, "raw": raw}
        )
    return summary(table, _NO_HEADER_NAMES, with_section=True) + "\n" + raw
