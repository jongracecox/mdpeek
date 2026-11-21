"""Text diagrams: fenced mermaid, PlantUML, Graphviz and D2 blocks.

Diagram source is rarely useful to read inline and mostly styling, so view
and full output replace every diagram with one line, such as
``[D1] mermaid flowchart (19 ln)``. ``--diagram D1`` shows the source.

As with headings and tables, only diagrams at the top block level count; a
diagram inside a blockquote or list item stays plain content. IDs ``D1..Dn``
run through the document in order.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from markdown_it.token import Token

from mdpeek.units import count as count_of

LANGUAGES = {
    "mermaid": "mermaid",
    "plantuml": "plantuml",
    "puml": "plantuml",
    "dot": "graphviz",
    "graphviz": "graphviz",
    "d2": "d2",
}
"""Fence info words that mark a diagram, and the language name shown for each."""

_PLANTUML_START = re.compile(r"@start(\w+)", re.IGNORECASE)
_GRAPHVIZ_KIND = re.compile(r"^\s*(?:strict\s+)?(digraph|graph)\b", re.IGNORECASE)
_TITLE = re.compile(r"^\s*title:?\s+(.+?)\s*$", re.IGNORECASE)


class DiagramNotFound(KeyError):
    """Raised when a diagram ID does not exist in the document."""

    def __init__(self, diagram_id: str, available: list[str]) -> None:
        self.diagram_id = diagram_id
        self.available = available
        hint = f"; available: {', '.join(available)}" if available else "; no diagrams"
        super().__init__(f"no diagram {diagram_id!r}{hint}")

    def __str__(self) -> str:
        return str(self.args[0])


@dataclass(eq=False)
class Diagram:
    """A fenced diagram and where it sits in the document."""

    id: str
    section_id: str
    start: int
    end: int
    """Source line span (half-open), including the fences."""
    language: str
    """Normalised language: mermaid, plantuml, graphviz or d2."""
    kind: str | None
    """Diagram type where it can be read, e.g. ``flowchart`` or ``sequenceDiagram``."""
    title: str | None
    source: str
    """The diagram source between the fences."""
    raw_text: str
    """The whole fenced block as written, with LF line endings."""

    @property
    def line_count(self) -> int:
        return len(self.source.splitlines())


def build_diagrams(
    tokens: Sequence[Token], lines: list[str], section_of: Callable[[int], str]
) -> list[Diagram]:
    """Extract top-level diagram fences from a markdown-it token stream."""
    diagrams: list[Diagram] = []
    for token in tokens:
        if token.type != "fence" or token.level != 0 or token.map is None:
            continue
        words = token.info.split()
        language = LANGUAGES.get(words[0].lower()) if words else None
        if language is None:
            continue
        start, end = token.map
        kind, title = describe(language, token.content)
        diagrams.append(
            Diagram(
                id=f"D{len(diagrams) + 1}",
                section_id=section_of(start),
                start=start,
                end=end,
                language=language,
                kind=kind,
                title=title,
                source=token.content,
                raw_text="".join(line.rstrip("\r\n") + "\n" for line in lines[start:end]),
            )
        )
    return diagrams


def describe(language: str, source: str) -> tuple[str | None, str | None]:
    """The diagram's type and title, where the source states them.

    >>> describe("mermaid", "---\\ntitle: Flow\\n---\\nflowchart LR\\n  a --> b\\n")
    ('flowchart', 'Flow')
    >>> describe("plantuml", "@startuml\\ntitle Login\\nA -> B\\n@enduml\\n")
    ('uml', 'Login')
    >>> describe("graphviz", "strict digraph G { a -> b }")
    ('digraph', None)
    """
    lines = source.splitlines()
    title = None
    if language == "mermaid":
        if lines and lines[0].strip() == "---":
            close = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
            for line in lines[1:close]:
                match = _TITLE.match(line)
                if match:
                    title = match.group(1).strip("\"'")
            lines = lines[close + 1 :]
        body = [ln for ln in lines if ln.strip() and not ln.strip().startswith("%%")]
        kind = body[0].split()[0] if body else None
        title = title or _first_title(body[1:])
        return kind, title
    if language == "plantuml":
        match = _PLANTUML_START.search(source)
        return (match.group(1).lower() if match else None), _first_title(lines)
    if language == "graphviz":
        match = _GRAPHVIZ_KIND.match(source)
        return (match.group(1).lower() if match else None), None
    return None, None


def _first_title(lines: Sequence[str]) -> str | None:
    for line in lines:
        match = _TITLE.match(line)
        if match:
            return match.group(1).strip("\"'")
    return None


def summary(diagram: Diagram, *, with_section: bool = False) -> str:
    """One-line description, e.g. ``[D1] mermaid flowchart "Flow" (19 ln)``."""
    parts = [f"[{diagram.id}]"]
    if with_section:
        parts.append(diagram.section_id)
    parts.append(diagram.language)
    if diagram.kind:
        parts.append(diagram.kind)
    if diagram.title:
        parts.append(f'"{diagram.title}"')
    count = diagram.line_count
    parts.append(f"({count_of(count, 'line')})")
    return " ".join(parts)
