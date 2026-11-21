"""mdpeek as a ready-made MCP tool.

One general-purpose tool lets an agent read a docs directory (or allowed
URLs) a piece at a time: the map first, then sections, tables, diagrams and
code blocks by ID, a search, or SQL over a file's tables.

This module imports no MCP library. :meth:`Toolset.register` adds the tool
to any server that offers a FastMCP-style ``server.tool(name=...,
description=..., annotations=...)`` decorator: the official ``mcp`` SDK's
``FastMCP`` (1.x) and ``MCPServer`` (2.x), and standalone fastmcp.
:meth:`Toolset.tool` returns a plain async function for anything else.

>>> import tempfile, pathlib
>>> root = pathlib.Path(tempfile.mkdtemp())
>>> _ = (root / "guide.md").write_text("# Guide\\nHello.\\n## Install\\nRun it.\\n")
>>> docs = Toolset(docs_dir=root)
>>> print(docs.call_sync(source="guide.md"), end="")
[S1] Guide (1)
  [S1.1] Install (1)
>>> print(docs.call_sync(ids=["guide.md#S1.1"]), end="")
==> guide.md <==
[S1.1] Install
Run it.
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import logging
import os
import re
import sys
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from mdpeek import ops
from mdpeek.cache import Cache
from mdpeek.diagram_output import render_diagrams
from mdpeek.diagrams import DiagramNotFound
from mdpeek.engines import EngineUnavailable, QueryError
from mdpeek.fences import FenceNotFound, render_fences
from mdpeek.guard import OutsideRoot, UrlNotAllowed, UrlPolicy, confine
from mdpeek.library import DEFAULT_BUDGET, Library
from mdpeek.meta import render_meta
from mdpeek.model import Document, SectionNotFound
from mdpeek.options import CacheBackend, Engine, Format, Mode, coerce
from mdpeek.render import render
from mdpeek.source import DEFAULT_TIMEOUT, DEFAULT_TTL, FetchError, SourceInfo, is_url, load
from mdpeek.tables import SelectionError, TableNotFound, TableSettings

__all__ = ["ToolCall", "ToolError", "ToolOutcome", "ToolSpec", "Toolset"]

logger = logging.getLogger("mdpeek.mcp")

DEFAULT_NAME = "mdpeek"
Show = Literal["tables", "diagrams", "fences", "meta"]
FormatName = Literal["md", "csv", "tsv", "json", "jsonl"]
Mode_ = Literal["help", "map", "ids", "show", "grep", "sql"]

_SECTION_ID = re.compile(r"S\d+(?:\.\d+)*", re.IGNORECASE)
_ITEM_ID = re.compile(r"[TDF]\d+", re.IGNORECASE)
_KNOWN_ERRORS = (
    SectionNotFound,
    TableNotFound,
    DiagramNotFound,
    FenceNotFound,
    SelectionError,
    QueryError,
    EngineUnavailable,
    FetchError,
    OutsideRoot,
    UrlNotAllowed,
    FileNotFoundError,
    NotADirectoryError,
    ValueError,
)


class ToolError(ValueError):
    """A call the tool could not answer; the message says what to do instead."""


@dataclass(frozen=True)
class ToolCall:
    """A call to the tool, as hooks see it."""

    tool: str
    """The registered name."""
    mode: str
    """``help``, ``map``, ``ids``, ``show``, ``grep`` or ``sql``."""
    arguments: Mapping[str, Any]
    """The arguments as received. They may contain user text (SQL, grep patterns)."""


@dataclass(frozen=True)
class ToolOutcome:
    """What happened, for ``after_call``."""

    status: Literal["ok", "error", "denied"]
    duration_ms: float
    error_class: str | None = None
    error: str | None = None
    """The message the agent saw."""
    source_kind: Literal["docs_dir", "path", "url", "none"] = "none"
    output_chars: int = 0
    truncated: bool = False
    """A row, file, tree or output cap held something back."""
    cached: bool | None = None
    """For URL sources: whether the text came from the cache."""


BeforeCall = Callable[[ToolCall], "None | Awaitable[None]"]
AfterCall = Callable[[ToolCall, ToolOutcome], "None | Awaitable[None]"]
Wrap = Callable[[Callable[..., Awaitable[str]], str], Callable[..., Awaitable[str]]]


@dataclass(frozen=True)
class ToolSpec:
    """Everything a framework needs to register the tool."""

    name: str
    fn: Callable[..., Awaitable[str]]
    """An ``async def`` with a real signature; its docstring is ``description``."""
    description: str
    annotations: Mapping[str, Any]
    """MCP tool annotations (``readOnlyHint`` etc.) as a plain mapping."""


@dataclass
class _Result:
    text: str
    notes: list[str] = field(default_factory=list)
    truncated: bool = False
    source_kind: Literal["docs_dir", "path", "url", "none"] = "none"
    cached: bool | None = None


class Toolset:
    """Settings that limit what the tool can reach, and how much it returns.

    ``docs_dir`` confines every ``source`` to that directory and below
    (symlinks resolved). Without it the tool has no filesystem access.
    ``url_allow`` turns URL sources on for matching URLs (a prefix, a host, or
    ``*.host``), checked on every redirect; non-public addresses are refused
    unless ``allow_private_networks``. ``url_headers`` are sent with every
    fetch; the agent cannot add headers.
    """

    def __init__(
        self,
        docs_dir: str | os.PathLike[str] | None = None,
        *,
        url_allow: Iterable[str] = (),
        url_headers: Mapping[str, str] | None = None,
        allow_private_networks: bool = False,
        cache: CacheBackend | str | Cache | None = CacheBackend.MEMORY,
        ttl: float = DEFAULT_TTL,
        fetch_timeout: float = DEFAULT_TIMEOUT,
        engine: Engine | str = Engine.AUTO,
        sql: bool = True,
        query_timeout: float = 10.0,
        tables: TableSettings | None = None,
        diagram_summaries: bool = True,
        default_limit: int = 50,
        max_limit: int = 500,
        budget: int = DEFAULT_BUDGET,
        grep_lines: int = 2,
        catalog_lines: int = 300,
        max_output_chars: int = 40_000,
        formats: bool = False,
        errors: Literal["raise", "return"] = "raise",
    ) -> None:
        self.docs_dir = Path(docs_dir).resolve(strict=True) if docs_dir is not None else None
        if self.docs_dir is not None and not self.docs_dir.is_dir():
            raise NotADirectoryError(f"docs_dir is not a directory: {os.fspath(docs_dir or '')!r}")
        allow = tuple(url_allow)
        self.url_policy = UrlPolicy(allow, allow_private=allow_private_networks) if allow else None
        self.url_headers = dict(url_headers or {})
        self.cache = cache
        self.ttl = ttl
        self.fetch_timeout = fetch_timeout
        self.engine = coerce(Engine, engine)
        self.sql = sql
        self.query_timeout = query_timeout
        self.tables = tables or TableSettings()
        self.diagram_summaries = diagram_summaries
        self.default_limit = default_limit
        self.max_limit = max_limit
        self.budget = budget
        self.grep_lines = grep_lines
        self.catalog_lines = catalog_lines
        self.max_output_chars = max_output_chars
        self.formats = formats
        if errors not in ("raise", "return"):
            raise ValueError(f"errors must be 'raise' or 'return', got {errors!r}")
        self.errors = errors

    # -- calling -------------------------------------------------------------

    async def call(self, **arguments: Any) -> str:
        """Run one call off the event loop and return the text the agent sees.

        Takes the tool's arguments (``source``, ``ids``, ``show``, ``grep``,
        ``sql``, ``depth``, ``full``, ``rows``, ``cols``, ``limit``, and
        ``format`` when enabled, ``help``). Raises :class:`ToolError`, or returns
        ``error: ...`` text when ``errors="return"``. No hooks run here; see
        :meth:`tool`.
        """
        try:
            result = await asyncio.to_thread(self._execute, arguments)
        except ToolError as exc:
            if self.errors == "return":
                return f"error: {exc}\n"
            raise
        return self._finish(result)

    def call_sync(self, **arguments: Any) -> str:
        """:meth:`call` for sync code and tests."""
        try:
            result = self._execute(arguments)
        except ToolError as exc:
            if self.errors == "return":
                return f"error: {exc}\n"
            raise
        return self._finish(result)

    def _finish(self, result: _Result) -> str:
        text = result.text
        if not text.endswith("\n") and text:
            text += "\n"
        if len(text) > self.max_output_chars:
            cut = text.rfind("\n", 0, self.max_output_chars)
            text = text[: cut + 1 if cut > 0 else self.max_output_chars]
            result.notes.append(
                f"output cut at {self.max_output_chars} characters; ask for less "
                "(fewer ids, a smaller depth, rows or limit)"
            )
            result.truncated = True
        return text + "".join(f"note: {self._scrub(note)}\n" for note in result.notes)

    def _scrub(self, message: str) -> str:
        """Drop the docs directory's absolute path: the agent never needs it."""
        if self.docs_dir is None:
            return message
        return message.replace(f"{self.docs_dir}{os.sep}", "").replace(str(self.docs_dir), ".")

    # -- the work ------------------------------------------------------------

    def _execute(
        self,
        arguments: Mapping[str, Any],
        name: str = DEFAULT_NAME,
        help_text: Callable[[], str] | None = None,
    ) -> _Result:
        if arguments.get("help"):
            return _Result(help_text() if help_text else self.help(name))
        args = _Args.parse(arguments, self)
        try:
            return self._dispatch(args)
        except ToolError:
            raise
        except _KNOWN_ERRORS as exc:
            raise ToolError(self._scrub(_message(exc))) from exc

    def _dispatch(self, args: _Args) -> _Result:
        if args.source is not None and is_url(args.source):
            return self._from_url(args)
        target, kind = self._resolve_path(args.source)
        if target.is_dir():
            result = self._on_directory(args, target)
        else:
            result = self._on_file(args, _parse(target), label=None)
        result.source_kind = kind
        return result

    def _resolve_path(self, source: str | None) -> tuple[Path, Literal["docs_dir", "path"]]:
        if self.docs_dir is None:
            if source is None:
                hint = " pass source=URL" if self.url_policy else ""
                raise ToolError(f"no docs directory is configured;{hint or ' nothing to read'}")
            raise ToolError("reading files is not enabled; only allowed URLs can be read")
        return confine(self.docs_dir, source), "docs_dir" if source is None else "path"

    def _from_url(self, args: _Args) -> _Result:
        if self.url_policy is None:
            raise ToolError("URL sources are not enabled")
        text, info = load(
            args.source or "",
            headers=self.url_headers,
            cache=self.cache,
            ttl=self.ttl,
            timeout=self.fetch_timeout,
            check=self.url_policy.check,
        )
        doc = Document.from_text(text)
        doc.source = info
        result = self._on_file(args, doc, label=None)
        result.source_kind = "url"
        result.cached = info.from_cache
        line = SourceInfo.cached_line(info)
        if line:
            result.notes.insert(0, line.strip("()"))
        return result

    # -- one file ------------------------------------------------------------

    def _on_file(self, args: _Args, doc: Document, label: str | None) -> _Result:
        sections = args.section_ids
        if args.mode == "map":
            if args.full:  # the whole file, asked for explicitly
                return _Result(
                    render(doc, Mode.FULL, args.depth, None, self.tables, self.diagram_summaries)
                )
            return _Result(render(doc, Mode.STRUCTURE, args.depth))
        if args.mode == "grep":
            return _from_ops(ops.grep_file(doc, args.grep or "", sections, lines=self.grep_lines))
        if args.mode == "show":
            return self._show_file(doc, args)
        if args.mode == "sql":
            return self._query(doc, args)
        return self._fetch(doc, args, label)

    def _show_file(self, doc: Document, args: _Args) -> _Result:
        if args.show == "meta":
            if doc.meta is None:
                return _Result("", ["no front matter"])
            return _Result(render_meta(doc.meta, args.fmt))
        kind = cast("ops.ListKind", args.show or "tables")
        out = ops.list_file(doc, kind, args.section_ids, self.tables, args.fmt)
        if not out.text:
            out.notes.append(f"no {args.show}")
        return _from_ops(out)

    def _query(self, doc: Document, args: _Args) -> _Result:
        limit = self.max_limit if args.full else args.limit
        out = ops.query(
            doc,
            args.sql or "",
            self.engine,
            args.section_ids,
            limit=limit,
            fmt=args.fmt,
            safe=True,
            timeout=self.query_timeout,
        )
        result = _from_ops(out)
        if out.truncated and out.query is not None:
            shown = "the first" if out.query.more else f"{out.shown} of {out.query.total}"
            result.notes.append(
                f"query: showing {shown} {out.shown} rows; raise limit (up to {self.max_limit}) "
                "or refine the query"
                if out.query.more
                else f"query: showing {shown} rows; raise limit (up to {self.max_limit})"
            )
        return result

    def _fetch(self, doc: Document, args: _Args, label: str | None) -> _Result:
        groups: dict[str, list[str]] = {}
        for item in args.ids:
            groups.setdefault(_kind(item), []).append(item)
        if (args.rows or args.cols) and "table" not in groups:
            raise ToolError("rows and cols only apply to table IDs (T1, T2, ...)")
        blocks: list[str] = []
        result = _Result("")
        for kind, items in groups.items():
            if kind == "section":
                mode = Mode.FULL if args.full else Mode.VIEW
                blocks.append(
                    render(doc, mode, args.depth, items, self.tables, self.diagram_summaries)
                )
            elif kind == "table":
                out = ops.tables(
                    doc,
                    items,
                    rows=args.rows,
                    cols=args.cols,
                    limit=args.limit,
                    full=args.full,
                    settings=self.tables,
                    fmt=args.fmt,
                )
                blocks.append(out.text)
                for selection in out.selections:
                    if selection.truncated:
                        result.notes.append(
                            f"{selection.table.id}: showing {len(selection.rows)} of "
                            f"{selection.matched} rows (use rows, limit or full)"
                        )
                result.truncated |= out.truncated
            elif kind == "diagram":
                found = [doc.diagram(i) for i in items]
                blocks.append(render_diagrams(found, args.fmt, label_single=len(groups) > 1))
            elif kind == "fence":
                found = [doc.fence(i) for i in items]
                blocks.append(render_fences(found, args.fmt, label_single=len(groups) > 1))
            elif doc.meta is None:
                result.notes.append("no front matter")
            else:
                blocks.append(render_meta(doc.meta, args.fmt))
        result.text = "\n".join(b.rstrip("\n") + "\n" for b in blocks if b)
        if label is not None:
            result.text = f"==> {label} <==\n{result.text}"
        return result

    # -- a directory ---------------------------------------------------------

    def _on_directory(self, args: _Args, root: Path) -> _Result:
        if args.mode == "sql":
            raise ToolError("sql works on one file; pass source=PATH to a file")
        if args.full and args.mode == "map":
            raise ToolError("full applies to one file or to ids; pass source=PATH to a file")
        if args.mode == "ids":
            return self._fetch_from_directory(args, root)
        if args.ids:
            raise ToolError(
                f"in a directory, ids name items as PATH#ID; to scope {args.mode} to sections, "
                "pass source=PATH to a file"
            )
        library = Library.from_path(root, confine=True)
        library.display = self._display(root)  # never show the server's absolute path
        if args.mode == "map":
            out = ops.tree(library, self.budget, depth=args.depth, summaries=True)
            result = _from_ops(out)
            if out.fit is not None and out.truncated:
                result.notes.append(
                    f"tree: fitted to {self.budget} lines; open a folder or file with "
                    "source=PATH, or search with grep"
                )
            return result
        if args.mode == "grep":
            out = ops.grep_library(
                library, args.grep or "", budget=self.budget, lines=self.grep_lines
            )
            return self._grouped(out, "matching sections")
        if args.show == "meta":
            result = _from_ops(ops.meta_library(library, args.fmt))
            if not result.text.strip():
                result.notes.append("no file has front matter")
            return result
        kind = cast("ops.ListKind", args.show or "tables")
        if args.fmt is Format.MD:
            out = ops.list_library(library, kind, self.tables, budget=self.budget)
        else:
            out = ops.list_library(library, kind, self.tables, fmt=args.fmt)
        return self._grouped(out, kind)

    def _display(self, root: Path) -> str:
        rel = root.relative_to(self.docs_dir).as_posix() if self.docs_dir else root.name
        return "./" if rel in ("", ".") else f"{rel}/"

    def _grouped(self, out: ops.Output, what: str) -> _Result:
        result = _from_ops(out)
        if out.truncated and out.grouped is not None and out.grouped.first is not None:
            result.notes.append(
                f"showing the first {out.grouped.first} files and {out.grouped.first} "
                f"{what} in each, to fit {self.budget} lines; narrow with source=PATH"
            )
        return result

    def _fetch_from_directory(self, args: _Args, root: Path) -> _Result:
        files: dict[str, list[str] | None] = {}  # None: the whole file
        for raw in args.ids:
            path, _, item = raw.rpartition("#")
            if not path:  # a bare path: the whole file
                if raw.lower() == "meta" or _SECTION_ID.fullmatch(raw) or _ITEM_ID.fullmatch(raw):
                    raise ToolError(
                        f"in a directory, name the file: PATH#ID (e.g. guides/install.md#{raw}), "
                        f"or PATH for the whole file; got {raw!r}"
                    )
                files[raw] = None
            elif not item:
                raise ToolError(f"empty ID after '#' in {raw!r}")
            elif path not in files:
                files[path] = [item]
            elif (wanted := files[path]) is not None:  # a whole file already covers it
                wanted.append(item)
        blocks: list[str] = []
        result = _Result("")
        for path, items in files.items():
            target = confine(root, path)
            if not target.is_file():
                raise ToolError(f"{path!r} is a folder; use source={path!r} for its tree")
            rel = target.relative_to(root).as_posix() if root in target.parents else path
            if items is None:
                mode = Mode.FULL if args.full else Mode.VIEW
                text = render(
                    _parse(target), mode, args.depth, None, self.tables, self.diagram_summaries
                )
                blocks.append(f"==> {rel} <==\n{text}")
                continue
            sub = self._on_file(args.with_ids(items), _parse(target), label=rel)
            blocks.append(sub.text)
            result.notes += [f"{rel}: {n}" for n in sub.notes]
            result.truncated |= sub.truncated
        result.text = "\n".join(blocks)
        return result

    # -- the tool ------------------------------------------------------------

    def _where(self) -> str:
        where = []
        if self.docs_dir is not None:
            where.append("the docs directory")
        if self.url_policy is not None:
            where.append("allowed URLs")
        return " and ".join(where) or "nothing (no docs directory or URLs configured)"

    def description(self, name: str = DEFAULT_NAME) -> str:
        """The tool's description: a short usage pattern, because every session
        pays for it; :meth:`help` has the rest."""
        sql = ", sql= to query a file's tables" if self.sql else ""
        return (
            f"Read {self._where()} a piece at a time. Start with help=True: it lists every "
            "document with a one-line summary and explains every call. Then grep several "
            'related terms at once (grep="a|b|c" shows matching lines) and read every '
            'relevant document: ids=["guide.md", "faq.md"] for whole files, '
            f'ids=["guide.md#S2"] for sections{sql}. Answers are often split across '
            "documents: the obvious one gives part, while caveats, exceptions, later changes "
            "and specific values live elsewhere, so keep searching until every part of the "
            "question is covered."
        )

    def help(self, name: str = DEFAULT_NAME) -> str:
        """The full guide, returned by a call with ``help=True``: how to research a
        question, every call, the rules, and a catalog of the documents."""
        lines = [
            f"# {name}: read {self._where()} a piece at a time",
            "",
            "## How to research a question",
            "",
            "1. Read the document list below (or call with no arguments for the tree).",
            "   Shortlist every document whose title or summary could bear on the question;",
            '   for "why" or "list every" questions, err on the side of more.',
            "2. Search several terms at once, including column names, statuses and",
            '   synonyms: grep="unknown|missing|-1". Results show the matching lines.',
            '3. Read whole documents with ids=["a.md", "b.md"], several per call; read',
            '   parts of long documents by section: ids=["a.md#S2"].',
            "4. The obvious document is rarely the whole answer. After reading it, grep for",
            "   the names it mentions (tables, columns, statuses, clients) to find caveats and",
            "   exceptions elsewhere, and follow cross-references.",
            "5. When documents disagree, prefer the more specific or more recent one and say",
            "   which you followed.",
            "6. Before answering, check every part of the question against what you found.",
            "   If a part rests on a single document, search once more for that topic, and",
            "   check the list again for documents you have not opened.",
            "",
            "## Calls",
            "",
            f"{name}()                          tree: each file with its title and summary",
            f'{name}(source="a.md")             outline of one file: [S1.2] Title (own lines)',
            f'{name}(ids=["a.md", "b.md"])      whole files (full=True adds every level)',
            f'{name}(ids=["a.md#S2"])           a section, subsections as one-line stubs;',
            "                                   depth=2 or full=True for more",
            f'{name}(ids=["a.md#T1"], rows="10-20", cols="name,region", limit=50)',
            f'{name}(ids=["a.md#D1", "a.md#F2"]) diagram or code block source',
            f'{name}(ids=["a.md#meta"])         front matter',
            f'{name}(grep="retry|timeout")      matching sections and lines (regex; smart case)',
            f'{name}(show="tables")             one line per table; also diagrams, fences, meta',
        ]
        if self.sql:
            lines.append(f'{name}(source="a.md", sql="select region, count(*) from t1 group by 1")')
        lines += [
            "",
            "## Rules",
            "",
            "- Pass at most one of ids, show, grep" + (", sql." if self.sql else "."),
            "- IDs come from outlines and never from heading text: S2.1 section, T3 table,",
            "  D1 diagram, F4 code block, meta. In a directory, prefix the file: PATH#ID.",
            '- With source set to one file, ids=["S2"] scopes show, grep'
            + (" or sql" if self.sql else "")
            + " to sections.",
            "- Line counts in outlines exclude subsections; `6×320` is columns × rows.",
            "- Large tables and diagrams inside sections appear as one-line [T1] / [D1] stubs.",
            f"- Output stops at {self.budget} lines for trees and lists, and at "
            f"{self.max_output_chars:,} characters overall.",
            "- Notes at the end start with 'note:': rows held back, truncation, cache.",
        ]
        if self.sql:
            lines += [
                "- SQL: tables load as t1, t2, ... with the column names shown by the table",
                f"  view; read-only (SELECT); {self.default_limit} rows by default, limit= up to "
                f"{self.max_limit}.",
            ]
        lines += self._catalog()
        return "\n".join(lines) + "\n"

    def _catalog(self) -> list[str]:
        """``## Documents``: every file with its title and summary, up to catalog_lines."""
        if self.docs_dir is None or self.catalog_lines < 1:
            return []
        library = Library.from_path(self.docs_dir, confine=True)
        entries = []
        for node in library.files_in_order():
            label = library.relative(node)
            if node.title is not None:
                label += f": {node.title.text}"
            if node.summary:
                label += f" — {node.summary}"
            entries.append(f"- {label}")
        shown = entries[: self.catalog_lines]
        out = ["", "## Documents", "", *shown]
        if len(entries) > len(shown):
            out.append(f"- … {len(entries) - len(shown)} more: use the tree or grep")
        return out

    def instructions(self, name: str = DEFAULT_NAME) -> str:
        """A short paragraph a server can add to its MCP ``instructions``."""
        return (
            f"For documentation, call {name}(help=True) first: it lists every document with "
            "a summary. Then grep for the topic and read the relevant documents whole or by "
            "section" + (", and use sql to answer questions from a table." if self.sql else ".")
        )

    def tool(
        self,
        name: str = DEFAULT_NAME,
        *,
        description: str | None = None,
        description_prefix: str | None = None,
        description_suffix: str | None = None,
        help_prefix: str | None = None,
        help_suffix: str | None = None,
        before_call: BeforeCall | None = None,
        after_call: AfterCall | None = None,
        wrap: Wrap | None = None,
        error_type: type[Exception] | None = None,
    ) -> ToolSpec:
        """The tool as an async function with a real signature, plus metadata.

        Order on each call: ``wrap`` (outermost) → ``before_call`` → the work
        → ``after_call``. ``after_call`` runs even when the call fails or is
        refused, and an exception it raises is logged, never passed on.
        ``before_call`` may raise ``PermissionError`` to refuse the call.

        ``description_prefix`` / ``description_suffix`` and ``help_prefix`` /
        ``help_suffix`` wrap mdpeek's text with the host's own context (what the
        docs cover, "start here", aliases, links); ``description`` replaces the
        default description, which the prefix and suffix then wrap.

        ``error_type`` is the framework's own tool-error class: mdpeek's errors
        and refusals are re-raised as it, so the framework shows the message to
        the client (some hide the message of any other exception).
        """
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name):
            raise ValueError(f"invalid tool name {name!r}: use letters, digits, _ . -")
        text = _wrap(description_prefix, description or self.description(name), description_suffix)
        toolset = self

        def help_text() -> str:
            return _wrap(help_prefix, toolset.help(name), help_suffix) + "\n"

        async def run(**arguments: Any) -> str:
            given = {k: v for k, v in arguments.items() if v is not None and v is not False}
            call = ToolCall(name, _mode_of(given), given)
            start = time.monotonic()
            status: Literal["ok", "error", "denied"] = "ok"
            error: BaseException | None = None
            message: str | None = None
            result: _Result | None = None
            try:
                if before_call is not None:
                    await _maybe_await(before_call(call))
                result = await asyncio.to_thread(toolset._execute, arguments, name, help_text)
                return toolset._finish(result)
            except PermissionError as exc:
                status, error, message = "denied", exc, str(exc) or "not allowed"
                if toolset.errors == "return":
                    return f"error: {message}\n"
                if error_type is not None:
                    raise error_type(message) from exc
                raise
            except ToolError as exc:
                status, error, message = "error", exc, str(exc)
                if toolset.errors == "return":
                    return f"error: {message}\n"
                if error_type is not None:
                    raise error_type(message) from exc
                raise
            except Exception as exc:
                status, error, message = "error", exc, str(exc)
                raise
            finally:
                if after_call is not None:
                    outcome = ToolOutcome(
                        status=status,
                        duration_ms=(time.monotonic() - start) * 1000.0,
                        error_class=type(error).__name__ if error is not None else None,
                        error=message,
                        source_kind=result.source_kind if result else "none",
                        output_chars=_output_chars(toolset, result),
                        truncated=result.truncated if result else False,
                        cached=result.cached if result else None,
                    )
                    try:
                        await _maybe_await(after_call(call, outcome))
                    except Exception:
                        logger.exception("after_call hook failed for %s", name)

        fn = _with_signature(run, name, text, self)
        if wrap is not None:
            fn = wrap(fn, name)
        annotations = {
            "title": "Read markdown",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": self.url_policy is not None,
        }
        return ToolSpec(name, fn, text, annotations)

    def register(
        self,
        server: Any,
        name: str = DEFAULT_NAME,
        *,
        description: str | None = None,
        description_prefix: str | None = None,
        description_suffix: str | None = None,
        help_prefix: str | None = None,
        help_suffix: str | None = None,
        before_call: BeforeCall | None = None,
        after_call: AfterCall | None = None,
        wrap: Wrap | None = None,
    ) -> ToolSpec:
        """Add the tool to a FastMCP-style ``server`` and return its spec.

        Uses ``server.tool(name=..., description=..., annotations=...)(fn)``,
        and turns off structured output (``structured_output=False`` on the
        official SDK, ``output_schema=None`` on fastmcp) so the text is sent
        once. See :meth:`tool` for the hooks.
        """
        spec = self.tool(
            name,
            description=description,
            description_prefix=description_prefix,
            description_suffix=description_suffix,
            help_prefix=help_prefix,
            help_suffix=help_suffix,
            before_call=before_call,
            after_call=after_call,
            wrap=wrap,
            error_type=_framework_tool_error(server),
        )
        try:
            accepted = inspect.signature(server.tool).parameters
        except (TypeError, ValueError):  # pragma: no cover - builtins without signatures
            accepted = {}
        options: dict[str, Any] = {"name": spec.name, "description": spec.description}
        if "annotations" in accepted:
            options["annotations"] = _tool_annotations(spec.annotations)
        if "structured_output" in accepted:  # the official SDK (FastMCP 1.x, MCPServer 2.x)
            options["structured_output"] = False
        elif "output_schema" in accepted:  # standalone fastmcp
            options["output_schema"] = None
        server.tool(**options)(spec.fn)
        return spec


