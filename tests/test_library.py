import json
import os
import re
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


def test_budget_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="budget must be at least 1"):
        Library.from_path(tmp_path).fit(0)


def test_fit_matches_the_tree_it_describes(tmp_path: Path) -> None:
    for name in ("a", "b", "c"):
        write(tmp_path, f"{name}/deep/{name}.md", f"# {name}\n## one\n## two\n")
    library = Library.from_path(tmp_path)
    for budget in range(1, 25):
        fit = library.fit(budget)
        tree = library.tree(levels=fit.levels, depth=fit.depth or None, first=fit.first)
        assert tree.count("\n") == fit.lines
        if fit.next_step is not None:
            assert fit.lines <= budget < fit.next_lines


def test_budget_on_an_empty_directory(tmp_path: Path) -> None:
    fit = Library.from_path(tmp_path).fit()
    assert (fit.levels, fit.depth, fit.first, fit.lines, fit.next_step) == (1, 0, None, 1, None)


def test_a_flat_directory_over_budget_suggests_more_entries(tmp_path: Path) -> None:
    for i in range(10):
        write(tmp_path, f"note{i}.md", "plain text\n")
    fit = Library.from_path(tmp_path).fit(5)
    assert (fit.first, fit.lines, fit.next_step, fit.next_lines) == (3, 5, "-n 4", 6)


def test_grep_limits_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="first must be at least 1"):
        Library.from_path(tmp_path).grep(re.compile("x"), first=0)


def test_grep_over_budget_says_so(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, "a.md", "# A\n## B\nneedle\n## C\nneedle\n")
    assert main([str(tmp_path), "--grep", "needle", "--budget", "2"]) == 0
    assert "mdpeek: grep: -n 1 is 4 lines, the smallest, over --budget 2" in capsys.readouterr().err


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="needs POSIX permissions")
def test_grep_reports_unreadable_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, "ok.md", "# Ok\nneedle\n")
    write(tmp_path, "locked.md", "# Locked\nneedle\n")
    (tmp_path / "locked.md").chmod(0)
    try:
        assert main([str(tmp_path), "--grep", "needle"]) == 0
    finally:
        (tmp_path / "locked.md").chmod(0o644)
    captured = capsys.readouterr()
    assert "(1 match in 1 file)" in captured.out
    assert "locked.md: Permission denied" in captured.err


def test_listing_as_json_and_reporting_unreadable_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, "b.md", "# B\n```sh\nls\n```\n")
    write(tmp_path, "a.md", "# A\n```py\nx = 1\n```\n")
    assert main([str(tmp_path), "--fences", "--format", "json"]) == 0
    records = json.loads(capsys.readouterr().out)
    assert [(r["path"], r["id"], r["language"]) for r in records] == [
        ("a.md", "F1", "py"),
        ("b.md", "F1", "sh"),
    ]
    if sys.platform != "win32" and os.geteuid() != 0:
        (tmp_path / "b.md").chmod(0)
        try:
            assert main([str(tmp_path), "--fences"]) == 0
        finally:
            (tmp_path / "b.md").chmod(0o644)
        captured = capsys.readouterr()
        assert "(1 fenced block in 1 file)" in captured.out
        assert "b.md: Permission denied" in captured.err
