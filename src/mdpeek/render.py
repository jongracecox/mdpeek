"""Render a :class:`~mdpeek.model.Document` in one of the three modes.

Output is compact text. Headings become ``[ID] Title`` lines, indented two
spaces per level below the scope root. Body text is copied as written, with
blank lines at its start and end dropped.

- **view**: content down to ``depth`` (default 1); the next level is listed
  as stubs with line counts.
- **structure**: heading lines only, down to ``depth`` (default: all).
- **full**: content down to ``depth`` (default: all), nothing deeper.

>>> from mdpeek.parse import parse
>>> doc = parse("# A\\nIntro.\\n## B\\nOne.\\nTwo.\\n")
>>> print(render(doc), end="")
[S1] A
Intro.
  [S1.1] B (2 lines)
>>> print(render(doc, Mode.STRUCTURE), end="")
[S1] A (1)
  [S1.1] B (2)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from mdpeek.model import Document, Section
from mdpeek.options import Mode, OnTableError, coerce
from mdpeek.tables import Table, TableSettings, should_summarise, summary

INDENT = "  "
DEFAULT_VIEW_DEPTH = 1


def render(
    doc: Document,
    mode: Mode | str = Mode.VIEW,
    depth: int | None = None,
    sections: Iterable[str] | None = None,
    tables: TableSettings | None = None,
) -> str:
    """Render ``doc`` and return the text, ending in a newline if not empty.

    ``sections`` limits output to those section IDs; depth then counts from
    each one (the section itself is depth 1). ``tables`` controls table
    summaries in view and full modes (default :class:`TableSettings`). Raises
    :class:`~mdpeek.model.SectionNotFound` for an unknown ID and
    ``ValueError`` for a depth below 1.
    """
    mode = coerce(Mode, mode)
    if depth is not None and depth < 1:
        raise ValueError(f"depth must be at least 1, got {depth}")
    if depth is None and mode is Mode.VIEW:
        depth = DEFAULT_VIEW_DEPTH

    ctx = _Context(doc, mode, depth, tables or TableSettings())
    out: list[str] = []
    for root in _roots(doc, sections):
        _render_section(ctx, root, 1, out)
    return "".join(f"{line}\n" for line in out)


def _roots(doc: Document, section_ids: Iterable[str] | None) -> list[Section]:
    if section_ids is None:
        return list(doc.sections)
    roots: list[Section] = []
    for section_id in section_ids:
        section = doc.get(section_id)
        if section not in roots:
            roots.append(section)
    return roots


@dataclass
class _Context:
    doc: Document
    mode: Mode
    max_depth: int | None
    tables: TableSettings

    def tables_of(self, section: Section) -> list[Table]:
        return [t for t in self.doc.tables if t.section_id == section.id]


def _render_section(ctx: _Context, section: Section, rel_depth: int, out: list[str]) -> None:
    indent = INDENT * (rel_depth - 1)
    at_limit = ctx.max_depth is not None and rel_depth >= ctx.max_depth

    if ctx.mode is Mode.STRUCTURE:
        details = [str(section.body_line_count(ctx.doc.lines))]
        if at_limit and section.children:
            details.append(f"{len(section.children)} sub")
        details.extend(_table_count(ctx, section))
        out.append(f"{indent}{_label(section)} ({', '.join(details)})")
    else:
        out.append(f"{indent}{_label(section)}")
        out.extend(_body(ctx, section))

    if not at_limit:
        for child in section.children:
            _render_section(ctx, child, rel_depth + 1, out)
    elif ctx.mode is Mode.VIEW:
        child_indent = INDENT * rel_depth
        out.extend(f"{child_indent}{_stub(ctx, child)}" for child in section.children)


def _label(section: Section) -> str:
    return f"[{section.id}] {section.title}".rstrip()


def _stub(ctx: _Context, section: Section) -> str:
    lines = section.body_line_count(ctx.doc.lines)
    details = [f"{lines} line" if lines == 1 else f"{lines} lines"]
    if section.children:
        details.append(f"{len(section.children)} sub")
    details.extend(_table_count(ctx, section))
    return f"{_label(section)} ({', '.join(details)})"


def _table_count(ctx: _Context, section: Section) -> list[str]:
    count = len(ctx.tables_of(section))
    if not count:
        return []
    return [f"{count} table" if count == 1 else f"{count} tables"]


def _body(ctx: _Context, section: Section) -> list[str]:
    lines = ctx.doc.lines
    by_start = {t.start: t for t in ctx.tables_of(section)}
    body: list[str] = []
    i = section.body_start
    while i < section.body_end:
        table = by_start.get(i)
        if table is None:
            body.append(lines[i].rstrip("\r\n"))
            i += 1
            continue
        body.extend(_table_lines(ctx, table))
        i = table.end

    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return body


def _table_lines(ctx: _Context, table: Table) -> list[str]:
    """What view/full output shows in place of a table's source lines."""
    raw = [line.rstrip("\r\n") for line in ctx.doc.lines[table.start : table.end]]
    if table.ok:
        if should_summarise(table, ctx.tables):
            return [summary(table, ctx.tables)]
        return [f"[{table.id}]", *raw]  # inline, but still addressable by ID
    policy = ctx.tables.on_error
    if policy is OnTableError.EXCLUDE:
        return []
    marker = summary(table, ctx.tables)
    return [f"{marker}, raw text below", *raw] if policy is OnTableError.SHOW else [marker]
