"""Command-line interface for mdpeek."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from mdpeek import __version__
from mdpeek.cache import DEFAULT_TTL, CacheBackend
from mdpeek.diagram_output import render_diagram_list, render_diagrams
from mdpeek.diagrams import DiagramNotFound
from mdpeek.engines import EngineUnavailable, QueryError, QueryResult, run_query
from mdpeek.formats import format_rows, to_json
from mdpeek.model import Document, SectionNotFound
from mdpeek.options import Engine, Format, Mode, OnTableError
from mdpeek.render import render
from mdpeek.source import DEFAULT_TIMEOUT, FetchError, SourceInfo, is_url, load, parse_header
from mdpeek.table_output import (
    DEFAULT_LIMIT,
    render_table,
    render_table_list,
    select,
    truncation_note,
)
from mdpeek.tables import SelectionError, TableNotFound, TableSettings

EXIT_USAGE = 2

_DATA_FLAGS = ("rows", "cols", "limit", "format")
_MACHINE_FORMATS = {f.value for f in Format} - {Format.MD.value}


def _flags(used: list[str]) -> str:
    return ", ".join(used)


def _verb(used: list[str]) -> str:
    return "applies" if len(used) == 1 else "apply"


class UsageError(Exception):
    """A problem with the arguments or the document, reported on stderr."""


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be a whole number of at least 1, got {value!r}")
    return number


def _column_list(value: str) -> list[str]:
    return [column for column in (c.strip() for c in value.split(",")) if column]


def build_parser() -> argparse.ArgumentParser:
    defaults = TableSettings()
    parser = argparse.ArgumentParser(
        prog="mdpeek",
        description="Progressively expose a markdown document by section.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("source", help="markdown file path, http(s) URL, or '-' for stdin")
    parser.add_argument(
        "-s",
        "--section",
        action="append",
        metavar="ID",
        help="show only this section (e.g. S2.1); repeatable; also scopes --tables",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--structure",
        dest="mode",
        action="store_const",
        const=Mode.STRUCTURE,
        help="headings and line counts only",
    )
    modes.add_argument(
        "--full",
        dest="mode",
        action="store_const",
        const=Mode.FULL,
        help="all content (down to --depth); with --table/--tables, every row",
    )
    parser.set_defaults(mode=Mode.VIEW)
    parser.add_argument(
        "-d",
        "--depth",
        type=_positive_int,
        metavar="N",
        help="levels to expand, counted from the top or from each --section",
    )

    tables = parser.add_argument_group("tables")
    targets = tables.add_mutually_exclusive_group()
    targets.add_argument(
        "--table",
        action="append",
        metavar="ID",
        help="show a table (e.g. T3): schema and first rows; repeatable",
    )
    targets.add_argument(
        "--tables",
        action="store_true",
        help="list every table (in --section scope); with --full/--rows/--cols, show each",
    )
    targets.add_argument(
        "--diagram",
        action="append",
        metavar="ID",
        help="print a diagram's source (e.g. D1); repeatable",
    )
    targets.add_argument(
        "--diagrams",
        action="store_true",
        help="list every diagram (in --section scope); with --full, show each",
    )
    targets.add_argument(
        "--sql",
        metavar="QUERY",
        help="run SQL over the tables (in --section scope), loaded as t1, t2, ...",
    )
    tables.add_argument(
        "--engine",
        choices=[e.value for e in Engine],
        default=None,
        help="SQL engine (default auto: duckdb if installed, else sqlite; or set MDPEEK_ENGINE)",
    )
    tables.add_argument("--rows", metavar="RANGE", help="rows to show: N, A-B, A- or -B (1-based)")
    tables.add_argument("--cols", type=_column_list, metavar="A,B", help="columns to show, by name")
    tables.add_argument(
        "--limit", type=_positive_int, metavar="N", help="maximum rows to show (default 50)"
    )
    tables.add_argument(
        "--format",
        choices=[f.value for f in Format],
        default=None,
        help="output format for table data (default md)",
    )
    tables.add_argument(
        "--table-summaries",
        action=argparse.BooleanOptionalAction,
        default=defaults.summaries,
        help="replace large tables with a one-line summary in document output",
    )
    tables.add_argument(
        "--table-max-cols",
        type=_positive_int,
        default=defaults.max_cols,
        metavar="N",
        help=f"summarise tables wider than N columns (default {defaults.max_cols})",
    )
    tables.add_argument(
        "--table-max-rows",
        type=_positive_int,
        default=defaults.max_rows,
        metavar="N",
        help=f"summarise tables longer than N rows (default {defaults.max_rows})",
    )
    tables.add_argument(
        "--table-header-max-chars",
        type=_positive_int,
        default=defaults.header_max_chars,
        metavar="N",
        help="list column names in a summary only if they fit in N characters "
        f"(default {defaults.header_max_chars})",
    )
    tables.add_argument(
        "--diagram-summaries",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="replace diagrams with a one-line summary in document output",
    )
    tables.add_argument(
        "--raw-column-names",
        action="store_true",
        help="show original table headers instead of their SQL column names",
    )
    tables.add_argument(
        "--on-table-error",
        choices=[p.value for p in OnTableError],
        default=OnTableError.SHOW.value,
        help="how to show a table that could not be parsed (default show)",
    )

    urls = parser.add_argument_group("URL sources")
    urls.add_argument(
        "-H",
        "--header",
        action="append",
        metavar="'NAME: VALUE'",
        help="request header for a URL source; repeatable (never written to the cache)",
    )
    urls.add_argument(
        "--ttl",
        type=_non_negative_float,
        metavar="SECONDS",
        help=f"reuse a cached copy younger than this (default {DEFAULT_TTL})",
    )
    urls.add_argument(
        "--refresh", action="store_true", help="fetch again, ignoring any cached copy"
    )
    urls.add_argument("--no-cache", action="store_true", help="neither read nor write the cache")
    urls.add_argument(
        "--timeout",
        type=_non_negative_float,
        metavar="SECONDS",
        help=f"network timeout (default {DEFAULT_TIMEOUT:g})",
    )
    return parser


def _non_negative_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        number = -1.0
    if number < 0:
        raise argparse.ArgumentTypeError(f"must be a number of seconds, got {value!r}")
    return number


_URL_FLAGS = {"header": "--header", "ttl": "--ttl", "timeout": "--timeout"}
_URL_SWITCHES = {"refresh": "--refresh", "no_cache": "--no-cache"}


def _load(args: argparse.Namespace) -> tuple[str, SourceInfo]:
    """Read the source; URL options are only allowed with a URL."""
    if not is_url(args.source):
        used = [flag for name, flag in _URL_FLAGS.items() if getattr(args, name) is not None]
        used += [flag for name, flag in _URL_SWITCHES.items() if getattr(args, name)]
        if used:
            raise UsageError(f"{_flags(used)} only {_verb(used)} to URL sources")
    headers = dict(parse_header(h) for h in args.header or [])
    return load(
        args.source,
        headers=headers,
        cache=None if args.no_cache else CacheBackend.DISK,
        ttl=DEFAULT_TTL if args.ttl is None else args.ttl,
        refresh=args.refresh,
        timeout=DEFAULT_TIMEOUT if args.timeout is None else args.timeout,
    )


def _check_combinations(args: argparse.Namespace) -> None:
    if args.engine is not None and args.sql is None:
        raise UsageError("--engine only applies with --sql")
    diagram_mode = bool(args.diagram or args.diagrams)
    data_mode = bool(args.table or args.tables or args.sql is not None)
    slicing = [f"--{f}" for f in ("rows", "cols", "limit") if getattr(args, f) is not None]
    if args.sql is not None:
        used = [flag for flag in slicing if flag != "--limit"]
        if used:
            raise UsageError(f"{', '.join(used)} cannot be combined with --sql")
    if slicing and not data_mode:
        raise UsageError(f"{_flags(slicing)} only {_verb(slicing)} with --table, --tables or --sql")
    targets = "--table, --tables, --sql, --diagram or --diagrams"
    if not (data_mode or diagram_mode):
        if args.format is not None:
            raise UsageError(f"--format only applies with {targets}")
        return
    if args.mode is Mode.STRUCTURE:
        raise UsageError(f"--structure cannot be combined with {targets}")
    if args.depth is not None:
        raise UsageError(f"--depth cannot be combined with {targets}")
    if (args.table or args.diagram) and args.section:
        raise UsageError(
            "--section cannot be combined with --table or --diagram (their IDs are global)"
        )
    if diagram_mode and args.format in (Format.CSV.value, Format.TSV.value):
        raise UsageError(
            f"--format {args.format} does not apply to diagrams; use md, json or jsonl"
        )


def _show_diagrams(doc: Document, args: argparse.Namespace) -> str:
    fmt = Format(args.format or Format.MD)
    if args.diagram:
        return render_diagrams([doc.diagram(d) for d in args.diagram], fmt)
    found = doc.diagrams_in(args.section)
    if args.mode is Mode.FULL:
        return render_diagrams(found, fmt)
    return render_diagram_list(found, fmt)


def _show_tables(doc: Document, args: argparse.Namespace, settings: TableSettings) -> str:
    fmt = Format(args.format or Format.MD)
    full = args.mode is Mode.FULL
    wants_data = bool(args.table) or full or args.rows is not None or args.cols is not None
    tables = [doc.table(t) for t in args.table] if args.table else doc.tables_in(args.section)
    if not wants_data:
        return render_table_list(tables, settings, fmt)

    selections = [
        select(t, rows=args.rows, cols=args.cols, limit=args.limit, full=full) for t in tables
    ]
    for selection in selections:
        note = truncation_note(selection)
        if note:
            print(note, file=sys.stderr)
    raw = settings.raw_column_names
    if fmt is Format.JSON and len(selections) > 1:
        blocks = [render_table(s, fmt, raw_column_names=raw).rstrip("\n") for s in selections]
        return "[" + ",".join(blocks) + "]\n"
    separator = "" if fmt is Format.JSONL else "\n"
    return separator.join(render_table(s, fmt, raw_column_names=raw) for s in selections)


def _run_sql(doc: Document, args: argparse.Namespace) -> str:
    tables = doc.tables_in(args.section)
    for table in tables:
        if not table.ok:
            print(f"mdpeek: skipped {table.id} (not parsed: {table.error})", file=sys.stderr)
    result: QueryResult = run_query(tables, args.sql, args.engine or Engine.AUTO)
    for note in result.notes:
        print(f"mdpeek: {note}", file=sys.stderr)
    fmt = Format(args.format or Format.MD)
    limit = result.total if args.mode is Mode.FULL else (args.limit or DEFAULT_LIMIT)
    rows = result.rows[:limit]
    if len(rows) < result.total:
        print(
            f"mdpeek: query: showing {len(rows)} of {result.total} rows (use --limit or --full)",
            file=sys.stderr,
        )
    if fmt is Format.JSON:
        return to_json(
            {
                "engine": result.engine.value,
                "columns": result.columns,
                "rows": rows,
                "total": result.total,
                "shown": len(rows),
            }
        )
    return format_rows(result.columns, rows, fmt)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        text, info = _load(args)
    except (UsageError, ValueError) as exc:
        print(f"mdpeek: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as exc:
        print(f"mdpeek: cannot read {args.source!r}: {exc.strerror or exc}", file=sys.stderr)
        return EXIT_USAGE
    except FetchError as exc:
        print(f"mdpeek: cannot fetch {args.source!r}: {exc}", file=sys.stderr)
        return EXIT_USAGE

    settings = TableSettings(
        summaries=args.table_summaries,
        max_cols=args.table_max_cols,
        max_rows=args.table_max_rows,
        header_max_chars=args.table_header_max_chars,
        on_error=args.on_table_error,
        raw_column_names=args.raw_column_names,
    )
    doc = Document.from_text(text)
    doc.source = info
    try:
        _check_combinations(args)
        if args.sql is not None:
            output = _run_sql(doc, args)
        elif args.table or args.tables:
            output = _show_tables(doc, args, settings)
        elif args.diagram or args.diagrams:
            output = _show_diagrams(doc, args)
        else:
            output = render(
                doc, args.mode, args.depth, args.section, settings, args.diagram_summaries
            )
    except (
        UsageError,
        SectionNotFound,
        TableNotFound,
        DiagramNotFound,
        SelectionError,
        QueryError,
        EngineUnavailable,
        ValueError,
    ) as exc:
        print(f"mdpeek: {exc}", file=sys.stderr)
        return EXIT_USAGE

    cached = info.cached_line()
    if cached and args.format in _MACHINE_FORMATS:
        print(f"mdpeek: {cached}", file=sys.stderr)  # keep data output parseable
    elif cached:
        output = f"{cached}\n{output}"
    sys.stdout.write(output)
    return 0
