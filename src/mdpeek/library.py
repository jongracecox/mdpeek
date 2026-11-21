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
docs/ Handbook (2 files, 1 dir, 4 ln)
  README.md Handbook (1 ln)
  guides/ (1 file, 3 ln)
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import cache, cached_property
from pathlib import Path

from mdpeek.model import Document, Section
from mdpeek.search import hit_line, matches, section_matches, snippets
from mdpeek.units import count

INDENT = "  "
DEFAULT_LEVELS = 1
DEFAULT_BUDGET = 150
"""Lines a directory tree aims to fit when no -L, -d or -n is given."""
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
    from_meta: bool = False
    """The title came from front matter, not a heading."""

    @property
    def collapsed(self) -> bool:
        """True when the title is the file's only top-level heading."""
        return not self.from_meta and self.extra == 0

    def __str__(self) -> str:
        return f"{self.text} +{self.extra}" if self.extra else self.text


def title_of(doc: Document) -> Title | None:
    """The title of ``doc``: its front matter ``title``, else its first top-level
    heading; ``None`` if it has neither.

    >>> str(title_of(Document.from_text("---\\ntitle: Venues\\n---\\n## Schema\\n## Keys\\n")))
    'Venues'

    >>> str(title_of(Document.from_text("intro\\n# Guide\\n## Install\\n")))
    'Guide'
    >>> str(title_of(Document.from_text("# One\\n# Two\\n# Three\\n")))
    'One +2'
    >>> title_of(Document.from_text("no headings\\n")) is None
    True
    """
    meta_title = doc.meta.value("title") if doc.meta is not None else None
    if meta_title:
        return Title(meta_title, from_meta=True)
    top = [s for s in doc.sections if not s.is_preamble]
    if not top:
        return None
    return Title(top[0].title, len(top) - 1)


