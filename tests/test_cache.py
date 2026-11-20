import json
import os
import stat
from datetime import UTC, datetime, timedelta

import pytest

from mdpeek.cache import (
    CacheEntry,
    DiskCache,
    MemoryCache,
    cache_key,
    default_cache_dir,
    format_fetched_at,
    make_cache,
)
from mdpeek.options import CacheBackend

T0 = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)


def entry(text: str = "# A\n", at: datetime = T0) -> CacheEntry:
    return CacheEntry("https://example.test/a.md", text, at)


def test_key_depends_on_url_and_headers():
    base = cache_key("https://x/a.md")
    assert base == cache_key("https://x/a.md", {})
    assert base != cache_key("https://x/b.md")
    assert base != cache_key("https://x/a.md", {"Authorization": "Bearer 1"})
    assert cache_key("https://x/a.md", {"Authorization": "Bearer 1"}) != cache_key(
        "https://x/a.md", {"Authorization": "Bearer 2"}
    )


def test_freshness():
    assert entry().fresh(3600, at=T0 + timedelta(minutes=59))
    assert not entry().fresh(3600, at=T0 + timedelta(minutes=60))
    assert not entry().fresh(0, at=T0)


def test_memory_cache():
    cache = MemoryCache()
    assert cache.get("k") is None
    cache.set("k", entry())
    assert cache.get("k") == entry()
    cache.clear()
    assert cache.get("k") is None


def test_disk_cache_round_trip_and_permissions(tmp_path):
    cache = DiskCache(tmp_path / "cache")
    cache.set("k", entry("# Café\n"))
    assert cache.get("k") == entry("# Café\n")
    directory, file = tmp_path / "cache", tmp_path / "cache" / "k.json"
    assert stat.S_IMODE(os.stat(directory).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(file).st_mode) == 0o600
    assert list(directory.iterdir()) == [file]  # no temp files left behind


def test_disk_cache_does_not_store_headers(tmp_path):
    cache = DiskCache(tmp_path)
    cache.set(cache_key("https://x/a.md", {"Authorization": "Bearer secret"}), entry())
    for path in tmp_path.iterdir():
        content = path.read_text()
        assert "secret" not in content
        assert set(json.loads(content)) == {"url", "fetched_at", "text"}


@pytest.mark.parametrize(
    "content", ["not json", "{}", '{"url": 1}', '{"url":"u","text":"t","fetched_at":"nope"}']
)
def test_unreadable_disk_entries_are_misses(tmp_path, content):
    (tmp_path / "k.json").write_text(content)
    assert DiskCache(tmp_path).get("k") is None


def test_default_cache_dir(tmp_path):
    assert default_cache_dir({"MDPEEK_CACHE_DIR": str(tmp_path)}) == tmp_path
    assert default_cache_dir({"XDG_CACHE_HOME": str(tmp_path)}) == tmp_path / "mdpeek"
    assert default_cache_dir({}).parts[-2:] == (".cache", "mdpeek")


def test_make_cache(isolated_cache):
    assert make_cache(None) is None
    assert isinstance(make_cache("memory"), MemoryCache)
    assert make_cache(CacheBackend.MEMORY) is make_cache("MEMORY")  # one per process
    disk = make_cache("disk")
    assert isinstance(disk, DiskCache)
    assert disk.directory == isolated_cache
    custom = MemoryCache()
    assert make_cache(custom) is custom
    with pytest.raises(ValueError):
        make_cache("redis")


def test_format_fetched_at():
    assert format_fetched_at(T0) == "2026-11-20 09:00Z"