# -- arguments -----------------------------------------------------------------


@dataclass(frozen=True)
class _Args:
    mode: Mode_
    source: str | None
    ids: tuple[str, ...]
    show: str | None
    grep: str | None
    sql: str | None
    depth: int | None
    full: bool
    rows: str | None
    cols: list[str] | None
    limit: int | None
    fmt: Format

    @property
    def section_ids(self) -> list[str] | None:
        """``ids`` used as section scope for show, grep and sql."""
        if self.mode == "ids" or not self.ids:
            return None
        bad = [i for i in self.ids if not _SECTION_ID.fullmatch(i)]
        if bad:
            raise ToolError(f"with {self.mode}, ids scope sections (S1, S2.3); got {bad}")
        return list(self.ids)

    def with_ids(self, ids: list[str]) -> _Args:
        return dataclasses.replace(self, ids=tuple(ids))

    @classmethod
    def parse(cls, arguments: Mapping[str, Any], toolset: Toolset) -> _Args:
        known = {"source", "ids", "show", "grep", "sql", "depth", "full", "rows", "cols", "limit"}
        known.add("help")
        if toolset.formats:
            known.add("format")
        unknown = sorted(set(arguments) - known)
        if unknown:
            raise ToolError(f"unknown argument(s): {', '.join(unknown)}")
        get = arguments.get
        ids = get("ids") or []
        if isinstance(ids, str):
            ids = [ids]
        given = {k: get(k) for k in ("show", "grep", "sql") if get(k) not in (None, "")}
        if len(given) > 1:
            raise ToolError(f"pass only one of {', '.join(sorted(given))}")
        if "sql" in given and not toolset.sql:
            raise ToolError("SQL is not enabled for this tool")
        show = given.get("show")
        if show is not None and show not in ("tables", "diagrams", "fences", "meta"):
            raise ToolError(f"show must be tables, diagrams, fences or meta, got {show!r}")
        mode = _mode_of({**given, "ids": ids})
        depth = get("depth")
        if depth is not None and depth < 1:
            raise ToolError(f"depth must be at least 1, got {depth}")
        limit = get("limit")
        if limit is not None:
            if limit < 1:
                raise ToolError(f"limit must be at least 1, got {limit}")
            limit = min(limit, toolset.max_limit)
        elif mode == "sql":
            limit = toolset.default_limit
        cols = get("cols")
        if isinstance(cols, str):
            cols = [c.strip() for c in cols.split(",") if c.strip()]
        fmt = coerce(Format, get("format") or Format.MD)
        if mode in ("map", "grep") and fmt is not Format.MD:
            raise ToolError(f"format applies to tables, lists and sql, not {mode}")
        if mode != "ids" and (get("rows") or cols):
            raise ToolError("rows and cols only apply when fetching table IDs")
        return cls(
            mode=mode,
            source=get("source") or None,
            ids=tuple(str(i).strip() for i in ids),
            show=show,
            grep=given.get("grep"),
            sql=given.get("sql"),
            depth=depth,
            full=bool(get("full")),
            rows=get("rows") or None,
            cols=cols or None,
            limit=limit,
            fmt=fmt,
        )


