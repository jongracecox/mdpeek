"""Output formatting for table and query results.

>>> print(format_rows(["a", "b"], [[1, None], ["x|y", 2.5]], Format.MD), end="")
| a | b |
|---|---|
| 1 |  |
| x\\|y | 2.5 |
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence
from typing import Any

from mdpeek.options import Format, coerce


def format_rows(
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
    fmt: Format | str,
    keys: Sequence[str] | None = None,
) -> str:
    """Format ``rows`` as md, csv, tsv or jsonl text ending in a newline.

    ``keys`` names the JSON Lines fields (default: ``columns``). Use
    :func:`to_json` for the ``json`` format, which needs an envelope.
    """
    fmt = coerce(Format, fmt)
    if fmt is Format.MD:
        return _markdown(columns, rows)
    if fmt in (Format.CSV, Format.TSV):
        return _delimited(columns, rows, "," if fmt is Format.CSV else "\t")
    if fmt is Format.JSONL:
        names = list(keys or columns)
        return "".join(to_json(dict(zip(names, row, strict=True))) for row in rows)
    raise ValueError("format_rows does not produce json; use to_json")


def to_json(value: Any) -> str:
    """Compact JSON on one line, ending in a newline."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"


def _cell(value: Any) -> str:
    return "" if value is None else str(value)


def _markdown(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    def line(values: Sequence[Any]) -> str:
        cells = (_cell(v).replace("|", "\\|").replace("\n", " ") for v in values)
        return "| " + " | ".join(cells) + " |"

    out = [line(columns), "|" + "---|" * len(columns), *(line(row) for row in rows)]
    return "\n".join(out) + "\n"


def _delimited(columns: Sequence[str], rows: Sequence[Sequence[Any]], delimiter: str) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows([_cell(v) for v in row] for row in rows)
    return buffer.getvalue()
