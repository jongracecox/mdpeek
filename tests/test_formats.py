import json

import pytest

from mdpeek.formats import format_rows, to_json

COLS = ["a", "b"]
ROWS = [[1, None], ["x,y", 'say "hi"']]


def test_markdown_escapes_pipes_and_newlines():
    assert format_rows(["h"], [["a|b"], ["two\nlines"]], "md") == (
        "| h |\n|---|\n| a\\|b |\n| two lines |\n"
    )


def test_csv_quotes_and_blanks_none():
    assert format_rows(COLS, ROWS, "csv") == 'a,b\n1,\n"x,y","say ""hi"""\n'


def test_tsv():
    assert format_rows(COLS, [[1, 2]], "tsv") == "a\tb\n1\t2\n"


def test_jsonl_uses_keys():
    out = format_rows(["Col A", "Col B"], [[1, None]], "jsonl", keys=["col_a", "col_b"])
    assert json.loads(out) == {"col_a": 1, "col_b": None}


def test_json_is_rejected_by_format_rows():
    with pytest.raises(ValueError, match="to_json"):
        format_rows(COLS, ROWS, "json")


def test_to_json_is_compact_and_keeps_unicode():
    assert to_json({"k": "café"}) == '{"k":"café"}\n'
