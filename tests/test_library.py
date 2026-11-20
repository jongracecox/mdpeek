import os
import sys
from pathlib import Path

import pytest

from mdpeek.cli import main
from mdpeek.library import Library, glob_match


def write(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_a_file_is_not_a_library(tmp_path: Path) -> None:
    write(tmp_path, "a.md", "# A\n")
    with pytest.raises(NotADirectoryError):
        Library.from_path(tmp_path / "a.md")


@pytest.mark.parametrize("kwargs", [{"levels": 0}, {"first": 0}, {"depth": 0}])
def test_levels_and_first_must_be_positive(tmp_path: Path, kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="must be at least 1"):
        Library.from_path(tmp_path).tree(**kwargs)


def test_readme_titles_a_directory_before_index(tmp_path: Path) -> None:
    write(tmp_path, "index.md", "# Index\n")
    write(tmp_path, "README.md", "# Readme\n")
    library = Library.from_path(tmp_path)
    assert str(library.root.title) == "Readme"
    assert [e.name for e in library.root.entries()] == ["README.md", "index.md"]


def test_an_empty_heading_leaves_the_file_untitled(tmp_path: Path) -> None:
    write(tmp_path, "blank.md", "#\ntext\n")
    lines = Library.from_path(tmp_path).tree().splitlines()
    assert lines[1] == "  blank.md (2 lines)"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_symlinked_directories_are_not_followed(tmp_path: Path) -> None:
    write(tmp_path, "real/a.md", "# A\n")
    (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)
    assert [e.name for e in Library.from_path(tmp_path).root.entries()] == ["real"]


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="needs POSIX permissions")
def test_unreadable_entries_are_skipped_and_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, "ok.md", "# Ok\n")
    write(tmp_path, "locked.md", "# Locked\n")
    write(tmp_path, "closed/inner.md", "# Inner\n")
    (tmp_path / "locked.md").chmod(0)
    (tmp_path / "closed").chmod(0)
    try:
        assert main([str(tmp_path)]) == 0
    finally:
        (tmp_path / "locked.md").chmod(0o644)
        (tmp_path / "closed").chmod(0o755)
    captured = capsys.readouterr()
    assert captured.out.splitlines()[1:] == ["  ok.md Ok (1 line)"]
    assert "mdpeek: skipped " in captured.err
    assert "locked.md: Permission denied" in captured.err
    assert "closed: Permission denied" in captured.err


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("a/b/c.md", "a/**", True),
        ("a.md", "?.md", True),
        ("a/b.md", "?/b.md", True),
        ("ab.md", "?.md", False),
        ("[x.md", "[x.md", True),
        ("b.md", "[abc].md", True),
        ("d.md", "[!abc].md", True),
        ("a.md", "[!abc].md", False),
        ("a+b.md", "a+b.md", True),
    ],
)
def test_glob_match(path: str, pattern: str, expected: bool) -> None:
    assert glob_match(path, pattern) is expected


def test_tree_headings_count_their_tables(tmp_path: Path) -> None:
    write(tmp_path, "data.md", "# Data\n## Sales\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    lines = Library.from_path(tmp_path).tree(depth=1).splitlines()
    assert lines[-1] == "    [S1.1] Sales (3, 1 table)"
