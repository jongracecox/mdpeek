"""Fenced code blocks: an inventory of every top-level fence, and direct access.

Every fenced block gets an ID ``F1..Fn`` in document order, including diagram
fences (which also have a ``D`` ID). Fences stay inline in view and full
output; ``--fences`` lists them and ``--fence F3`` prints one, so an agent can
pull a single code example without reading its whole section.

As with headings and tables, a fence inside a blockquote or list item is
content of that block and gets no ID. Indented code blocks are not fences.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from markdown_it.token import Token

from mdpeek.diagrams import Diagram
from mdpeek.formats import to_json
from mdpeek.options import Format, coerce
from mdpeek.units import count as count_of


class FenceNotFound(KeyError):
    """Raised when a fence ID does not exist in the document."""

    def __init__(self, fence_id: str, available: list[str]) -> None:
        self.fence_id = fence_id
        self.available = available
        hint = f"; available: {_id_range(available)}" if available else "; no fenced blocks"
        super().__init__(f"no fenced block {fence_id!r}{hint}")

    def __str__(self) -> str:
        return str(self.args[0])


def _id_range(ids: list[str]) -> str:
    return ", ".join(ids) if len(ids) <= 5 else f"{ids[0]}..{ids[-1]}"


@dataclass(eq=False)
class Fence:
    """A fenced block and where it sits in the document."""

    id: str
    section_id: str
    start: int
    end: int
    """Source line span (half-open), including the fences."""
    language: str | None
    """First word of the info string, lowercased; ``None`` if there is none."""
    source: str
    raw_text: str
    """The whole fenced block as written, with LF line endings."""
    diagram_id: str | None = None
    """The diagram ID when this fence is also a diagram."""

    @property
    def line_count(self) -> int:
        return len(self.source.splitlines())


def build_fences(
    tokens: Sequence[Token],
    lines: list[str],
    section_of: Callable[[int], str],
    diagrams: Sequence[Diagram] = (),
) -> list[Fence]:
    """Extract every top-level fence from a markdown-it token stream."""
    diagram_at = {d.start: d.id for d in diagrams}
    fences: list[Fence] = []
    for token in tokens:
        if token.type != "fence" or token.level != 0 or token.map is None:
            continue
        start, end = token.map
        words = token.info.split()
        fences.append(
            Fence(
                id=f"F{len(fences) + 1}",
                section_id=section_of(start),
                start=start,
                end=end,
                language=words[0].lower() if words else None,
                source=token.content,
                raw_text="".join(line.rstrip("\r\n") + "\n" for line in lines[start:end]),
                diagram_id=diagram_at.get(start),
            )
        )
    return fences


def summary(fence: Fence, *, with_section: bool = True) -> str:
    """One line, e.g. ``[F4] S1.6.2 mermaid (19 ln) = D1``."""
    parts = [f"[{fence.id}]"]
    if with_section:
        parts.append(fence.section_id)
    parts.append(fence.language or "plain")
    count = fence.line_count
    parts.append(f"({count_of(count, 'line')})")
    if fence.diagram_id:
        parts.append(f"= {fence.diagram_id}")
    return " ".join(parts)


def render_fences(fences: Sequence[Fence], fmt: Format | str, *, label_single: bool = False) -> str:
    """Fence source for md, or JSON with the source.

    A single fence prints its bare source (no summary line, no fence markers),
    ready to pipe on: whoever asked for it by ID has already seen its summary.
    Several fences each get their summary line and fences, so the boundaries
    are clear. ``label_single`` labels and fences a single fence too, for
    callers that show it alongside others.
    """
    fmt = coerce(Format, fmt)
    if fmt is Format.MD and len(fences) == 1 and not label_single:
        return fences[0].source
    if fmt is Format.JSON:
        objects = [_describe(f, source=True) for f in fences]
        return to_json(objects[0] if len(objects) == 1 else objects)
    if fmt is Format.JSONL:
        return "".join(to_json(_describe(f, source=True)) for f in fences)
    return "\n".join(f"{summary(f)}\n{f.raw_text}" for f in fences)


def render_fence_list(fences: Sequence[Fence], fmt: Format | str) -> str:
    """One summary line (or JSON object, without source) per fence."""
    fmt = coerce(Format, fmt)
    if fmt is Format.JSON:
        return to_json([_describe(f, source=False) for f in fences])
    if fmt is Format.JSONL:
        return "".join(to_json(_describe(f, source=False)) for f in fences)
    return "".join(summary(f) + "\n" for f in fences)


def _describe(fence: Fence, *, source: bool) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": fence.id,
        "section": fence.section_id,
        "language": fence.language,
        "lines": fence.line_count,
        "diagram": fence.diagram_id,
    }
    if source:
        data["source"] = fence.source
    return data
