"""Command-line interface for mdpeek."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from mdpeek import __version__
from mdpeek.model import Document, SectionNotFound
from mdpeek.options import Mode
from mdpeek.render import render

EXIT_USAGE = 2


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be a whole number of at least 1, got {value!r}")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdpeek",
        description="Progressively expose a markdown document by section.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("source", help="markdown file path, or '-' for stdin")
    parser.add_argument(
        "-s",
        "--section",
        action="append",
        metavar="ID",
        help="show only this section (e.g. S2.1); repeatable",
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
        help="all content (down to --depth, if given)",
    )
    parser.set_defaults(mode=Mode.VIEW)
    parser.add_argument(
        "-d",
        "--depth",
        type=_positive_int,
        metavar="N",
        help="levels to expand, counted from the top or from each --section",
    )
    return parser


def _read_source(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    with open(source, encoding="utf-8", newline="") as handle:
        return handle.read()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        text = _read_source(args.source)
    except (OSError, UnicodeDecodeError) as exc:
        reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
        print(f"mdpeek: cannot read {args.source!r}: {reason}", file=sys.stderr)
        return EXIT_USAGE

    doc = Document.from_text(text)
    try:
        output = render(doc, args.mode, args.depth, args.section)
    except SectionNotFound as exc:
        print(f"mdpeek: {exc}", file=sys.stderr)
        return EXIT_USAGE
    sys.stdout.write(output)
    return 0
