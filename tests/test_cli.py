import pytest

from mdpeek import __version__
from mdpeek.cli import main


def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"mdpeek {__version__}"


def test_missing_source_is_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
    assert "usage: mdpeek" in capsys.readouterr().err


def test_reads_stdin(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("# A\nbody\n"))
    assert main(["-", "--full"]) == 0
    assert capsys.readouterr().out == "[S1] A\nbody\n"


def test_non_utf8_bytes_are_replaced(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "latin1.md"
    path.write_bytes(b"# caf\xe9\nbody\n")
    assert main([str(path)]) == 0
    assert capsys.readouterr().out == "[S1] caf\ufffd\nbody\n"


def test_depth_must_be_a_number(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["doc.md", "--depth", "two"])
    assert "must be a whole number" in capsys.readouterr().err


def test_grep_lines_are_an_ops_option_the_cli_leaves_off(tmp_path, capsys):
    from mdpeek import Document, ops

    doc = Document.from_text("# A\nretry once\n")
    assert ops.grep_file(doc, "retry", lines=1).text == "[S1] A (1 match)\n  > retry once\n"
    assert ops.grep_file(doc, "retry").text == "[S1] A (1 match)\n"
