import io
from datetime import UTC, datetime

import pytest

from mdpeek import Document, __version__
from mdpeek import cache as cache_module
from mdpeek import source as source_module
from mdpeek.cache import MemoryCache
from mdpeek.source import FetchError, fetch, is_url, load, parse_header


def test_is_url():
    assert is_url("https://x/a.md")
    assert is_url("HTTP://x/a.md")
    assert not is_url("docs/a.md")
    assert not is_url("ftp://x/a.md")


@pytest.mark.parametrize("bad", ["no colon", ": value", ""])
def test_parse_header_rejects_bad_values(bad):
    with pytest.raises(ValueError, match="expected 'Name: value'"):
        parse_header(bad)


def test_parse_header_keeps_colons_in_value():
    assert parse_header("X-Time: 09:30") == ("X-Time", "09:30")


def test_fetch_sends_user_agent_and_headers(http_server):
    http_server.serve("/a.md", "# A\n")
    assert fetch(f"{http_server.url}/a.md", {"Authorization": "Bearer t"}) == "# A\n"
    headers = http_server.requests[0]["headers"]
    assert headers["User-Agent"] == f"mdpeek/{__version__}"
    assert headers["Authorization"] == "Bearer t"


def test_fetch_uses_response_charset(http_server):
    http_server.serve("/l.md", "# Café\n", content_type="text/markdown; charset=latin-1")
    assert fetch(f"{http_server.url}/l.md") == "# Café\n"


def test_fetch_errors(http_server):
    with pytest.raises(FetchError, match="HTTP 404"):
        fetch(f"{http_server.url}/missing.md")
    port = http_server.server_address[1]
    http_server.shutdown()
    http_server.server_close()
    with pytest.raises(FetchError):
        fetch(f"http://127.0.0.1:{port}/a.md", timeout=2)


def test_fetch_size_limit(http_server, monkeypatch):
    monkeypatch.setattr(source_module, "MAX_BYTES", 4)
    http_server.serve("/big.md", "# much too long\n")
    with pytest.raises(FetchError, match="larger than"):
        fetch(f"{http_server.url}/big.md")


def test_load_path_and_stdin(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("# A\n")
    assert load(str(path))[1].kind == "path"
    text, info = load("-", stdin=io.StringIO("# B\n"))
    assert (text, info.kind) == ("# B\n", "stdin")


def test_load_caches_until_ttl(http_server, monkeypatch):
    clock = [datetime(2026, 11, 20, 9, 0, tzinfo=UTC)]
    monkeypatch.setattr(cache_module, "now", lambda: clock[0])
    http_server.serve("/a.md", "# One\n")
    url, cache = f"{http_server.url}/a.md", MemoryCache()

    text, info = load(url, cache=cache)
    assert (text, info.from_cache, info.cached_line()) == ("# One\n", False, None)

    http_server.serve("/a.md", "# Two\n")
    clock[0] = datetime(2026, 11, 20, 9, 30, tzinfo=UTC)
    text, info = load(url, cache=cache)
    assert (text, info.cached_line()) == ("# One\n", "(cached 2026-11-20 09:00Z)")

    assert load(url, cache=cache, refresh=True)[0] == "# Two\n"
    clock[0] = datetime(2026, 11, 20, 11, 0, tzinfo=UTC)
    assert load(url, cache=cache, ttl=60)[1].from_cache is False
    assert len(http_server.requests) == 3


def test_load_without_cache_always_fetches(http_server):
    http_server.serve("/a.md", "# A\n")
    url = f"{http_server.url}/a.md"
    load(url, cache=None)
    load(url, cache=None)
    assert len(http_server.requests) == 2


def test_document_from_url_uses_the_process_memory_cache(http_server):
    http_server.serve("/a.md", "# A\nbody\n")
    url = f"{http_server.url}/a.md"
    first = Document.from_url(url)
    second = Document.from_url(url)
    assert first.view() == "[S1] A\nbody\n"
    assert (first.source.from_cache, second.source.from_cache) == (False, True)
    assert len(http_server.requests) == 1


def test_document_from_url_rejects_paths():
    with pytest.raises(ValueError, match="not an http"):
        Document.from_url("docs/a.md")
