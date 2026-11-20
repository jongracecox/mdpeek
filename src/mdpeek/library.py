"""A directory of markdown files, shown as a tree.

Every entry is listed by its path, so an agent opens anything it sees by
pointing mdpeek at that path. Directories show recursive totals, so the
bulk of a large library is visible before it is opened.

- A file is labelled with its title: the text of its only top-level heading,
  or the first of several with ``+N`` for the rest. A file with no headings
  has no title.
- A directory's ``README.md`` (or ``index.md``) gives the directory its title
  and is listed first.
- Hidden entries, ``node_modules`` and ``__pycache__`` are skipped, and so is
  any directory with no markdown in it. Symlinked directories are not
  followed.

>>> import tempfile, pathlib
>>> root = pathlib.Path(tempfile.mkdtemp())
>>> _ = (root / "README.md").write_text("# Handbook\\n")
>>> (root / "guides").mkdir()
>>> _ = (root / "guides" / "install.md").write_text("# Install\\n## Linux\\nRun it.\\n")
>>> print(Library.from_path(root).tree().replace(str(root), "docs"), end="")
docs/ Handbook (2 files, 1 dir, 4 lines)
  README.md Handbook (1 line)
  guides/ (1 file, 3 lines)
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cache, cached_property
from pathlib import Path

from mdpeek.model import Document

INDENT = "  "
DEFAULT_LEVELS = 1
MARKDOWN_SUFFIXES = (".md", ".markdown")
SKIPPED_NAMES = frozenset({"node_modules", "__pycache__"})
INDEX_STEMS = ("readme", "index")
"""File stems that title their directory, in order of preference."""


@dataclass(frozen=True)
class Title:
    """How a file is labelled in a tree."""

    text: str
    extra: int = 0
    """Further top-level headings not shown in the label."""

    @property
    def collapsed(self) -> bool:
        """True when the title is the file's only top-level heading."""
        return self.extra == 0

    def __str__(self) -> str:
        return f"{self.text} +{self.extra}" if self.extra else self.text


def title_of(doc: Document) -> Title | None:
    """The title of ``doc``, or ``None`` if it has no headings.

    >>> str(title_of(Document.from_text("intro\\n# Guide\\n## Install\\n")))
    'Guide'
    >>> str(title_of(Document.from_text("# One\\n# Two\\n# Three\\n")))
    'One +2'
    >>> title_of(Document.from_text("no headings\\n")) is None
    True
    """
    top = [s for s in doc.sections if not s.is_preamble]
    if not top:
        return None
    return Title(top[0].title, len(top) - 1)


@dataclass(eq=False)
class FileNode:
    """A markdown file in a library."""

    name: str
    path: Path
    text: str

    @cached_property
    def doc(self) -> Document:
        return Document.from_text(self.text)

    @cached_property
    def line_count(self) -> int:
        return len(self.text.splitlines())

    @cached_property
    def title(self) -> Title | None:
        return title_of(self.doc)

    def section_count(self) -> int:
        """Headings in the file, not counting a collapsed title."""
        headings = sum(1 for s in self.doc.walk() if not s.is_preamble)
        title = self.title
        return headings - 1 if title is not None and title.collapsed else headings


@dataclass(eq=False)
class DirNode:
    """A directory holding markdown, directly or in a subdirectory."""

    name: str
    path: Path
    dirs: list[DirNode] = field(default_factory=list)
    files: list[FileNode] = field(default_factory=list)

    @cached_property
    def index(self) -> FileNode | None:
        """The file that titles this directory, if any."""
        for stem in INDEX_STEMS:
            for node in self.files:
                if Path(node.name).stem.lower() == stem:
                    return node
        return None

    @property
    def title(self) -> Title | None:
        return self.index.title if self.index else None

    def entries(self) -> list[DirNode | FileNode]:
        """The index file first, then directories, then the other files."""
        index = self.index
        rest = [f for f in self.files if f is not index]
        return ([index] if index else []) + list(self.dirs) + rest

    @cached_property
    def file_count(self) -> int:
        return len(self.files) + sum(d.file_count for d in self.dirs)

    @cached_property
    def dir_count(self) -> int:
        return len(self.dirs) + sum(d.dir_count for d in self.dirs)

    @cached_property
    def line_count(self) -> int:
        return sum(f.line_count for f in self.files) + sum(d.line_count for d in self.dirs)


@dataclass(eq=False)
class Library:
    """Every markdown file under a directory."""

    root: DirNode
    display: str
    """The root as the caller named it, ending in ``/``."""
    skipped: list[str] = field(default_factory=list)
    """Paths that could not be read, each with the reason."""

    @classmethod
    def from_path(
        cls,
        path: str | os.PathLike[str],
        include: Iterable[str] | None = None,
        exclude: Iterable[str] | None = None,
    ) -> Library:
        """Scan the directory at ``path``.

        ``include`` globs replace the default (``*.md``, ``*.markdown``,
        case-insensitive). A path is excluded when an ``exclude`` glob matches
        its name or its path relative to the root; an excluded directory is
        not entered. Globs are case-sensitive; see :func:`glob_match`.
        """
        root = Path(path)
        if not root.is_dir():
            raise NotADirectoryError(f"not a directory: {os.fspath(path)!r}")
        scanner = _Scanner(root, list(include or ()), list(exclude or ()))
        node = scanner.scan(root, "")
        if node is None:
            node = DirNode(root.name, root)
        display = os.fspath(path).rstrip("/") or "/"
        if not display.endswith("/"):
            display += "/"
        return cls(node, display, scanner.skipped)

    def tree(self, levels: int | None = None, first: int | None = None) -> str:
        """The tree, expanding ``levels`` directory levels (default 1).

        ``first`` shows only the first N entries of each directory; the rest
        are summarised on one line. Raises ``ValueError`` for values below 1.
        """
        levels = DEFAULT_LEVELS if levels is None else levels
        for name, value in (("levels", levels), ("first", first)):
            if value is not None and value < 1:
                raise ValueError(f"{name} must be at least 1, got {value}")
        out = [_dir_line(self.root, self.display)]
        _render_entries(self.root, 1, levels, first, out)
        return "".join(f"{line}\n" for line in out)


