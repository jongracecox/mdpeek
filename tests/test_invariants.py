"""Structural invariants that must hold for every fixture."""

import re

import pytest
from conftest import SMALL_FIXTURES, read_fixture

from mdpeek.parse import parse

ID_PATTERN = re.compile(r"^S(0|[1-9]\d*(\.[1-9]\d*)*)$")


@pytest.fixture(params=SMALL_FIXTURES, ids=lambda p: p.name)
def doc(request):
    return parse(read_fixture(request.param))


def test_top_level_spans_rebuild_the_text(doc):
    rebuilt = "".join("".join(doc.lines[s.start : s.end]) for s in doc.sections)
    leading = "".join(doc.lines[: doc.sections[0].start]) if doc.sections else doc.text
    assert leading + rebuilt == doc.text


def test_every_line_has_exactly_one_owner(doc):
    owners = [0] * len(doc.lines)
    for section in doc.walk():
        heading = range(section.start, section.body_start)
        body = range(section.body_start, section.body_end)
        for i in (*heading, *body):
            owners[i] += 1
    first = doc.sections[0].start if doc.sections else len(doc.lines)
    assert all(count == 0 for count in owners[:first])  # blank lines before the first heading
    assert all(count == 1 for count in owners[first:])


def test_ids_are_well_formed_unique_and_contiguous(doc):
    ids = [s.id for s in doc.walk()]
    assert len(ids) == len(set(ids))
    assert all(ID_PATTERN.match(i) for i in ids)
    numbered = [s for s in doc.sections if not s.is_preamble]
    assert [s.id for s in numbered] == [f"S{i}" for i in range(1, len(numbered) + 1)]
    for section in doc.walk():
        assert [c.id for c in section.children] == [
            f"{section.id}.{i}" for i in range(1, len(section.children) + 1)
        ]


def test_children_nest_inside_parent(doc):
    for section in doc.walk():
        for child in section.children:
            assert section.body_end <= child.start
            assert child.end <= section.end
            assert child.depth == section.depth + 1
            assert child.parent is section
