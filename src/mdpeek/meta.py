"""Front matter: a metadata block fenced at the very top of a file.

A block that opens on the first line with ``---`` (YAML, closed by ``---`` or
``...``) or ``+++`` (TOML) is front matter. It is recognised by its fences
alone: there is no standard set of keys, so mdpeek never interprets what is
inside. Document output shows a ``[meta] (N)`` marker in its place, and
``--meta`` prints the block's contents. An unclosed block is ordinary text.

>>> meta = find_front_matter(["---\\n", "title: x\\n", "---\\n", "# A\\n"])
>>> meta.format, meta.end, meta.source
('yaml', 3, 'title: x\\n')
>>> find_front_matter(["# A\\n"]) is None
True
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from mdpeek.formats import to_json
from mdpeek.options import Format, coerce

_FENCES = {"---": ("yaml", ("---", "...")), "+++": ("toml", ("+++",))}

MARKER_ID = "meta"


@dataclass(frozen=True)
class FrontMatter:
    """A front matter block. It always starts on line 0."""

    format: str
    """``yaml`` or ``toml``, from the opening fence."""
    end: int
    """The line after the closing fence."""
    source: str
    """The lines between the fences, with LF line endings."""

    @property
    def line_count(self) -> int:
        return len(self.source.splitlines())

    def marker(self) -> str:
        """The one-line stand-in shown in document output, e.g. ``[meta] (2)``."""
        return f"[{MARKER_ID}] ({self.line_count})"

    def describe(self) -> dict[str, Any]:
        return {"format": self.format, "lines": self.line_count, "source": self.source}


def find_front_matter(lines: Sequence[str]) -> FrontMatter | None:
    """The front matter at the top of ``lines``, or ``None``."""
    if not lines:
        return None
    fence = _FENCES.get(lines[0].strip())
    if fence is None:
        return None
    fmt, closers = fence
    for i in range(1, len(lines)):
        if lines[i].strip() in closers:
            source = "".join(line.rstrip("\r\n") + "\n" for line in lines[1:i])
            return FrontMatter(fmt, i + 1, source)
    return None


def render_meta(meta: FrontMatter, fmt: Format | str) -> str:
    """The block's bare contents for md, ready to pipe, or a JSON object."""
    fmt = coerce(Format, fmt)
    if fmt in (Format.JSON, Format.JSONL):
        return to_json(meta.describe())
    return meta.source


def render_meta_list(entries: Sequence[tuple[str, FrontMatter]], fmt: Format | str) -> str:
    """Front matter of several files, each labelled with its path."""
    fmt = coerce(Format, fmt)
    objects = [{"path": path, **meta.describe()} for path, meta in entries]
    if fmt is Format.JSON:
        return to_json(objects)
    if fmt is Format.JSONL:
        return "".join(to_json(o) for o in objects)
    return "\n".join(f"==> {path} <==\n{meta.source}" for path, meta in entries)