class _Scanner:
    def __init__(self, root: Path, include: list[str], exclude: list[str]) -> None:
        self.root = root
        self.include = include
        self.exclude = exclude
        self.skipped: list[str] = []

    def _excluded(self, name: str, rel: str) -> bool:
        return any(glob_match(name, p) or glob_match(rel, p) for p in self.exclude)

    def _included(self, name: str, rel: str) -> bool:
        if not self.include:
            return name.lower().endswith(MARKDOWN_SUFFIXES)
        return any(glob_match(name, p) or glob_match(rel, p) for p in self.include)

    def scan(self, path: Path, rel: str) -> DirNode | None:
        """The node for ``path``, or ``None`` if it holds no markdown."""
        try:
            with os.scandir(path) as it:
                entries = sorted(it, key=lambda e: (e.name.casefold(), e.name))
        except OSError as exc:
            self.skipped.append(f"{path}: {exc.strerror or exc}")
            return None

        node = DirNode(path.name, path)
        for entry in entries:
            name = entry.name
            child_rel = f"{rel}/{name}" if rel else name
            if name.startswith(".") or self._excluded(name, child_rel):
                continue
            if entry.is_dir(follow_symlinks=False):
                if name in SKIPPED_NAMES:
                    continue
                child = self.scan(Path(entry.path), child_rel)
                if child is not None:
                    node.dirs.append(child)
            elif entry.is_file() and self._included(name, child_rel):
                file_node = self._read(Path(entry.path), name)
                if file_node is not None:
                    node.files.append(file_node)
        return node if node.dirs or node.files else None

    def _read(self, path: Path, name: str) -> FileNode | None:
        try:
            with open(path, encoding="utf-8", errors="replace", newline="") as handle:
                return FileNode(name, path, handle.read())
        except OSError as exc:
            self.skipped.append(f"{path}: {exc.strerror or exc}")
            return None


@cache
def _glob_regex(pattern: str) -> re.Pattern[str]:
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            parts.append(".*")
            i += 2
            continue
        if char == "*":
            parts.append("[^/]*")
        elif char == "?":
            parts.append("[^/]")
        elif char == "[" and (close := pattern.find("]", i + 2)) != -1:
            body = pattern[i + 1 : close]
            if body.startswith("!"):
                body = "^" + body[1:]
            parts.append(f"[{body.replace(chr(92), chr(92) * 2)}]")
            i = close + 1
            continue
        else:
            parts.append(re.escape(char))
        i += 1
    return re.compile("".join(parts))


def glob_match(path: str, pattern: str) -> bool:
    """Whether ``path`` matches ``pattern``, gitignore-style.

    ``*`` and ``?`` stay within one path segment, ``**`` crosses segments,
    and ``[abc]`` / ``[!abc]`` match one character.

    >>> glob_match("guides/install.md", "guides/*.md")
    True
    >>> glob_match("guides/advanced/tuning.md", "guides/*.md")
    False
    >>> glob_match("guides/advanced/tuning.md", "guides/**/*.md")
    True
    >>> glob_match("guides/install.md", "guides/**/*.md")
    True
    >>> glob_match("v2.md", "v[!0-1].md")
    True
    """
    return _glob_regex(pattern).fullmatch(path) is not None


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _labelled(name: str, title: Title | None, details: list[str]) -> str:
    label = f"{name} {title}" if title is not None and str(title) else name
    return f"{label} ({', '.join(details)})"


def _dir_line(node: DirNode, name: str) -> str:
    details = [_plural(node.file_count, "file")]
    if node.dir_count:
        details.append(_plural(node.dir_count, "dir"))
    if node.file_count:
        details.append(_plural(node.line_count, "line"))
    return _labelled(name, node.title, details)


def _file_line(node: FileNode) -> str:
    details = [_plural(node.line_count, "line")]
    sections = node.section_count()
    if sections:
        details.append(_plural(sections, "section"))
    if node.doc.tables:
        details.append(_plural(len(node.doc.tables), "table"))
    return _labelled(node.name, node.title, details)


def _render_entries(
    node: DirNode, depth: int, levels: int, first: int | None, out: list[str]
) -> None:
    indent = INDENT * depth
    entries = node.entries()
    shown = entries if first is None else entries[:first]
    for entry in shown:
        if isinstance(entry, FileNode):
            out.append(indent + _file_line(entry))
            continue
        out.append(indent + _dir_line(entry, entry.name + "/"))
        if depth < levels:
            _render_entries(entry, depth + 1, levels, first, out)
    hidden = entries[len(shown) :]
    if hidden:
        dirs = [e for e in hidden if isinstance(e, DirNode)]
        files = [e for e in hidden if isinstance(e, FileNode)]
        details = []
        if dirs:
            details.append(_plural(len(dirs), "dir"))
        if files:
            details.append(_plural(len(files), "file"))
        details.append(_plural(sum(e.line_count for e in hidden), "line"))
        out.append(f"{indent}… {len(hidden)} more ({', '.join(details)})")