SUMMARY_CHARS = 160
_NOT_PROSE = ("#", "|", "```", "~~~", "<", ">", "-", "*", "+", "!")
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z`(])")


def summary_of(doc: Document) -> str | None:
    """A one-line summary: front matter ``summary`` or ``description``, else the
    first sentence of the first paragraph (links reduced to their text), else
    the first few section headings; cut to about 160 characters.

    >>> summary_of(Document.from_text("---\\nsummary: Store rows.\\n---\\n# S\\n"))
    'Store rows.'
    >>> summary_of(Document.from_text("# Guide\\n\\nInstall it\\nfirst. Then run.\\n"))
    'Install it first.'
    >>> summary_of(Document.from_text("# Runbook\\n\\nFor the fix [PR #9](https://x/9) needs.\\n"))
    'For the fix PR #9 needs.'
    >>> summary_of(Document.from_text("# T\\n## Setup\\n- a\\n## Use\\n- b\\n"))
    'Covers: Setup; Use'
    >>> summary_of(Document.from_text("# Only a heading\\n")) is None
    True
    """
    if doc.meta is not None:
        for key in ("summary", "description"):
            value = doc.meta.value(key)
            if value:
                return _clip(value)
    start = doc.meta.end if doc.meta is not None else 0
    in_fence = False
    paragraph: list[str] = []
    for raw in doc.lines[start:]:
        line = raw.strip()
        if line.startswith(("```", "~~~")):
            in_fence = not in_fence
            if paragraph:
                break
            continue
        if in_fence:
            continue
        numbered = bool(line) and line[0].isdigit() and ". " in line[:4]
        if line and not numbered and not line.startswith(_NOT_PROSE):
            paragraph.append(line)
        elif paragraph:
            break
    if paragraph:
        text = _LINK.sub(r"\1", " ".join(paragraph)).replace("**", "")
        return _clip(_SENTENCE_END.split(text, maxsplit=1)[0])
    headings = [s.title for s in doc.walk() if not s.is_preamble][1:5]
    return _clip("Covers: " + "; ".join(headings)) if headings else None


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SUMMARY_CHARS else text[: SUMMARY_CHARS - 1].rstrip() + "…"


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

    @cached_property
    def summary(self) -> str | None:
        return summary_of(self.doc)

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
        confine: bool = False,
    ) -> Library:
        """Scan the directory at ``path``.

        ``include`` globs replace the default (``*.md``, ``*.markdown``,
        case-insensitive). A path is excluded when an ``exclude`` glob matches
        its name or its path relative to the root; an excluded directory is
        not entered. Globs are case-sensitive; see :func:`glob_match`.
        ``confine`` skips symlinked files that lead outside the directory.
        """
        root = Path(path)
        if not root.is_dir():
            raise NotADirectoryError(f"not a directory: {os.fspath(path)!r}")
        scanner = _Scanner(
            root, list(include or ()), list(exclude or ()), root.resolve() if confine else None
        )
        node = scanner.scan(root, "")
        if node is None:
            node = DirNode(root.name, root)
        display = os.fspath(path).rstrip("/") or "/"
        if not display.endswith("/"):
            display += "/"
        return cls(node, display, scanner.skipped)

    def tree(
        self,
        levels: int | None = None,
        first: int | None = None,
        depth: int | None = None,
        summaries: bool = False,
    ) -> str:
        """The tree, expanding ``levels`` directory levels (default 1).

        ``depth`` lists each shown file's headings down to that depth,
        counted below a collapsed title (default: none). ``first`` shows only
        the first N entries of each directory and the first N sections under
        each heading; the rest are summarised on one line. ``summaries`` adds
        each file's one-line summary (:func:`summary_of`) to its line. Raises
        ``ValueError`` for values below 1.
        """
        levels = DEFAULT_LEVELS if levels is None else levels
        for name, value in (("levels", levels), ("first", first), ("depth", depth)):
            if value is not None and value < 1:
                raise ValueError(f"{name} must be at least 1, got {value}")
        out = [_dir_line(self.root, self.display)]
        _render_entries(self.root, 1, _TreeOptions(levels, first, depth or 0, summaries), out)
        return "".join(f"{line}\n" for line in out)

    def fit(
        self,
        budget: int = DEFAULT_BUDGET,
        levels: int | None = None,
        depth: int | None = None,
        first: int | None = None,
    ) -> TreeFit:
        """The most detailed tree settings whose output fits ``budget`` lines.

        Directory levels are expanded first; heading depth is added only once
        every directory is shown (or ``levels`` is given). If even the first
        level does not fit, ``first`` is set to the largest N that does. Any
        of ``levels``, ``depth`` and ``first`` that is given stays fixed.
        When nothing fits, the smallest tree is chosen.
        """
        if budget < 1:
            raise ValueError(f"budget must be at least 1, got {budget}")
        sizes: dict[tuple[int, int, int | None], int] = {}

        def size(lv: int, dp: int, n: int | None) -> int:
            key = (lv, dp, n)
            if key not in sizes:
                sizes[key] = self.tree(levels=lv, depth=dp or None, first=n).count("\n")
            return sizes[key]

        lv, dp, n = levels or 1, depth or 0, first
        if first is None and size(lv, dp, None) > budget:
            n = self._largest_first(lambda k: size(lv, dp, k) <= budget)
        if size(lv, dp, n) > budget:
            return TreeFit(lv, dp, n, size(lv, dp, n))  # nothing fits: the smallest tree

        def stopped(flag: str, lines: int) -> TreeFit:
            return TreeFit(lv, dp, n, size(lv, dp, n), flag, lines)

        if levels is None:
            while lv < _dir_height(self.root):
                if size(lv + 1, dp, n) > budget:
                    return stopped(f"-L {lv + 1}", size(lv + 1, dp, n))
                lv += 1
        if depth is None:
            max_depth = max(
                (_heading_height(heading_roots(f.doc)) for f in self._files()), default=0
            )
            while dp < max_depth:
                if size(lv, dp + 1, n) > budget:
                    return stopped(f"-d {dp + 1}", size(lv, dp + 1, n))
                dp += 1
        if n is not None and first is None:
            return stopped(f"-n {n + 1}", size(lv, dp, n + 1))
        return TreeFit(lv, dp, n, size(lv, dp, n))

    def grep(
        self,
        regex: re.Pattern[str],
        first: int | None = None,
        budget: int | None = None,
        lines: int = 0,
    ) -> Grouped:
        """Matching sections, grouped by file, the files with most matches first.

        ``lines`` shows up to that many matching lines under each section. See
        :meth:`grouped` for ``first`` and ``budget``.
        """
        groups: list[_Group] = []
        for node in self._files():
            found = section_matches(node.doc, regex)
            if found:
                children = [
                    (hit_line(s, len(m)) + snippets(m, lines, INDENT * 3), len(m)) for s, m in found
                ]
                groups.append(_Group(self.relative(node), node, children))
        groups.sort(key=lambda g: (-g.count, g.rel))
        return self.grouped(groups, matches, "section", first, budget)

    def items(
        self,
        word: str,
        lines_of: Callable[[FileNode], list[str]],
        first: int | None = None,
        budget: int | None = None,
    ) -> Grouped:
        """One summary line per item (e.g. table) in each file, in tree order.

        ``lines_of`` gives a file's item lines; ``word`` names an item. See
        :meth:`grouped` for ``first`` and ``budget``.
        """
        groups = []
        for node in self.files_in_order():
            lines = lines_of(node)
            if lines:
                groups.append(_Group(self.relative(node), node, [(line, 1) for line in lines]))
        return self.grouped(groups, lambda n: count(n, word), word, first, budget)

    def grouped(
        self,
        groups: list[_Group],
        unit: Callable[[int], str],
        child_word: str,
        first: int | None = None,
        budget: int | None = None,
    ) -> Grouped:
        """Render ``groups`` under a summary line.

        ``first`` shows the first N files and the first N lines in each,
        summarising the rest on ``… K more`` lines. With a ``budget`` and no
        ``first``, ``first`` is set to the largest N whose output fits (or 1).
        """
        for name, value in (("first", first), ("budget", budget)):
            if value is not None and value < 1:
                raise ValueError(f"{name} must be at least 1, got {value}")

        def render(n: int | None) -> list[str]:
            return self._grouped_lines(groups, unit, child_word, n)

        lines = render(first)
        if budget is not None and first is None and len(lines) > budget:
            first = self._largest_first(lambda n: len(render(n)) <= budget)
            lines = render(first)
        text = "".join(f"{line}\n" for line in lines)
        return Grouped(text, len(groups), sum(g.count for g in groups), first)

    def _grouped_lines(
        self,
        groups: list[_Group],
        unit: Callable[[int], str],
        child_word: str,
        first: int | None,
    ) -> list[str]:
        total = sum(g.count for g in groups)
        details = [unit(total)] + ([f"in {count(len(groups), 'file')}"] if groups else [])
        out = [f"{self.display} ({' '.join(details)})"]
        shown = groups if first is None else groups[:first]
        for group in shown:
            out.append(INDENT + _labelled(group.rel, group.node.title, [unit(group.count)]))
            children = group.children if first is None else group.children[:first]
            out += [INDENT * 2 + line for line, _ in children]
            hidden = group.children[len(children) :]
            if hidden:
                weight = sum(w for _, w in hidden)
                more = [count(len(hidden), child_word)]
                if unit(weight) != count(weight, child_word):
                    more.append(unit(weight))
                out.append(f"{INDENT * 2}… {len(hidden)} more ({', '.join(more)})")
        rest = groups[len(shown) :]
        if rest:
            weight = sum(g.count for g in rest)
            out.append(f"{INDENT}… {len(rest)} more ({count(len(rest), 'file')}, {unit(weight)})")
        return out

    def relative(self, node: FileNode) -> str:
        """``node``'s path relative to the library root, with ``/`` separators."""
        return node.path.relative_to(self.root.path).as_posix()

    def files_in_order(self) -> list[FileNode]:
        """Every file, in the order the tree lists them."""
        found: list[FileNode] = []

        def walk(node: DirNode) -> None:
            for entry in node.entries():
                if isinstance(entry, FileNode):
                    found.append(entry)
                else:
                    walk(entry)

        walk(self.root)
        return found

    def _files(self) -> list[FileNode]:
        found: list[FileNode] = []
        pending = [self.root]
        while pending:
            node = pending.pop()
            found.extend(node.files)
            pending.extend(node.dirs)
        return found

    def _largest_first(self, fits: Callable[[int], bool]) -> int:
        """The largest N for ``first`` that ``fits``, or 1 if none does."""
        lo, hi = 1, max(self.root.file_count + self.root.dir_count, 1)
        hi += sum(sum(1 for s in f.doc.walk() if not s.is_preamble) for f in self._files())
        if not fits(lo):
            return 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if fits(mid):
                lo = mid
            else:
                hi = mid - 1
        return lo


