"""Counts in compact output, such as ``53 ln, 6 sec, 1 tbl``.

These labels repeat on every line of a large directory scan, so the long
units are abbreviated, and abbreviations take no plural. Units that are
already short stay words and pluralise as usual.

>>> count(53, "line"), count(1, "table"), count(2, "file"), count(1, "dir")
('53 ln', '1 tbl', '2 files', '1 dir')
>>> shape(4, 32)
'4×32'
"""

from __future__ import annotations

ABBREVIATIONS = {"line": "ln", "section": "sec", "table": "tbl", "diagram": "diag"}


def count(n: int, unit: str) -> str:
    """``n`` with its unit, abbreviated where :data:`ABBREVIATIONS` has one."""
    short = ABBREVIATIONS.get(unit)
    if short is not None:
        return f"{n} {short}"
    return f"{n} {unit}" if n == 1 else f"{n} {unit}s"


def shape(cols: int, rows: int) -> str:
    """A table's size as columns × rows, like a matrix."""
    return f"{cols}×{rows}"