def _mode_of(given: Mapping[str, Any]) -> Mode_:
    if given.get("help"):
        return "help"
    for mode in ("sql", "grep", "show"):
        if given.get(mode):
            return mode  # type: ignore[return-value]
    return "ids" if given.get("ids") else "map"


def _kind(item: str) -> str:
    if item.lower() == "meta":
        return "meta"
    if _SECTION_ID.fullmatch(item):
        return "section"
    if _ITEM_ID.fullmatch(item):
        return {"t": "table", "d": "diagram", "f": "fence"}[item[0].lower()]
    raise ToolError(
        f"unknown ID {item!r}: use S2.1 (section), T1 (table), D1 (diagram), F1 (code block) "
        "or meta"
    )


# -- helpers -------------------------------------------------------------------


@lru_cache(maxsize=64)
def _parse_cached(path: str, mtime_ns: int, size: int) -> Document:
    return Document.from_path(path)


def _parse(path: Path) -> Document:
    stat = path.stat()
    return _parse_cached(os.fspath(path), stat.st_mtime_ns, stat.st_size)


def _from_ops(out: ops.Output) -> _Result:
    return _Result(out.text, list(out.notes), out.truncated)


def _message(exc: BaseException) -> str:
    if isinstance(exc, FileNotFoundError) and exc.filename is None:
        return str(exc)
    if isinstance(exc, OSError):
        return f"cannot read {exc.filename!r}: {exc.strerror or exc}"
    if isinstance(exc, FetchError):
        return f"cannot fetch: {exc}"
    return str(exc).replace("--grep pattern", "grep pattern")