_ID_SUFFIX = re.compile(r"[SsTtDdFf]\d+(?:\.\d+)*")


@dataclass(frozen=True)
class Ref:
    """A file in a library, optionally narrowed to one section or table."""

    rel: str
    """The file's path relative to the library root, with ``/`` separators."""
    path: Path
    item: str | None = None
    """A section, table, diagram or fenced-block ID, upper-cased, or ``None``
    for the whole file."""


def resolve_ref(root: str | os.PathLike[str], ref: str) -> Ref:
    """Resolve ``PATH`` or ``PATH#ID`` against the library at ``root``.

    The path is relative to ``root`` and must stay inside it. Raises
    ``ValueError`` if it does not name a file there.

    >>> import tempfile, pathlib
    >>> root = pathlib.Path(tempfile.mkdtemp())
    >>> (root / "guides").mkdir()
    >>> _ = (root / "guides" / "install.md").write_text("# Install\\n")
    >>> ref = resolve_ref(root, "guides/install.md#s1.2")
    >>> ref.rel, ref.item
    ('guides/install.md', 'S1.2')
    >>> resolve_ref(root, "guides/../guides/install.md").item is None
    True
    >>> resolve_ref(root, "../secret.md")
    Traceback (most recent call last):
    ...
    ValueError: '../secret.md' is outside the directory
    """
    path_part, _, item = ref.rpartition("#")
    if not path_part or not _ID_SUFFIX.fullmatch(item):
        path_part, item = ref, ""
    normal = os.path.normpath(path_part)
    if os.path.isabs(normal) or normal == ".." or normal.startswith(".." + os.sep):
        raise ValueError(f"{ref!r} is outside the directory")
    path = Path(root) / normal
    if not path.is_file():
        raise ValueError(_missing_file(Path(root), normal))
    return Ref(Path(normal).as_posix(), path, item.upper() or None)


