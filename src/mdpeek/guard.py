"""Limits on what a source may reach: a confining directory and a URL policy.

The CLI trusts its user. These guards are for callers that pass on input from
someone else, such as a model calling an MCP tool.

>>> import tempfile, pathlib
>>> root = pathlib.Path(tempfile.mkdtemp())
>>> _ = (root / "a.md").write_text("# A\\n")
>>> confine(root, "a.md").name
'a.md'
>>> confine(root, "../etc/passwd")
Traceback (most recent call last):
...
mdpeek.guard.OutsideRoot: '../etc/passwd' is outside the docs directory; give a path inside it
>>> policy = UrlPolicy(["docs.example.com", "https://example.org/pub/"], allow_private=True)
>>> policy.check("https://docs.example.com/a.md")
>>> policy.check("https://example.org/private/a.md")
Traceback (most recent call last):
...
mdpeek.guard.UrlNotAllowed: URL not allowed: https://example.org/private/a.md
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


class OutsideRoot(ValueError):
    """A path leads outside the confining directory."""


class UrlNotAllowed(ValueError):
    """A URL (or a redirect) is not allowed by the policy."""


def confine(root: str | os.PathLike[str], rel: str | None) -> Path:
    """The real path of ``rel`` inside ``root``, symlinks resolved.

    ``None`` or ``""`` means ``root`` itself. Raises :class:`OutsideRoot` for an
    absolute path or one that resolves outside ``root``, and
    ``FileNotFoundError`` when it does not exist.
    """
    base = Path(root).resolve(strict=True)
    if not rel or rel in (".", "./"):
        return base
    if os.path.isabs(rel) or rel.startswith("~"):
        raise OutsideRoot(_outside(rel))
    target = (base / rel).resolve()
    if not inside(base, target):
        raise OutsideRoot(_outside(rel))
    if not target.exists():
        raise FileNotFoundError(f"no file or directory {rel!r} in the docs directory")
    return target


def inside(base: Path, target: Path) -> bool:
    """Whether ``target`` is ``base`` or below it (both already resolved)."""
    return target == base or base in target.parents


def _outside(rel: str) -> str:
    return f"{rel!r} is outside the docs directory; give a path inside it"


Resolver = Callable[[str], Iterable[str]]


def _resolve_host(host: str) -> list[str]:
    return [str(info[4][0]) for info in socket.getaddrinfo(host, None)]


@dataclass
class UrlPolicy:
    """Which URLs may be fetched.

    Each ``allow`` entry is a URL prefix (``https://docs.example.com/guides/``),
    a host (``docs.example.com``) or a host wildcard (``*.example.com``). Hosts
    that resolve to loopback, private, link-local or reserved addresses are
    refused unless ``allow_private``.
    """

    allow: Iterable[str] = ()
    allow_private: bool = False
    resolver: Resolver = field(default=_resolve_host, repr=False)

    def __post_init__(self) -> None:
        self.allow = tuple(self.allow)

    def check(self, url: str) -> None:
        """Raise :class:`UrlNotAllowed` unless ``url`` may be fetched."""
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or not host:
            raise UrlNotAllowed(f"URL not allowed: {url}")
        if not any(_matches(entry, url, host) for entry in self.allow):
            raise UrlNotAllowed(f"URL not allowed: {url}")
        if not self.allow_private:
            self._check_address(url, host)

    def _check_address(self, url: str, host: str) -> None:
        try:
            addresses = list(self.resolver(host))
        except OSError as exc:
            raise UrlNotAllowed(f"cannot resolve {host!r}: {exc}") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address.split("%")[0])
            if not ip.is_global or ip.is_multicast:
                raise UrlNotAllowed(f"URL not allowed: {url} (resolves to a non-public address)")


def _matches(entry: str, url: str, host: str) -> bool:
    if "://" in entry:
        allowed = urlsplit(entry)
        wanted = urlsplit(url)
        return (
            wanted.scheme == allowed.scheme
            and (wanted.hostname or "").lower() == (allowed.hostname or "").lower()
            and wanted.port == allowed.port
            and wanted.path.startswith(allowed.path or "/")
        )
    entry = entry.lower()
    if entry.startswith("*."):
        return host.endswith(entry[1:])
    return host == entry
