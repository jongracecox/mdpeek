"""Data model: a markdown document as a tree of sections.

Line numbers are 0-based indexes into ``Document.lines`` and every span is
half-open (``start`` inclusive, ``end`` exclusive).
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mdpeek.options import Engine, Mode

if TYPE_CHECKING:
    from mdpeek.cache import Cache
    from mdpeek.diagrams import Diagram
    from mdpeek.engines import QueryResult
    from mdpeek.fences import Fence
    from mdpeek.meta import FrontMatter
    from mdpeek.options import CacheBackend
    from mdpeek.source import SourceInfo
    from mdpeek.tables import Table, TableSettings

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
    """Top-level sections in order, starting with ``S0`` when there is a preamble
    (content before the first heading, after any front matter)."""
    tables: list[Table] = field(default_factory=list)
    """Top-level GFM tables in document order (``T1..Tn``)."""
    diagrams: list[Diagram] = field(default_factory=list)
    """Top-level mermaid/PlantUML/Graphviz/D2 fences in document order (``D1..Dn``)."""
    fences: list[Fence] = field(default_factory=list)
    """Every top-level fenced block in document order (``F1..Fn``), diagrams included."""
    meta: FrontMatter | None = None
    """The front matter block at the top of the file, if any. Not part of any section."""
    source: SourceInfo | None = None
    """Where the text came from (path, URL, stdin), and whether it was cached."""

    @classmethod
    def from_text(cls, text: str) -> Document:
        """Parse markdown ``text``."""
        from mdpeek.parse import parse

        return parse(text)

    @classmethod
    def from_path(cls, path: str | os.PathLike[str]) -> Document:
        """Read and parse a markdown file, keeping its line endings.

        The file is decoded as UTF-8; invalid bytes become U+FFFD rather than
        failing the whole read (tables report them as cleaned cells).
        """
        from mdpeek.source import SourceInfo, read_path

        doc = cls.from_text(read_path(os.fspath(path)))
        doc.source = SourceInfo(os.fspath(path), "path")
        return doc

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        cache: CacheBackend | str | Cache | None = "memory",
        ttl: float | None = None,
        refresh: bool = False,
        timeout: float | None = None,
    ) -> Document:
        """Fetch and parse markdown from an ``http(s)://`` URL.

        Results are cached in memory for the process by default; pass
        ``cache="disk"`` to share them between runs, or ``None`` to turn
        caching off. ``doc.source`` says whether the text came from the cache.
        """
        from mdpeek.source import DEFAULT_TIMEOUT, DEFAULT_TTL, is_url, load

        if not is_url(url):
            raise ValueError(f"not an http(s) URL: {url!r}")
        text, info = load(
            url,
            headers=headers,
            cache=cache,
            ttl=DEFAULT_TTL if ttl is None else ttl,
            refresh=refresh,
            timeout=DEFAULT_TIMEOUT if timeout is None else timeout,
        )
        doc = cls.from_text(text)
        doc.source = info
        return doc

    def view(
        self,
        depth: int | None = None,
        sections: Iterable[str] | None = None,
        tables: TableSettings | None = None,
        diagram_summaries: bool = True,
    ) -> str:
        """Content down to ``depth`` (default 1), with stubs for the next level."""
        from mdpeek.render import render

        return render(self, Mode.VIEW, depth, sections, tables, diagram_summaries)

    def structure(self, depth: int | None = None, sections: Iterable[str] | None = None) -> str:
        """Heading outline with line counts, down to ``depth`` (default: all)."""
        from mdpeek.render import render

        return render(self, Mode.STRUCTURE, depth, sections)

    def full(
        self,
        depth: int | None = None,
        sections: Iterable[str] | None = None,
        tables: TableSettings | None = None,
        diagram_summaries: bool = True,
    ) -> str:
        """All content down to ``depth`` (default: all)."""
        from mdpeek.render import render

        return render(self, Mode.FULL, depth, sections, tables, diagram_summaries)

    def table(self, table_id: str) -> Table:
        """Return the table with ``table_id`` (case-insensitive)."""
        from mdpeek.tables import TableNotFound

        wanted = table_id.strip().upper()
        for table in self.tables:
            if table.id == wanted:
                return table
        raise TableNotFound(table_id, [t.id for t in self.tables])

    def query(
        self,
        sql: str,
        engine: Engine | str = Engine.AUTO,
        sections: Iterable[str] | None = None,
    ) -> QueryResult:
        """Run ``sql`` over the tables (as ``t1``, ``t2``, ...) in ``sections``.

        See :mod:`mdpeek.engines` for engine selection and errors.
        """
        from mdpeek.engines import run_query

        return run_query(self.tables_in(sections), sql, engine)

    def diagram(self, diagram_id: str) -> Diagram:
        """Return the diagram with ``diagram_id`` (case-insensitive)."""
        from mdpeek.diagrams import DiagramNotFound

        wanted = diagram_id.strip().upper()
        for diagram in self.diagrams:
            if diagram.id == wanted:
                return diagram
        raise DiagramNotFound(diagram_id, [d.id for d in self.diagrams])

    def diagrams_in(self, section_ids: Iterable[str] | None = None) -> list[Diagram]:
        """Diagrams in the given sections' subtrees, or all diagrams if ``None``."""
        if section_ids is None:
            return list(self.diagrams)
        scope = {s.id for section_id in section_ids for s in self.get(section_id).walk()}
        return [d for d in self.diagrams if d.section_id in scope]

    def fence(self, fence_id: str) -> Fence:
        """Return the fenced block with ``fence_id`` (case-insensitive)."""
        from mdpeek.fences import FenceNotFound

        wanted = fence_id.strip().upper()
        for fence in self.fences:
            if fence.id == wanted:
                return fence
        raise FenceNotFound(fence_id, [f.id for f in self.fences])

    def fences_in(self, section_ids: Iterable[str] | None = None) -> list[Fence]:
        """Fenced blocks in the given sections' subtrees, or all if ``None``."""
        if section_ids is None:
            return list(self.fences)
        scope = {s.id for section_id in section_ids for s in self.get(section_id).walk()}
        return [f for f in self.fences if f.section_id in scope]

    def tables_in(self, section_ids: Iterable[str] | None = None) -> list[Table]:
        """Tables in the given sections' subtrees, or all tables if ``None``."""
        if section_ids is None:
            return list(self.tables)
        scope = {s.id for section_id in section_ids for s in self.get(section_id).walk()}
        return [t for t in self.tables if t.section_id in scope]

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
