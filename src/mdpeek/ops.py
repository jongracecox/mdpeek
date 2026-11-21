"""Operations shared by the CLI and the MCP tool.

Each function takes typed arguments and returns an :class:`Output`: the text
to show, notes that would go to stderr in the CLI, and what was held back.
Notes here never name a CLI flag; each front end words its own hints from
the ``fit``, ``grouped``, ``selections`` and ``query`` details.

>>> doc = Document.from_text("# A\\nretry once\\n## B\\nno\\n")
>>> print(grep_file(doc, "retry").text, end="")
[S1] A (1 match)
>>> grep_file(doc, "zzz").notes
["grep: no matches for 'zzz'"]
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from mdpeek.diagram_output import render_diagram_list
from mdpeek.engines import QueryResult, run_query
from mdpeek.fences import render_fence_list
from mdpeek.formats import format_rows, to_json
from mdpeek.library import DEFAULT_BUDGET, FileNode, Grouped, Library, TreeFit
from mdpeek.meta import render_meta_list
from mdpeek.model import Document
from mdpeek.options import Engine, Format, coerce
from mdpeek.search import compile_pattern, render_hits, section_hits
from mdpeek.table_output import (
    DEFAULT_LIMIT,
    Selection,
    render_table,
    render_table_list,
    select,
)
from mdpeek.tables import TableSettings

ListKind = Literal["tables", "diagrams", "fences"]

LIST_ITEM = {"tables": "table", "diagrams": "diagram", "fences": "fence"}
"""The item word for each list kind."""


@dataclass
class Output:
    """What an operation produced."""

    text: str
    notes: list[str] = field(default_factory=list)
    """Plain notes (no ``mdpeek:`` prefix, no flag names)."""
    truncated: bool = False
    """Rows, files or items were held back by a limit or budget."""
    fit: TreeFit | None = None
    grouped: Grouped | None = None
    selections: list[Selection] = field(default_factory=list)
    query: QueryResult | None = None
    shown: int | None = None
    """Query rows shown, when ``query`` is set."""


def library_notes(library: Library) -> list[str]:
    """A note for each path the library skipped."""
    return [f"skipped {skipped}" for skipped in library.skipped]


def tree(
    library: Library,
    budget: int | None = None,
    *,
    levels: int | None = None,
    depth: int | None = None,
    first: int | None = None,
) -> Output:
    """The directory tree: fixed when ``levels``, ``depth`` or ``first`` is
    given without a budget, otherwise fitted to ``budget`` lines."""
    notes = library_notes(library)
    if budget is None and any(v is not None for v in (levels, depth, first)):
        return Output(library.tree(levels=levels, first=first, depth=depth), notes)
    budget = budget or DEFAULT_BUDGET
    fit = library.fit(budget, levels=levels, depth=depth, first=first)
    text = library.tree(levels=fit.levels, first=fit.first, depth=fit.depth or None)
    return Output(text, notes, truncated=bool(fit.next_step) or fit.lines > budget, fit=fit)


def grep_file(doc: Document, pattern: str, sections: Sequence[str] | None = None) -> Output:
    """Sections of ``doc`` with lines matching ``pattern``."""
    hits = section_hits(doc, compile_pattern(pattern), sections)
    notes = [] if hits else [f"grep: no matches for {pattern!r}"]
    return Output(render_hits(hits), notes)


def grep_library(
    library: Library, pattern: str, *, first: int | None = None, budget: int | None = None
) -> Output:
    """Matching sections across a directory, files with most matches first."""
    notes = library_notes(library)
    result = library.grep(compile_pattern(pattern), first=first, budget=budget)
    if not result.files:
        notes.append(f"grep: no matches for {pattern!r}")
    return Output(result.text, notes, truncated=_held_back(result, budget, first), grouped=result)


def _held_back(result: Grouped, budget: int | None, first: int | None) -> bool:
    return budget is not None and first is None and result.first is not None


def list_file(
    doc: Document,
    kind: ListKind,
    sections: Sequence[str] | None = None,
    settings: TableSettings | None = None,
    fmt: Format | str = Format.MD,
) -> Output:
    """One line per table, diagram or fenced block in ``doc`` (or ``sections``)."""
    fmt = coerce(Format, fmt)
    if kind == "tables":
        return Output(render_table_list(doc.tables_in(sections), settings or TableSettings(), fmt))
    if kind == "diagrams":
        return Output(render_diagram_list(doc.diagrams_in(sections), fmt))
    return Output(render_fence_list(doc.fences_in(sections), fmt))


def _node_list(node: FileNode, kind: ListKind, settings: TableSettings, fmt: Format) -> str:
    return list_file(node.doc, kind, None, settings, fmt).text


def list_library(
    library: Library,
    kind: ListKind,
    settings: TableSettings | None = None,
    *,
    fmt: Format | str = Format.MD,
    first: int | None = None,
    budget: int | None = None,
) -> Output:
    """Tables, diagrams or fenced blocks across a directory, grouped by file.

    Markdown output is fitted to ``budget``; JSON and JSONL list every item
    with its file's ``path``.
    """
    settings = settings or TableSettings()
    fmt = coerce(Format, fmt)
    notes = library_notes(library)
    if fmt is not Format.MD:
        records = [
            {"path": library.relative(node), **item}
            for node in library.files_in_order()
            for item in json.loads(_node_list(node, kind, settings, Format.JSON))
        ]
        text = "".join(to_json(r) for r in records) if fmt is Format.JSONL else to_json(records)
        return Output(text, notes)
    result = library.items(
        LIST_ITEM[kind],
        lambda node: _node_list(node, kind, settings, Format.MD).splitlines(),
        first,
        budget,
    )
    return Output(result.text, notes, truncated=_held_back(result, budget, first), grouped=result)


def meta_library(library: Library, fmt: Format | str = Format.MD) -> Output:
    """The front matter of every file in a directory that has one."""
    entries = [
        (library.relative(node), node.doc.meta)
        for node in library.files_in_order()
        if node.doc.meta
    ]
    return Output(render_meta_list(entries, fmt), library_notes(library))


def tables(
    doc: Document,
    ids: Sequence[str] | None = None,
    sections: Sequence[str] | None = None,
    *,
    rows: str | None = None,
    cols: Sequence[str] | None = None,
    limit: int | None = None,
    full: bool = False,
    settings: TableSettings | None = None,
    fmt: Format | str = Format.MD,
) -> Output:
    """Tables by ID, or all tables in ``sections``: a summary list, or data
    when IDs, ``rows``, ``cols`` or ``full`` ask for it."""
    settings = settings or TableSettings()
    fmt = coerce(Format, fmt)
    found = [doc.table(t) for t in ids] if ids else doc.tables_in(sections)
    if not (ids or full or rows is not None or cols is not None):
        return Output(render_table_list(found, settings, fmt))
    selections = [select(t, rows=rows, cols=cols, limit=limit, full=full) for t in found]
    raw = settings.raw_column_names
    if fmt is Format.JSON and len(selections) > 1:
        blocks = [render_table(s, fmt, raw_column_names=raw).rstrip("\n") for s in selections]
        text = "[" + ",".join(blocks) + "]\n"
    else:
        separator = "" if fmt is Format.JSONL else "\n"
        text = separator.join(render_table(s, fmt, raw_column_names=raw) for s in selections)
    truncated = any(s.truncated for s in selections)
    return Output(text, truncated=truncated, selections=selections)


def query(
    doc: Document,
    sql: str,
    engine: Engine | str = Engine.AUTO,
    sections: Sequence[str] | None = None,
    *,
    limit: int | None = None,
    full: bool = False,
    fmt: Format | str = Format.MD,
) -> Output:
    """Run ``sql`` over the tables in ``sections`` (``t1``, ``t2``, ...)."""
    fmt = coerce(Format, fmt)
    found = doc.tables_in(sections)
    notes = [f"skipped {t.id} (not parsed: {t.error})" for t in found if not t.ok]
    result = run_query(found, sql, engine)
    notes += result.notes
    cap = result.total if full else (limit or DEFAULT_LIMIT)
    rows = result.rows[:cap]
    if fmt is Format.JSON:
        text = to_json(
            {
                "engine": result.engine.value,
                "columns": result.columns,
                "rows": rows,
                "total": result.total,
                "shown": len(rows),
            }
        )
    else:
        text = format_rows(result.columns, rows, fmt)
    return Output(text, notes, truncated=len(rows) < result.total, query=result, shown=len(rows))
