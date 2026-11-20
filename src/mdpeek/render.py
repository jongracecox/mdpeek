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

from mdpeek.model import Document, Section
from mdpeek.options import Mode, coerce

INDENT = "  "
DEFAULT_VIEW_DEPTH = 1


def render(
    doc: Document,
    mode: Mode | str = Mode.VIEW,
    depth: int | None = None,
    sections: Iterable[str] | None = None,
) -> str:
    """Render ``doc`` and return the text, ending in a newline if not empty.

    ``sections`` limits output to those section IDs; depth then counts from
    each one (the section itself is depth 1). Raises
    :class:`~mdpeek.model.SectionNotFound` for an unknown ID and
    ``ValueError`` for a depth below 1.
    """
    mode = coerce(Mode, mode)
    if depth is not None and depth < 1:
        raise ValueError(f"depth must be at least 1, got {depth}")
    if depth is None and mode is Mode.VIEW:
        depth = DEFAULT_VIEW_DEPTH

    out: list[str] = []
    for root in _roots(doc, sections):
        _render_section(doc, root, mode, 1, depth, out)
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


def _render_section(
    doc: Document,
    section: Section,
    mode: Mode,
    rel_depth: int,
    max_depth: int | None,
    out: list[str],
) -> None:
    indent = INDENT * (rel_depth - 1)
    at_limit = max_depth is not None and rel_depth >= max_depth

    if mode is Mode.STRUCTURE:
        count = str(section.body_line_count(doc.lines))
        if at_limit and section.children:
            count += f", {len(section.children)} sub"
        out.append(f"{indent}{_label(section)} ({count})")
    else:
        out.append(f"{indent}{_label(section)}")
        out.extend(_body(doc, section))

    if not at_limit:
        for child in section.children:
            _render_section(doc, child, mode, rel_depth + 1, max_depth, out)
    elif mode is Mode.VIEW:
        child_indent = INDENT * rel_depth
        out.extend(f"{child_indent}{_stub(doc, child)}" for child in section.children)


def _label(section: Section) -> str:
    return f"[{section.id}] {section.title}".rstrip()


def _stub(doc: Document, section: Section) -> str:
    lines = section.body_line_count(doc.lines)
    detail = f"{lines} line" if lines == 1 else f"{lines} lines"
    if section.children:
        detail += f", {len(section.children)} sub"
    return f"{_label(section)} ({detail})"


def _body(doc: Document, section: Section) -> list[str]:
    body = [line.rstrip("\r\n") for line in doc.lines[section.body_start : section.body_end]]
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return body