def _missing_file(root: Path, normal: str) -> str:
    message = f"no file {Path(normal).as_posix()!r}"
    if _ID_SUFFIX.fullmatch(normal):
        return f"{message}; on a directory, name the file: PATH#{normal.upper()}"
    parent = (root / normal).parent
    if parent.is_dir():
        nearby = sorted(
            e.name for e in parent.iterdir() if e.name.lower().endswith(MARKDOWN_SUFFIXES)
        )
        if nearby:
            message += f"; nearby: {', '.join(nearby[:5])}"
    return message


@dataclass(frozen=True)
class Grouped:
    """Lines grouped by file (grep hits, or tables etc.), as text."""

    text: str
    files: int
    """Files with at least one line."""
    total: int
    """What the lines add up to: matches, or items."""
    first: int | None
    """The ``first`` used: as given, or chosen to fit the budget."""


@dataclass(frozen=True)
class _Group:
    rel: str
    node: FileNode
    children: list[tuple[str, int]]
    """Each line under the file, with its weight (matches, or 1 per item)."""

    @property
    def count(self) -> int:
        return sum(weight for _, weight in self.children)


@dataclass(frozen=True)
class TreeFit:
    """The tree settings :meth:`Library.fit` chose for a line budget."""

    levels: int
    depth: int
    """Heading depth; 0 lists no headings."""
    first: int | None
    lines: int
    """Lines the tree takes with these settings."""
    next_step: str | None = None
    """The next expansion, as CLI flags, if it did not fit (e.g. ``-L 3``)."""
    next_lines: int | None = None
    """Lines the tree would take with ``next_step``."""

    def flags(self) -> str:
        """These settings as CLI flags, e.g. ``-L 2 -d 1``."""
        parts = [f"-L {self.levels}"]
        if self.depth:
            parts.append(f"-d {self.depth}")
        if self.first is not None:
            parts.append(f"-n {self.first}")
        return " ".join(parts)


@dataclass(frozen=True)
class _TreeOptions:
    levels: int
    first: int | None
    depth: int
    summaries: bool = False


class _Scanner:
    def __init__(
        self, root: Path, include: list[str], exclude: list[str], confine: Path | None = None
    ) -> None:
        self.root = root
        self.include = include
        self.exclude = exclude
        self.confine = confine
        """The resolved root when files must stay inside it."""
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
        if self.confine is not None:
            real = path.resolve()
            if real != self.confine and self.confine not in real.parents:
                self.skipped.append(f"{path}: links outside the directory")
                return None
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


