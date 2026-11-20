"""mdpeek: progressive exposure for markdown documents.

>>> doc = Document.from_text("# Guide\\nHello.\\n## Install\\nRun it.\\n")
>>> print(doc.view(), end="")
[S1] Guide
Hello.
  [S1.1] Install (1 line)
"""

from importlib.metadata import PackageNotFoundError, version

from mdpeek.model import Document, Section, SectionNotFound
from mdpeek.options import CacheBackend, Engine, Format, Mode, OnTableError
from mdpeek.parse import parse
from mdpeek.render import render

try:
    __version__ = version("mdpeek")
except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
    __version__ = "0.0.0"

__all__ = [
    "CacheBackend",
    "Document",
    "Engine",
    "Format",
    "Mode",
    "OnTableError",
    "Section",
    "SectionNotFound",
    "__version__",
    "parse",
    "render",
]
