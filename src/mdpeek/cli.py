"""Command-line interface for mdpeek."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from mdpeek import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdpeek",
        description="Progressively expose a markdown document by section.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("source", nargs="?", help="Markdown file path, URL, or '-' for stdin")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.source is None:
        parser.print_usage(sys.stderr)
        return 2
    print("mdpeek: document views are not implemented yet", file=sys.stderr)
    return 2