def _output_chars(toolset: Toolset, result: _Result | None) -> int:
    if result is None:
        return 0
    return min(len(result.text), toolset.max_output_chars)


async def _maybe_await(value: Any) -> None:
    if inspect.isawaitable(value):
        await value


def _wrap(prefix: str | None, text: str, suffix: str | None) -> str:
    """``text`` with the host's prefix and suffix, each separated by a blank line."""
    parts = [p.strip("\n") for p in (prefix, text, suffix) if p]
    return "\n\n".join(parts)


PARAMETER_DOCS = {
    "source": 'A file or folder inside the docs directory (e.g. "guides/install.md"), or an '
    "allowed URL. Omit for the whole docs directory.",
    "ids": 'What to read, several per call: whole files ("guides/install.md"), sections '
    "(S2.1), tables (T1), diagrams (D1), code blocks (F1) or front matter (meta). In a "
    'directory, prefix the file: "guides/install.md#S2".',
    "show": "List items across the docs or one file: tables, diagrams, fences or meta.",
    "grep": "A regex; returns matching sections with their matching lines. Combine terms: "
    '"retry|timeout|backoff".',
    "sql": "A read-only SELECT over one file's tables (t1, t2, ...); needs source=<file>.",
    "depth": "Heading levels to show in an outline or section.",
    "full": "With a file: every level. With section ids: each section with everything below it.",
    "rows": 'Table rows to show, e.g. "10-20".',
    "cols": 'Table columns to show, e.g. "name,region".',
    "limit": "Maximum rows for a table or SQL result.",
    "format": "Output format for tables, lists and SQL: md (default), csv, tsv, json or jsonl.",
    "help": "The usage guide and a list of every document with its summary. Read it before "
    "assuming how this tool works.",
}


