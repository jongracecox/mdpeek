import json

import pytest

from mdpeek import Document
from mdpeek.diagram_output import render_diagram_list, render_diagrams
from mdpeek.diagrams import DiagramNotFound, describe, summary


@pytest.fixture
def doc(fixture_text) -> Document:
    return Document.from_text(fixture_text("diagrams.md"))


def test_extraction(doc):
    assert [(d.id, d.section_id, d.language, d.kind, d.title) for d in doc.diagrams] == [
        ("D1", "S1", "mermaid", "flowchart", "Order flow"),
        ("D2", "S1.1", "graphviz", "digraph", None),
        ("D3", "S1.1", "plantuml", "uml", "Login"),
        ("D4", "S1.1", "d2", None, None),
        ("D5", "S1.1", "plantuml", "mindmap", None),
        ("D6", "S1.2", "mermaid", "sequenceDiagram", "Checkout"),
    ]


def test_source_and_raw_text(doc):
    d2 = doc.diagram("d2")
    assert d2.source == "strict digraph G {\n  a -> b\n}\n"
    assert d2.raw_text.startswith("~~~ dot\n") and d2.raw_text.endswith("~~~\n")
    assert d2.line_count == 3


@pytest.mark.parametrize(
    ("language", "source", "expected"),
    [
        ("mermaid", "%% note\n\ngantt\n    title Plan\n", ("gantt", "Plan")),
        ("mermaid", "---\ntitle: 'Quoted'\n---\npie\n", ("pie", "Quoted")),
        ("mermaid", "", (None, None)),
        ("plantuml", "A -> B\n", (None, None)),
        ("graphviz", "graph { a -- b }", ("graph", None)),
        ("d2", "a -> b", (None, None)),
    ],
)
def test_describe(language, source, expected):
    assert describe(language, source) == expected


def test_summaries(doc):
    assert summary(doc.diagram("D1")) == '[D1] mermaid flowchart "Order flow" (6 lines)'
    assert summary(doc.diagram("D4"), with_section=True) == "[D4] S1.1 d2 (1 line)"


def test_unknown_diagram(doc):
    with pytest.raises(DiagramNotFound, match="no diagram 'D9'; available: D1, D2"):
        doc.diagram("D9")
    with pytest.raises(DiagramNotFound, match="no diagrams"):
        Document.from_text("# A\n").diagram("D1")


def test_scope(doc):
    assert [d.id for d in doc.diagrams_in(["S1.2"])] == ["D6"]
    assert len(doc.diagrams_in()) == 6


def test_view_replaces_diagrams_and_counts_them(doc):
    out = doc.full(sections=["S1"], depth=1).splitlines()
    assert out == [
        "[S1] Diagrams",
        "Intro.",
        "",
        '[D1] mermaid flowchart "Order flow" (6 lines)',
        "",
        "```python",
        "# a code block, not a diagram",
        'print("hi")',
        "```",
    ]
    assert "  [S1.1] Other languages (22 lines, 4 diagrams)" in doc.view().splitlines()


def test_diagrams_inline_on_request(doc):
    out = doc.full(sections=["S1.1"], diagram_summaries=False).splitlines()
    assert out[1:4] == ["[D2]", "~~~ dot", "strict digraph G {"]


def test_output_formats(doc):
    d1 = doc.diagram("D1")
    assert render_diagrams([d1], "md") == d1.source  # one diagram: bare source
    several = render_diagrams(doc.diagrams[:2], "md")
    assert several.startswith('[D1] S1 mermaid flowchart "Order flow" (6 lines)\n```mermaid\n---\n')
    assert "\n\n[D2] S1.1 graphviz digraph (3 lines)\n~~~ dot\n" in several
    data = json.loads(render_diagrams([d1], "json"))
    assert data["source"].startswith("---\ntitle: Order flow")
    assert len(json.loads(render_diagrams(doc.diagrams[:2], "json"))) == 2
    listing = json.loads(render_diagram_list(doc.diagrams, "json"))
    assert "source" not in listing[0]
    assert listing[0]["lines"] == 6
    assert len(render_diagram_list(doc.diagrams, "jsonl").splitlines()) == 6
