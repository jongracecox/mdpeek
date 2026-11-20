"""Find the sections whose lines match a pattern.

Every line of a section is searched: its heading, body text, tables and
fenced blocks. A line belongs to the innermost section around it, and each
matching line counts once.

Patterns are regular expressions with smart case: case-insensitive unless the
pattern has an upper-case letter.

>>> from mdpeek.model import Document
>>> doc = Document.from_text("# Setup\\nInstall it.\\n## Linux\\napt install x\\nthen run\\n")
>>> [(s.id, n) for s, n in section_hits(doc, compile_pattern("INSTALL"))]
[]
>>> [(s.id, n) for s, n in section_hits(doc, compile_pattern("install"))]
[('S1', 1), ('S1.1', 1)]
>>> print(render_hits(section_hits(doc, compile_pattern("install|run"))), end="")
[S1] Setup (1 match)
[S1.1] Linux (2 matches)
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from mdpeek.model import Document, Section

INDENT = "  "


class PatternError(ValueError):
    """Raised for a pattern that is not a valid regular expression."""


def compile_pattern(pattern: str) -> re.Pattern[str]:
    """Compile ``pattern`` with smart case.

    >>> bool(compile_pattern("todo").search("TODO: later"))
    True
    >>> bool(compile_pattern("Todo").search("TODO: later"))
    False
    >>> compile_pattern("(")  # doctest: +ELLIPSIS
    Traceback (most recent call last):
    ...
    mdpeek.search.PatternError: invalid --grep pattern '(': missing ), ...
    """
    flags = 0 if any(c.isupper() for c in pattern) else re.IGNORECASE
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        raise PatternError(f"invalid --grep pattern {pattern!r}: {exc}") from None


def section_hits(
    doc: Document, regex: re.Pattern[str], sections: Iterable[str] | None = None
) -> list[tuple[Section, int]]:
    """Each section with a matching line, and its count, in document order.

    ``sections`` limits the search to those sections' subtrees.
    """
    owners: dict[int, Section] = {}
    roots = list(doc.sections) if sections is None else [doc.get(s) for s in sections]
    for root in roots:
        for section in root.walk():
            for line in range(section.start, section.body_end):
                owners[line] = section
    counts: dict[int, int] = {}
    order: list[Section] = []
    for index in sorted(owners):
        if regex.search(doc.lines[index].rstrip("\r\n")):
            section = owners[index]
            if id(section) not in counts:
                counts[id(section)] = 0
                order.append(section)
            counts[id(section)] += 1
    return [(s, counts[id(s)]) for s in order]


def matches(count: int) -> str:
    return f"{count} match" if count == 1 else f"{count} matches"


def hit_line(section: Section, count: int) -> str:
    return f"[{section.id}] {section.title}".rstrip() + f" ({matches(count)})"


def render_hits(hits: list[tuple[Section, int]], indent: str = "") -> str:
    """One line per matching section."""
    return "".join(f"{indent}{hit_line(s, n)}\n" for s, n in hits)
