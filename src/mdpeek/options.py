"""Enumerated options for the mdpeek API and CLI.

Every option with a fixed set of values is a ``StrEnum``. API functions accept
either the enum member or its string value (case-insensitive) and normalise
with :func:`coerce`.

>>> coerce(Mode, "structure")
<Mode.STRUCTURE: 'structure'>
>>> coerce(Mode, Mode.FULL)
<Mode.FULL: 'full'>
"""

from __future__ import annotations

import sys
from enum import Enum
from typing import TypeVar

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:  # pragma: no cover - Python 3.10

    class StrEnum(str, Enum):
        """Backport of :class:`enum.StrEnum`: members are strings and print as their value."""

        def __str__(self) -> str:
            return str(self.value)

        def __format__(self, format_spec: str) -> str:
            return str(self.value).__format__(format_spec)


class Mode(StrEnum):
    """How much of each section to show."""

    VIEW = "view"
    STRUCTURE = "structure"
    FULL = "full"


class OnTableError(StrEnum):
    """What to do with a table that cannot be parsed."""

    SHOW = "show"
    SUMMARY = "summary"
    EXCLUDE = "exclude"


class Format(StrEnum):
    """Output format for table and query results."""

    MD = "md"
    CSV = "csv"
    TSV = "tsv"
    JSON = "json"
    JSONL = "jsonl"


class Engine(StrEnum):
    """SQL engine used for table queries."""

    AUTO = "auto"
    SQLITE = "sqlite"
    DUCKDB = "duckdb"


class CacheBackend(StrEnum):
    """Where fetched URL content is cached."""

    MEMORY = "memory"
    DISK = "disk"


E = TypeVar("E", bound=StrEnum)


def coerce(enum_cls: type[E], value: E | str) -> E:
    """Return ``value`` as a member of ``enum_cls``.

    Accepts a member or its string value, case-insensitively. Raises
    ``ValueError`` listing the valid choices otherwise.

    >>> coerce(Format, "JSON")
    <Format.JSON: 'json'>
    >>> coerce(Format, "xml")
    Traceback (most recent call last):
    ...
    ValueError: invalid Format 'xml'; expected one of: md, csv, tsv, json, jsonl
    """
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        try:
            return enum_cls(value.lower())
        except ValueError:
            pass
    choices = ", ".join(member.value for member in enum_cls)
    raise ValueError(f"invalid {enum_cls.__name__} {value!r}; expected one of: {choices}")
