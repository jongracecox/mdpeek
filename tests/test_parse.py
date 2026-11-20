import pytest

from mdpeek.model import SectionNotFound
from mdpeek.parse import parse


def tree(text: str) -> list[tuple[str, str, int]]:
    """(id, title, depth) for every section."""
    return [(s.id, s.title, s.depth) for s in parse(text).walk()]


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("front_matter.md", [("S0", "", 1), ("S1", "First", 1), ("S1.1", "Child", 2)]),
        ("code_fences.md", [("S1", "Code", 1), ("S2", "After", 1)]),
        ("setext.md", [("S1", "Setext Title", 1), ("S1.1", "Sub Title", 2)]),
        (
            "skipped_levels.md",
            [
                ("S1", "Top", 1),
                ("S1.1", "Skipped to three", 2),
                ("S1.2", "Back to two", 2),
                ("S1.2.1", "Four", 3),
            ],
        ),
        (
            "duplicates_and_numbering.md",
            [
                ("S1", "Notes", 1),
                ("S2", "Notes", 1),
                ("S2.1", "1. Intro / Overview", 2),
                ("S2.2", "2.3 Numbered", 2),
            ],
        ),
        (
            "empty_sections.md",
            [("S1", "Empty", 1), ("S2", "Also empty", 1), ("S2.1", "Child of empty", 2)],
        ),
        ("nested_headings.md", [("S0", "", 1), ("S1", "Real", 1)]),
        ("no_headings.md", [("S0", "", 1)]),
        ("no_trailing_newline.md", [("S1", "No trailing newline", 1)]),
        ("crlf.md", [("S1", "CRLF", 1), ("S1.1", "Sub", 2)]),
    ],
)
def test_section_tree(fixture_text, fixture, expected):
    assert tree(fixture_text(fixture)) == expected


def test_empty_document_has_no_sections():
    assert parse("").sections == []


def test_blank_preamble_is_not_a_section():
    assert tree("\n\n# A\n") == [("S1", "A", 1)]


def test_document_starting_below_level_one():
    assert tree("## A\n### B\n## C\n") == [("S1", "A", 1), ("S1.1", "B", 2), ("S2", "C", 1)]


def test_body_line_count_trims_outer_blank_lines(fixture_text):
    doc = parse(fixture_text("code_fences.md"))
    assert doc.get("S1").body_line_count(doc.lines) == 6
    assert doc.get("S2").body_line_count(doc.lines) == 1


def test_setext_heading_spans_two_lines(fixture_text):
    doc = parse(fixture_text("setext.md"))
    s1 = doc.get("S1")
    assert (s1.start, s1.body_start) == (0, 2)


def test_get_is_case_insensitive(fixture_text):
    doc = parse(fixture_text("skipped_levels.md"))
    assert doc.get("s1.2.1").title == "Four"


def test_get_unknown_suggests_siblings(fixture_text):
    doc = parse(fixture_text("skipped_levels.md"))
    with pytest.raises(SectionNotFound) as exc:
        doc.get("S1.9")
    assert exc.value.suggestions == ["S1.1", "S1.2"]
    assert str(exc.value) == "no section 'S1.9'; nearby: S1.1, S1.2"


def test_get_unknown_top_level_suggests_top_level(fixture_text):
    doc = parse(fixture_text("front_matter.md"))
    with pytest.raises(SectionNotFound) as exc:
        doc.get("S7")
    assert exc.value.suggestions == ["S0", "S1"]


def test_unclosed_front_matter_is_ordinary_text():
    # No closing fence: the '---' is a thematic break, not front matter.
    assert tree("---\ntitle: x\n\n# A\n") == [("S0", "", 1), ("S1", "A", 1)]
