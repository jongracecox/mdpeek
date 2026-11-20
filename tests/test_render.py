import pytest

from mdpeek import Document, Mode, SectionNotFound, render

TEXT = "# A\nIntro.\n## B\nOne.\n### C\nDeep.\n# D\n"


@pytest.fixture
def doc() -> Document:
    return Document.from_text(TEXT)


def test_document_methods_match_render(doc):
    assert doc.view() == render(doc, Mode.VIEW)
    assert doc.structure(depth=2) == render(doc, Mode.STRUCTURE, 2)
    assert doc.full(sections=["S1.1"]) == render(doc, Mode.FULL, sections=["S1.1"])


def test_mode_accepts_strings(doc):
    assert render(doc, "STRUCTURE") == render(doc, Mode.STRUCTURE)


def test_invalid_mode_is_rejected(doc):
    with pytest.raises(ValueError, match="expected one of: view, structure, full"):
        render(doc, "outline")


@pytest.mark.parametrize("depth", [0, -1])
def test_depth_below_one_is_rejected(doc, depth):
    with pytest.raises(ValueError, match="depth must be at least 1"):
        doc.view(depth=depth)


def test_duplicate_sections_render_once(doc):
    assert doc.full(sections=["S2", "s2"]) == "[S2] D\n"


def test_unknown_section_raises(doc):
    with pytest.raises(SectionNotFound):
        doc.view(sections=["S3"])


def test_empty_section_heading_only(doc):
    assert doc.view(sections=["S2"]) == "[S2] D\n"


def test_crlf_input_renders_with_lf():
    doc = Document.from_text("# A\r\nOne.\r\n## B\r\nTwo.\r\n")
    assert doc.full() == "[S1] A\nOne.\n  [S1.1] B\nTwo.\n"


def test_body_keeps_interior_blank_lines_and_drops_outer_ones():
    doc = Document.from_text("# A\n\n\nOne.\n\nTwo.\n\n\n")
    assert doc.full() == "[S1] A\nOne.\n\nTwo.\n"


def test_from_path_keeps_line_endings(tmp_path):
    path = tmp_path / "doc.md"
    path.write_bytes(b"# A\r\nOne.\r\n")
    assert Document.from_path(path).lines == ["# A\r\n", "One.\r\n"]


def test_stub_pluralisation():
    doc = Document.from_text("# A\n## One\nx\n## Two\nx\ny\n## None\n")
    assert doc.view() == (
        "[S1] A\n  [S1.1] One (1 line)\n  [S1.2] Two (2 lines)\n  [S1.3] None (0 lines)\n"
    )