def _documented(params: list[inspect.Parameter]) -> list[inspect.Parameter]:
    """Attach PARAMETER_DOCS as pydantic field descriptions, when pydantic is installed
    (every MCP library depends on it), so they appear in the input schema."""
    try:
        from pydantic import Field  # ty: ignore[import-not-found]
    except ImportError:  # pragma: no cover - MCP libraries always bring pydantic
        return params
    return [
        p.replace(annotation=Annotated[p.annotation, Field(description=PARAMETER_DOCS[p.name])])
        if p.name in PARAMETER_DOCS
        else p
        for p in params
    ]


def _with_signature(
    run: Callable[..., Awaitable[str]], name: str, description: str, toolset: Toolset
) -> Callable[..., Awaitable[str]]:
    """Give ``run`` the tool's public signature, so frameworks build the right schema."""
    kw = inspect.Parameter.KEYWORD_ONLY
    params = [
        inspect.Parameter("source", kw, default=None, annotation=str | None),
        inspect.Parameter("ids", kw, default=None, annotation=list[str] | None),
        inspect.Parameter("show", kw, default=None, annotation=Show | None),
        inspect.Parameter("grep", kw, default=None, annotation=str | None),
    ]
    if toolset.sql:
        params.append(inspect.Parameter("sql", kw, default=None, annotation=str | None))
    params += [
        inspect.Parameter("depth", kw, default=None, annotation=int | None),
        inspect.Parameter("full", kw, default=False, annotation=bool),
        inspect.Parameter("rows", kw, default=None, annotation=str | None),
        inspect.Parameter("cols", kw, default=None, annotation=str | None),
        inspect.Parameter("limit", kw, default=None, annotation=int | None),
    ]
    if toolset.formats:
        params.append(inspect.Parameter("format", kw, default=None, annotation=FormatName | None))
    params.append(inspect.Parameter("help", kw, default=False, annotation=bool))
    params = _documented(params)

    async def tool_fn(**arguments: Any) -> str:
        return await run(**arguments)

    tool_fn.__name__ = name.replace("-", "_").replace(".", "_")
    tool_fn.__qualname__ = tool_fn.__name__
    tool_fn.__doc__ = description
    tool_fn.__signature__ = inspect.Signature(params, return_annotation=str)  # ty: ignore[missing-attribute]
    annotations = {p.name: p.annotation for p in params} | {"return": str}
    tool_fn.__annotations__ = annotations
    if sys.version_info >= (3, 14):
        # functools.wraps copies __annotate__ (not __annotations__) from 3.14, so a
        # host's decorator only keeps these types if __annotate__ provides them.
        def annotate(format: int) -> dict[str, Any]:
            if format != 1:  # annotationlib.Format.VALUE
                raise NotImplementedError
            return dict(annotations)

        tool_fn.__annotate__ = annotate
    return tool_fn


_TOOL_ERRORS = (  # (module prefix of the server class, where its ToolError lives)
    ("fastmcp", "fastmcp.exceptions"),
    ("mcp.server.mcpserver", "mcp.server.mcpserver.exceptions"),
    ("mcp.server.fastmcp", "mcp.server.fastmcp.exceptions"),
)


def _framework_tool_error(server: Any) -> type[Exception] | None:
    """The ToolError class of the library ``server`` comes from, if known."""
    import importlib

    for cls in type(server).__mro__:
        for prefix, module in _TOOL_ERRORS:
            if cls.__module__ == prefix or cls.__module__.startswith(prefix + "."):
                try:
                    return getattr(importlib.import_module(module), "ToolError", None)
                except ImportError:  # pragma: no cover - a partial install
                    return None
    return None


def _tool_annotations(values: Mapping[str, Any]) -> Any:
    """``mcp.types.ToolAnnotations`` when the MCP SDK is installed, else the mapping."""
    try:
        from mcp.types import ToolAnnotations  # ty: ignore[import-not-found]
    except ImportError:
        return dict(values)
    return ToolAnnotations.model_validate(dict(values))  # camelCase works in 1.x and 2.x
