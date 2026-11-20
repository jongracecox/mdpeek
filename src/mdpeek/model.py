"""Data model: a markdown document as a tree of sections.

Line numbers are 0-based indexes into ``Document.lines`` and every span is
half-open (``start`` inclusive, ``end`` exclusive).
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from mdpeek.options import Mode

PREAMBLE_ID = "S0"


class SectionNotFound(KeyError):
    """Raised when a section ID does not exist in the document."""

    def __init__(self, section_id: str, suggestions: list[str]) -> None:
        self.section_id = section_id
        self.suggestions = suggestions
        hint = f"; nearby: {', '.join(suggestions)}" if suggestions else ""
        super().__init__(f"no section {section_id!r}{hint}")

    def __str__(self) -> str:
        return str(self.args[0])


@dataclass(eq=False)
class Section:
    """One heading and the content under it.

    ``start`` is the heading's first line (the preamble ``S0`` has no heading,
    so its heading span is empty). ``body_start`` to ``body_end`` is the section's
    own content, up to the next heading of any level. ``end`` closes the whole
    subtree, including descendants.
    """

    id: str
    title: str
    level: int
    """Markdown heading level, 1-6. The preamble uses 0."""
    depth: int
    """Position in the tree: top-level sections are depth 1."""
    start: int
    body_start: int
    body_end: int
    end: int
    parent: Section | None = field(default=None, repr=False)
    children: list[Section] = field(default_factory=list, repr=False)

    @property
    def is_preamble(self) -> bool:
        return self.id == PREAMBLE_ID

    def body_line_count(self, lines: list[str]) -> int:
        """Lines of own content, ignoring leading and trailing blank lines."""
        body = lines[self.body_start : self.body_end]
        while body and not body[0].strip():
            body = body[1:]
        while body and not body[-1].strip():
            body = body[:-1]
        return len(body)

    def walk(self) -> Iterator[Section]:
        """Yield this section and all descendants in document order."""
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass(eq=False)
class Document:
    """A parsed markdown document."""

    text: str
    lines: list[str]
    """Source lines, each keeping its line ending."""
    sections: list[Section]
    """Top-level sections in order, starting with ``S0`` when there is a preamble."""

    @classmethod
    def from_text(cls, text: str) -> Document:
        """Parse markdown ``text``."""
        from mdpeek.parse import parse

        return parse(text)

    @classmethod
    def from_path(cls, path: str | os.PathLike[str]) -> Document:
        """Read and parse a UTF-8 markdown file, keeping its line endings."""
        with open(path, encoding="utf-8", newline="") as handle:
            return cls.from_text(handle.read())

    def view(self, depth: int | None = None, sections: Iterable[str] | None = None) -> str:
        """Content down to ``depth`` (default 1), with stubs for the next level."""
        from mdpeek.render import render

        return render(self, Mode.VIEW, depth, sections)

    def structure(self, depth: int | None = None, sections: Iterable[str] | None = None) -> str:
        """Heading outline with line counts, down to ``depth`` (default: all)."""
        from mdpeek.render import render

        return render(self, Mode.STRUCTURE, depth, sections)

    def full(self, depth: int | None = None, sections: Iterable[str] | None = None) -> str:
        """All content down to ``depth`` (default: all)."""
        from mdpeek.render import render

        return render(self, Mode.FULL, depth, sections)

    def walk(self) -> Iterator[Section]:
        """Yield every section in document order."""
        for section in self.sections:
            yield from section.walk()

    def get(self, section_id: str) -> Section:
        """Return the section with ``section_id`` (case-insensitive).

        Raises :class:`SectionNotFound` with nearby valid IDs otherwise.
        """
        wanted = section_id.strip().upper()
        for section in self.walk():
            if section.id == wanted:
                return section
        raise SectionNotFound(section_id, self._suggest(wanted))

    def _suggest(self, wanted: str) -> list[str]:
        """Suggest the siblings of the closest existing ancestor ID."""
        parts = wanted.removeprefix("S").split(".")
        for cut in range(len(parts) - 1, 0, -1):
            parent_id = "S" + ".".join(parts[:cut])
            for section in self.walk():
                if section.id == parent_id:
                    return [c.id for c in section.children] or [section.id]
        return [s.id for s in self.sections]
