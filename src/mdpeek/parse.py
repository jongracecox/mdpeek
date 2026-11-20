"""Parse markdown text into a :class:`~mdpeek.model.Document` section tree.

Headings are found with markdown-it (CommonMark), so ``#`` lines inside code
fences, setext headings and HTML blocks are handled correctly. Only headings
at the top block level count: a heading inside a blockquote or list item is
content, not a section.

Section IDs come only from the tree shape. A heading becomes a child of the
nearest earlier heading with a lower level, so skipped levels (``###``
directly under ``#``) still number as direct children.

>>> doc = parse("intro\\n# A\\n## B\\n### C\\n# D\\n")
>>> [(s.id, s.title) for s in doc.walk()]
[('S0', ''), ('S1', 'A'), ('S1.1', 'B'), ('S1.1.1', 'C'), ('S2', 'D')]
"""

from __future__ import annotations

from dataclasses import dataclass

from markdown_it import MarkdownIt
from markdown_it.token import Token

from mdpeek.diagrams import build_diagrams
from mdpeek.model import PREAMBLE_ID, Document, Section
from mdpeek.tables import build_tables

_FRONT_MATTER_FENCES = {"---": ("---", "..."), "+++": ("+++",)}


@dataclass
class _Heading:
    level: int
    title: str
    start: int
    end: int


def parse(text: str) -> Document:
    """Parse ``text`` into a document with a section tree."""
    lines = text.splitlines(keepends=True)
    tokens = _tokenize(lines)
    headings = _find_headings(tokens)
    total = len(lines)

    sections: list[Section] = []
    first_heading = headings[0].start if headings else total
    if any(line.strip() for line in lines[:first_heading]):
        sections.append(
            Section(
                id=PREAMBLE_ID,
                title="",
                level=0,
                depth=1,
                start=0,
                body_start=0,
                body_end=first_heading,
                end=first_heading,
            )
        )

    stack: list[Section] = []
    top_level_count = 0
    for index, heading in enumerate(headings):
        while stack and stack[-1].level >= heading.level:
            stack.pop()
        parent = stack[-1] if stack else None
        if parent is None:
            top_level_count += 1
            section_id = f"S{top_level_count}"
        else:
            section_id = f"{parent.id}.{len(parent.children) + 1}"
        next_start = headings[index + 1].start if index + 1 < len(headings) else total
        section = Section(
            id=section_id,
            title=heading.title,
            level=heading.level,
            depth=parent.depth + 1 if parent else 1,
            start=heading.start,
            body_start=heading.end,
            body_end=next_start,
            end=total,  # closed below once the next sibling or ancestor is known
            parent=parent,
        )
        if parent is None:
            sections.append(section)
        else:
            parent.children.append(section)
        stack.append(section)

    _close_subtrees(sections, total)
    doc = Document(text=text, lines=lines, sections=sections)
    doc.tables = build_tables(tokens, lines, lambda line: _section_at(doc, line))
    doc.diagrams = build_diagrams(tokens, lines, lambda line: _section_at(doc, line))
    return doc


def _section_at(doc: Document, line: int) -> str:
    """ID of the section whose own body contains ``line``."""
    for section in doc.walk():
        if section.body_start <= line < section.body_end:
            return section.id
    return ""  # unreachable for parsed tables: every body line has an owner


def _close_subtrees(siblings: list[Section], end: int) -> None:
    """Set each section's ``end`` to where its next sibling starts."""
    for index, section in enumerate(siblings):
        section.end = siblings[index + 1].start if index + 1 < len(siblings) else end
        _close_subtrees(section.children, section.end)


def _tokenize(lines: list[str]) -> list[Token]:
    """Parse with markdown-it (CommonMark plus GFM tables)."""
    masked = list(lines)
    for i in range(_front_matter_end(lines)):
        # Blank out front matter so markdown-it can't read it as headings
        # (its closing '---' would otherwise make a setext heading).
        masked[i] = "\n"
    return MarkdownIt("commonmark").enable("table").parse("".join(masked))


def _find_headings(tokens: list[Token]) -> list[_Heading]:
    """Return top-level ATX and setext headings in document order."""
    headings: list[_Heading] = []
    for i, token in enumerate(tokens):
        if token.type != "heading_open" or token.level != 0 or token.map is None:
            continue
        inline = tokens[i + 1]
        headings.append(
            _Heading(
                level=int(token.tag[1:]),
                title=inline.content.strip(),
                start=token.map[0],
                end=token.map[1],
            )
        )
    return headings


def _front_matter_end(lines: list[str]) -> int:
    """Return the line index after a leading YAML/TOML front matter block, or 0."""
    if not lines:
        return 0
    closers = _FRONT_MATTER_FENCES.get(lines[0].strip())
    if closers is None:
        return 0
    for i in range(1, len(lines)):
        if lines[i].strip() in closers:
            return i + 1
    return 0
