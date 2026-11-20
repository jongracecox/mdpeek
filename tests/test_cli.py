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


def test_non_utf8_file_is_a_read_error(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "latin1.md"
    path.write_bytes(b"# caf\xe9\n")
    assert main([str(path)]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_depth_must_be_a_number(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["doc.md", "--depth", "two"])
    assert "must be a whole number" in capsys.readouterr().err
