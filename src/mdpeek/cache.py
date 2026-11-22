"""Caches for fetched URL content.

Entries are keyed by a SHA-256 of the URL and the sorted request headers, so
the same URL fetched with different headers is cached separately. Header
values are never stored: only their hash is part of the key.

- :class:`MemoryCache` lives for the process (the API default).
- :class:`DiskCache` keeps entries under ``$MDPEEK_CACHE_DIR``, or
  ``$XDG_CACHE_HOME/mdpeek``, or ``~/.cache/mdpeek`` (the CLI default), so
  separate CLI runs share them.

Expiry is the caller's choice: :meth:`CacheEntry.fresh` takes a TTL.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from mdpeek.options import CacheBackend, coerce

DEFAULT_TTL = 3600
"""Seconds a cached entry stays fresh."""


def now() -> datetime:
    """The current UTC time (a seam for tests)."""
    return datetime.now(timezone.utc)


def cache_key(url: str, headers: Mapping[str, str] | None = None) -> str:
    """SHA-256 of the URL and headers (names case-insensitive, sorted).

    >>> cache_key("https://x/a.md", {"B": "2", "a": "1"}) == cache_key(
    ...     "https://x/a.md", {"A": "1", "b": "2"})
    True
    """
    parts = [url]
    for name, value in sorted((k.lower(), v) for k, v in (headers or {}).items()):
        parts.append(f"{name}:{value}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CacheEntry:
    """A fetched document and when it was fetched."""

    url: str
    text: str
    fetched_at: datetime

    def fresh(self, ttl: float, at: datetime | None = None) -> bool:
        """Whether the entry is younger than ``ttl`` seconds."""
        return (at or now()) - self.fetched_at < timedelta(seconds=ttl)


class Cache(Protocol):
    """Somewhere to keep fetched documents."""

    def get(self, key: str) -> CacheEntry | None: ...

    def set(self, key: str, entry: CacheEntry) -> None: ...


class MemoryCache:
    """A per-process cache."""

    def __init__(self) -> None:
        self._entries: dict[str, CacheEntry] = {}

    def get(self, key: str) -> CacheEntry | None:
        return self._entries.get(key)

    def set(self, key: str, entry: CacheEntry) -> None:
        self._entries[key] = entry

    def clear(self) -> None:
        self._entries.clear()


def default_cache_dir(env: Mapping[str, str] | None = None) -> Path:
    """``$MDPEEK_CACHE_DIR``, else ``$XDG_CACHE_HOME/mdpeek``, else ``~/.cache/mdpeek``."""
    env = os.environ if env is None else env
    if env.get("MDPEEK_CACHE_DIR"):
        return Path(env["MDPEEK_CACHE_DIR"]).expanduser()
    base = env.get("XDG_CACHE_HOME") or "~/.cache"
    return Path(base).expanduser() / "mdpeek"


class DiskCache:
    """A cache shared between runs: one JSON file per entry, readable only by you."""

    def __init__(self, directory: str | os.PathLike[str] | None = None) -> None:
        self.directory = Path(directory) if directory is not None else default_cache_dir()

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> CacheEntry | None:
        try:
            data = json.loads(self._path(key).read_text(encoding="utf-8"))
            return CacheEntry(
                url=data["url"],
                text=data["text"],
                fetched_at=datetime.fromisoformat(data["fetched_at"]),
            )
        except (OSError, ValueError, KeyError, TypeError):
            return None  # missing or unreadable entries are just cache misses

    def set(self, key: str, entry: CacheEntry) -> None:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        payload = {"url": entry.url, "fetched_at": entry.fetched_at.isoformat(), "text": entry.text}
        # Write then rename, so a concurrent reader never sees half a file.
        fd, tmp = tempfile.mkstemp(dir=self.directory, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._path(key))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


_PROCESS_CACHE = MemoryCache()


def make_cache(backend: CacheBackend | str | Cache | None) -> Cache | None:
    """Turn a backend name (or a ready cache, or ``None`` for no cache) into a cache."""
    if backend is None:
        return None
    if isinstance(backend, (str, CacheBackend)):
        kind = coerce(CacheBackend, backend)
        return _PROCESS_CACHE if kind is CacheBackend.MEMORY else DiskCache()
    return backend


def format_fetched_at(moment: datetime) -> str:
    """Compact UTC timestamp: ``2026-11-20 15:04Z``."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
