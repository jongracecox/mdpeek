import json

import pytest

from mdpeek import Document
from mdpeek.fences import FenceNotFound, render_fence_list, render_fences, summary


@pytest.fixture
def doc(fixture_text) -> Document:
    return Document.from_text(fixture_text("diagrams.md"))


def test_every_top_level_fence_gets_an_id(doc):
    assert [(f.id, f.section_id, f.language, f.diagram_id) for f in doc.fences] == [
        ("F1", "S1", "mermaid", "D1"),
        ("F2", "S1", "python", None),
        ("F3", "S1.1", "dot", "D2"),
        ("F4", "S1.1", "plantuml", "D3"),
        ("F5", "S1.1", "d2", "D4"),
        ("F6", "S1.1", "puml", "D5"),
        ("F7", "S1.2", "mermaid", "D6"),
    ]


def test_fence_without_language_and_indented_code():
    doc = Document.from_text("```\nplain text\n```\n\n    indented code\n")
    assert [(f.id, f.language) for f in doc.fences] == [("F1", None)]
    assert summary(doc.fences[0]) == "[F1] S0 plain (1 line)"


def test_summary_links_diagrams(doc):
    assert summary(doc.fence("f1")) == "[F1] S1 mermaid (6 lines) = D1"
    assert summary(doc.fence("F2"), with_section=False) == "[F2] python (2 lines)"


def test_unknown_fence_lists_ids(doc):
    with pytest.raises(FenceNotFound, match=r"available: F1\.\.F7"):
        doc.fence("F9")
    small = Document.from_text("```\na\n```\n")
    with pytest.raises(FenceNotFound, match=r"available: F1$"):
        small.fence("F2")
    with pytest.raises(FenceNotFound, match="no fenced blocks"):
        Document.from_text("# A\n").fence("F1")


def test_scope(doc):
    assert [f.id for f in doc.fences_in(["S1.1"])] == ["F3", "F4", "F5", "F6"]


def test_view_output_is_unchanged_by_fences(doc):
    assert "```python" in doc.full(sections=["S1"], depth=1)


def test_output_formats(doc):
    # one fence: bare source; several: labelled and fenced
    assert render_fences([doc.fence("F2")], "md") == '# a code block, not a diagram\nprint("hi")\n'
    assert render_fences(doc.fences[1:3], "md") == (
        '[F2] S1 python (2 lines)\n```python\n# a code block, not a diagram\nprint("hi")\n```\n'
        "\n[F3] S1.1 dot (3 lines) = D2\n~~~ dot\nstrict digraph G {\n  a -> b\n}\n~~~\n"
    )
    data = json.loads(render_fences([doc.fence("F2")], "json"))
    assert data == {
        "id": "F2",
        "section": "S1",
        "language": "python",
        "lines": 2,
        "diagram": None,
        "source": '# a code block, not a diagram\nprint("hi")\n',
    }
    listing = json.loads(render_fence_list(doc.fences, "json"))
    assert [o["diagram"] for o in listing][:2] == ["D1", None]
    assert "source" not in listing[0]
    assert len(render_fences(doc.fences[:2], "jsonl").splitlines()) == 2
