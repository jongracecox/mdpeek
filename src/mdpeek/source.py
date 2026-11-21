"""Load markdown from a file path, a URL or stdin.

URLs are fetched with the standard library and cached (see
:mod:`mdpeek.cache`). Requests identify themselves only as
``mdpeek/<version>``; extra headers (e.g. ``Authorization``) are sent as
given and never written to the cache.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TextIO

from mdpeek import cache as _cache
from mdpeek.cache import (
    DEFAULT_TTL,  # re-exported for callers of load()
    Cache,
    CacheBackend,
    CacheEntry,
    cache_key,
    format_fetched_at,
    make_cache,
)

DEFAULT_TIMEOUT = 30.0
MAX_BYTES = 50 * 1024 * 1024


class FetchError(Exception):
    """A URL could not be fetched."""


@dataclass(frozen=True)
class SourceInfo:
    """Where a document came from."""

    source: str
    kind: Literal["path", "url", "stdin", "text"]
    from_cache: bool = False
    fetched_at: datetime | None = None

    def cached_line(self) -> str | None:
        """``(cached 2026-11-20 15:04Z)`` when the text came from the cache."""
        if not self.from_cache or self.fetched_at is None:
            return None
        return f"(cached {format_fetched_at(self.fetched_at)})"


def is_url(source: str) -> bool:
    return source.lower().startswith(("http://", "https://"))


def parse_header(value: str) -> tuple[str, str]:
    """Split ``"Name: value"``.

    >>> parse_header("Accept: text/markdown")
    ('Accept', 'text/markdown')
    """
    name, sep, rest = value.partition(":")
    if not sep or not name.strip():
        raise ValueError(f"invalid header {value!r}; expected 'Name: value'")
    return name.strip(), rest.strip()


def read_path(path: str) -> str:
    """Read a file as UTF-8 (invalid bytes replaced), keeping line endings."""
    with open(path, encoding="utf-8", errors="replace", newline="") as handle:
        return handle.read()


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    """Runs ``check`` on every redirect target before following it."""

    def __init__(self, check: Callable[[str], None]) -> None:
        self.check = check

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.check(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(
    url: str,
    headers: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    check: Callable[[str], None] | None = None,
) -> str:
    """GET ``url`` and decode it (charset from the response, else UTF-8).

    ``check`` is called with the URL and with every redirect target, and may
    raise to refuse it (see :class:`mdpeek.guard.UrlPolicy`).
    """
    from mdpeek import __version__

    if check is not None:
        check(url)
    request = urllib.request.Request(url, headers={"User-Agent": f"mdpeek/{__version__}"})
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    opener = (
        urllib.request.build_opener(_CheckedRedirects(check))
        if check is not None
        else urllib.request.build_opener()
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(MAX_BYTES + 1)
            charset = response.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code} {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise FetchError(str(exc.reason)) from exc
    except TimeoutError as exc:
        raise FetchError(f"timed out after {timeout:g}s") from exc
    if len(body) > MAX_BYTES:
        raise FetchError(f"response is larger than {MAX_BYTES // (1024 * 1024)} MB")
    return body.decode(charset, errors="replace")


def load(
    source: str,
    *,
    headers: Mapping[str, str] | None = None,
    cache: CacheBackend | str | Cache | None = CacheBackend.MEMORY,
    ttl: float = DEFAULT_TTL,
    refresh: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
    stdin: TextIO | None = None,
    check: Callable[[str], None] | None = None,
) -> tuple[str, SourceInfo]:
    """Return the markdown text for ``source`` and where it came from.

    ``source`` is a path, an ``http(s)://`` URL, or ``-`` for stdin. For URLs,
    a fresh cache entry (younger than ``ttl`` seconds) is used unless
    ``refresh``; ``cache=None`` turns caching off. ``check`` vets the URL and
    each redirect before fetching; a cached entry is only used if the URL passes.
    """
    if source == "-":
        return (stdin or sys.stdin).read(), SourceInfo(source, "stdin")
    if not is_url(source):
        return read_path(source), SourceInfo(source, "path")

    if check is not None:
        check(source)
    store = make_cache(cache)
    key = cache_key(source, headers)
    if store is not None and not refresh:
        entry = store.get(key)
        if entry is not None and entry.fresh(ttl):
            return entry.text, SourceInfo(source, "url", True, entry.fetched_at)
    text = fetch(source, headers, timeout, check)
    fetched_at = _cache.now()
    if store is not None:
        store.set(key, CacheEntry(source, text, fetched_at))
    return text, SourceInfo(source, "url", False, fetched_at)
