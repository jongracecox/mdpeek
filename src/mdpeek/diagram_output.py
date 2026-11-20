"""Show diagrams on demand (``--diagram`` / ``--diagrams``)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mdpeek.diagrams import Diagram, summary
from mdpeek.formats import to_json
from mdpeek.options import Format, coerce


def render_diagrams(diagrams: Sequence[Diagram], fmt: Format | str) -> str:
    """Diagram source for md, or JSON with the source.

    A single diagram prints its bare source, ready to pipe into a renderer:
    whoever asked for it by ID has already seen its summary. Several diagrams
    each get their summary line and fences, so the boundaries are clear.
    """
    fmt = coerce(Format, fmt)
    if fmt is Format.MD and len(diagrams) == 1:
        return diagrams[0].source
    if fmt is Format.JSON:
        objects = [_describe(d, source=True) for d in diagrams]
        return to_json(objects[0] if len(objects) == 1 else objects)
    if fmt is Format.JSONL:
        return "".join(to_json(_describe(d, source=True)) for d in diagrams)
    return "\n".join(f"{summary(d, with_section=True)}\n{d.raw_text}" for d in diagrams)


def render_diagram_list(diagrams: Sequence[Diagram], fmt: Format | str) -> str:
    """One summary line (or JSON object, without source) per diagram."""
    fmt = coerce(Format, fmt)
    if fmt is Format.JSON:
        return to_json([_describe(d, source=False) for d in diagrams])
    if fmt is Format.JSONL:
        return "".join(to_json(_describe(d, source=False)) for d in diagrams)
    return "".join(summary(d, with_section=True) + "\n" for d in diagrams)


def _describe(diagram: Diagram, *, source: bool) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": diagram.id,
        "section": diagram.section_id,
        "language": diagram.language,
        "kind": diagram.kind,
        "title": diagram.title,
        "lines": diagram.line_count,
    }
    if source:
        data["source"] = diagram.source
    return data