def _labelled(name: str, title: Title | None, details: list[str]) -> str:
    label = f"{name} {title}" if title is not None and str(title) else name
    return f"{label} ({', '.join(details)})"


def _dir_line(node: DirNode, name: str) -> str:
    details = [count(node.file_count, "file")]
    if node.dir_count:
        details.append(count(node.dir_count, "dir"))
    if node.file_count:
        details.append(count(node.line_count, "line"))
    return _labelled(name, node.title, details)


def _file_line(node: FileNode, summaries: bool = False) -> str:
    details = [count(node.line_count, "line")]
    sections = node.section_count()
    if sections:
        details.append(count(sections, "section"))
    if node.doc.tables:
        details.append(count(len(node.doc.tables), "table"))
    if node.doc.diagrams:
        details.append(count(len(node.doc.diagrams), "diagram"))
    line = _labelled(node.name, node.title, details)
    if summaries and node.summary:
        line += f" — {node.summary}"
    return line


def _render_entries(node: DirNode, indent_level: int, opts: _TreeOptions, out: list[str]) -> None:
    indent = INDENT * indent_level
    entries = node.entries()
    shown = entries if opts.first is None else entries[: opts.first]
    for entry in shown:
        if isinstance(entry, FileNode):
            out.append(indent + _file_line(entry, opts.summaries))
            if opts.depth:
                _render_headings(entry, heading_roots(entry.doc), indent_level + 1, 1, opts, out)
            continue
        out.append(indent + _dir_line(entry, entry.name + "/"))
        if indent_level < opts.levels:
            _render_entries(entry, indent_level + 1, opts, out)
    hidden = entries[len(shown) :]
    if hidden:
        dirs = [e for e in hidden if isinstance(e, DirNode)]
        files = [e for e in hidden if isinstance(e, FileNode)]
        details = []
        if dirs:
            details.append(count(len(dirs), "dir"))
        if files:
            details.append(count(len(files), "file"))
        details.append(count(sum(e.line_count for e in hidden), "line"))
        out.append(f"{indent}… {len(hidden)} more ({', '.join(details)})")


def _dir_height(node: DirNode) -> int:
    """The ``levels`` needed to expand every directory under ``node``."""
    return 1 + max((_dir_height(d) for d in node.dirs), default=0)


def _heading_height(sections: list[Section]) -> int:
    return max((1 + _heading_height(s.children) for s in sections), default=0)


def heading_roots(doc: Document) -> list[Section]:
    """The sections a tree lists first: under a collapsed title, else the top level.

    >>> doc = Document.from_text("# Guide\\n## Install\\n## Use\\n")
    >>> [s.id for s in heading_roots(doc)]
    ['S1.1', 'S1.2']
    >>> [s.id for s in heading_roots(Document.from_text("# A\\n# B\\n"))]
    ['S1', 'S2']
    """
    top = [s for s in doc.sections if not s.is_preamble]
    return top[0].children if len(top) == 1 else top


def _render_headings(
    node: FileNode,
    sections: list[Section],
    indent_level: int,
    rel_depth: int,
    opts: _TreeOptions,
    out: list[str],
) -> None:
    indent = INDENT * indent_level
    shown = sections if opts.first is None else sections[: opts.first]
    lines = node.doc.lines
    for section in shown:
        at_limit = rel_depth >= opts.depth
        details = [str(section.body_line_count(lines))]
        if at_limit and section.children:
            details.append(f"{len(section.children)} sub")
        for items, word in ((node.doc.tables, "table"), (node.doc.diagrams, "diagram")):
            n = sum(1 for item in items if item.section_id == section.id)
            if n:
                details.append(count(n, word))
        out.append(f"{indent}[{section.id}] {section.title}".rstrip() + f" ({', '.join(details)})")
        if not at_limit:
            _render_headings(node, section.children, indent_level + 1, rel_depth + 1, opts, out)
    hidden = sections[len(shown) :]
    if hidden:
        span = sum(s.end - s.start for s in hidden)
        out.append(
            f"{indent}… {len(hidden)} more ({count(len(hidden), 'section')}, {count(span, 'line')})"
        )
