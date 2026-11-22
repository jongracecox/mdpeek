"""Confinement to a directory and the URL policy."""

import os

import pytest

from mdpeek import Library
from mdpeek.guard import OutsideRoot, UrlNotAllowed, UrlPolicy, confine
from mdpeek.source import fetch, load


@pytest.fixture
def docs(tmp_path):
    root = tmp_path / "docs"
    (root / "guides").mkdir(parents=True)
    (root / "guides" / "install.md").write_text("# Install\n")
    (tmp_path / "secret.md").write_text("# Secret\n")
    return root


def test_confine_accepts_paths_inside(docs):
    assert confine(docs, "guides/install.md") == (docs / "guides" / "install.md").resolve()
    assert confine(docs, None) == docs.resolve()
    assert confine(docs, "guides/../guides") == (docs / "guides").resolve()


@pytest.mark.parametrize("rel", ["../secret.md", "guides/../../secret.md", "/etc/passwd", "~/x"])
def test_confine_refuses_paths_outside(docs, rel):
    with pytest.raises(OutsideRoot, match="outside the docs directory"):
        confine(docs, rel)


def test_confine_refuses_a_symlink_out(docs):
    os.symlink(docs.parent / "secret.md", docs / "link.md")
    with pytest.raises(OutsideRoot):
        confine(docs, "link.md")


def test_confine_allows_a_symlink_that_stays_inside(docs):
    os.symlink(docs / "guides" / "install.md", docs / "alias.md")
    assert confine(docs, "alias.md").name == "install.md"


def test_confine_reports_a_missing_path(docs):
    with pytest.raises(FileNotFoundError, match=r"no file or directory 'nope\.md'"):
        confine(docs, "nope.md")


def test_library_confine_skips_links_out(docs):
    os.symlink(docs.parent / "secret.md", docs / "link.md")
    assert "link.md" in Library.from_path(docs).tree()
    library = Library.from_path(docs, confine=True)
    assert "link.md" not in library.tree()
    assert any("links outside the directory" in s for s in library.skipped)


def _public(_host):
    return ["93.184.216.34"]


@pytest.mark.parametrize(
    ("entry", "url", "allowed"),
    [
        ("docs.example.com", "https://docs.example.com/a.md", True),
        ("docs.example.com", "http://docs.example.com/a.md", True),
        ("docs.example.com", "https://evil.example.com/a.md", False),
        ("*.example.com", "https://a.b.example.com/x", True),
        ("*.example.com", "https://example.com.evil.net/x", False),
        ("https://example.org/pub/", "https://example.org/pub/a.md", True),
        ("https://example.org/pub/", "https://example.org/private/a.md", False),
        ("https://example.org/pub/", "http://example.org/pub/a.md", False),
    ],
)
def test_url_policy_matching(entry, url, allowed):
    policy = UrlPolicy([entry], resolver=_public)
    if allowed:
        policy.check(url)
    else:
        with pytest.raises(UrlNotAllowed):
            policy.check(url)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1"])
def test_url_policy_refuses_non_public_addresses(address):
    policy = UrlPolicy(["internal.example.com"], resolver=lambda _h: [address])
    with pytest.raises(UrlNotAllowed, match="non-public address"):
        policy.check("https://internal.example.com/a.md")
    UrlPolicy(["internal.example.com"], allow_private=True, resolver=lambda _h: [address]).check(
        "https://internal.example.com/a.md"
    )


def test_url_policy_refuses_other_schemes():
    with pytest.raises(UrlNotAllowed):
        UrlPolicy(["example.com"], resolver=_public).check("file:///etc/passwd")


def test_fetch_checks_every_redirect(http_server):
    http_server.serve("/ok.md", "# OK\n")
    http_server.redirects["/hop"] = f"{http_server.url}/ok.md"
    allowed = UrlPolicy([f"{http_server.url}/hop"], allow_private=True)
    with pytest.raises(UrlNotAllowed, match=r"ok\.md"):
        fetch(f"{http_server.url}/hop", check=allowed.check)
    both = UrlPolicy([f"{http_server.url}/hop", f"{http_server.url}/ok.md"], allow_private=True)
    assert fetch(f"{http_server.url}/hop", check=both.check) == "# OK\n"


def test_load_checks_before_using_the_cache(http_server):
    http_server.serve("/a.md", "# A\n")
    url = f"{http_server.url}/a.md"
    load(url)  # now cached
    with pytest.raises(UrlNotAllowed):
        load(url, check=UrlPolicy([], allow_private=True).check)
