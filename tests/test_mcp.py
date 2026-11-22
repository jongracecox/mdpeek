"""The MCP toolset without any MCP library: calls, limits, hooks, registration."""

import asyncio
import contextvars
import logging
import subprocess
import sys
from pathlib import Path

import pytest

from mdpeek.mcp import ToolCall, ToolError, ToolOutcome, Toolset

FIXTURES = Path(__file__).parent / "fixtures"
SMALL = FIXTURES / "small"


@pytest.fixture
def small() -> Toolset:
    return Toolset(docs_dir=SMALL)


# -- calls -----------------------------------------------------------------------


def test_file_map_honours_depth():
    docs = Toolset(docs_dir=FIXTURES / "library")
    assert docs.call_sync(source="guides/install.md", depth=1) == "[S1] Install (0, 2 sub)\n"
    assert "[S1.1]" in docs.call_sync(source="guides/install.md")


def test_full_needs_a_file():
    with pytest.raises(ToolError, match="full applies to one file"):
        Toolset(docs_dir=FIXTURES / "library").call_sync(full=True)


def test_diagrams_and_fences_by_id(small):
    listed = small.call_sync(source="diagrams.md", show="diagrams")
    assert listed.startswith("[D1]")
    source = small.call_sync(source="diagrams.md", ids=["D1"])
    assert "[D1]" not in source  # a single item is its bare source
    both = small.call_sync(source="code_fences.md", ids=["F1", "S1"])
    assert both.startswith("[S1]") or "[F1]" in both


def test_front_matter(small):
    assert small.call_sync(source="front_matter.md", show="meta").strip()
    assert small.call_sync(source="front_matter.md", ids=["meta"]).strip()


def test_ids_scope_grep_to_sections(small):
    assert small.call_sync(source="nested_headings.md", grep=".", ids=["S1"]).startswith("[S1]")
    with pytest.raises(ToolError, match="ids scope sections"):
        small.call_sync(source="nested_headings.md", grep=".", ids=["T1"])


def test_table_preview_notes_held_back_rows(small):
    text = small.call_sync(source="tables.md", ids=["T1"], limit=1, rows="1-2")
    assert "note: T1: showing 1 of 2 rows (use rows, limit or full)" in text


def test_limit_is_capped_by_max_limit():
    docs = Toolset(docs_dir=FIXTURES / "library", max_limit=1)
    text = docs.call_sync(source="guides/deploy.md", sql="select * from t1", limit=99)
    assert text.count("| dev |") == 1
    assert "up to 1" in text


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"source": "tables.md", "ids": ["X1"]}, "unknown ID 'X1'"),
        ({"depth": 0}, "depth must be at least 1"),
        ({"limit": 0}, "limit must be at least 1"),
        ({"show": "pictures"}, "show must be tables"),
        ({"nope": 1}, "unknown argument"),
        ({"format": "json", "show": "tables"}, "unknown argument"),
        ({"rows": "1-2"}, "rows and cols only apply"),
        ({"source": "tables.md", "ids": ["S1"], "rows": "1"}, "only apply to table IDs"),
        ({"source": "tables.md", "grep": "("}, "pattern"),
    ],
)
def test_bad_calls_name_the_fix(small, arguments, message):
    with pytest.raises(ToolError, match=message):
        small.call_sync(**arguments)


def test_formats_option_adds_format(small):
    docs = Toolset(docs_dir=SMALL, formats=True)
    assert docs.call_sync(source="tables.md", show="tables", format="json").startswith("[")
    with pytest.raises(ToolError, match="format applies"):
        docs.call_sync(source="tables.md", format="json")


def test_output_is_capped_at_a_line(small):
    docs = Toolset(docs_dir=SMALL, max_output_chars=40)
    text = docs.call_sync(source="tables.md", ids=["S1"], full=True)
    body, _, note = text.rpartition("note: ")
    assert len(body) <= 40 and body.endswith("\n")
    assert note.startswith("output cut at 40 characters")


def test_errors_can_be_returned_as_text():
    docs = Toolset(docs_dir=SMALL, errors="return")
    assert docs.call_sync(ids=["S1"]).startswith("error: in a directory, name the file: PATH#ID")
    assert asyncio.run(docs.call(ids=["S1"])).startswith("error: ")


def test_absolute_paths_never_reach_the_agent(small):
    with pytest.raises(ToolError) as caught:
        small.call_sync(source="nope.md")
    assert str(SMALL.resolve()) not in str(caught.value)


def test_settings_are_checked():
    with pytest.raises(NotADirectoryError):
        Toolset(docs_dir=SMALL / "tables.md")
    with pytest.raises(ValueError, match="errors must be"):
        Toolset(errors="ignore")  # type: ignore[arg-type]


def test_no_docs_dir_and_no_urls_reads_nothing():
    with pytest.raises(ToolError, match="nothing to read"):
        Toolset().call_sync()


def test_async_call_matches_sync(small):
    assert asyncio.run(small.call(source="tables.md")) == small.call_sync(source="tables.md")


# -- URLs ------------------------------------------------------------------------


def test_url_sources_follow_the_allow_list(http_server):
    http_server.serve("/doc.md", "# Doc\nBody.\n")
    http_server.redirects["/elsewhere"] = "http://example.invalid/doc.md"
    docs = Toolset(url_allow=[f"{http_server.url}/"], allow_private_networks=True)
    assert docs.call_sync(source=f"{http_server.url}/doc.md") == "[S1] Doc (1)\n"
    second = docs.call_sync(source=f"{http_server.url}/doc.md")
    assert "note: cached " in second
    with pytest.raises(ToolError, match="URL not allowed"):
        docs.call_sync(source="https://example.com/doc.md")
    with pytest.raises(ToolError, match="URL not allowed"):
        docs.call_sync(source=f"{http_server.url}/elsewhere")


def test_url_headers_come_from_the_host(http_server):
    http_server.serve("/doc.md", "# Doc\n")
    docs = Toolset(
        url_allow=[http_server.url], allow_private_networks=True, url_headers={"X-Key": "k"}
    )
    docs.call_sync(source=f"{http_server.url}/doc.md")
    assert http_server.requests[-1]["headers"]["X-Key"] == "k"


def test_private_addresses_are_refused_by_default(http_server):
    http_server.serve("/doc.md", "# Doc\n")
    docs = Toolset(url_allow=[http_server.url])
    with pytest.raises(ToolError, match="non-public address"):
        docs.call_sync(source=f"{http_server.url}/doc.md")


# -- hooks -----------------------------------------------------------------------


def _run(spec, **arguments):
    return asyncio.run(spec.fn(**arguments))


def test_hooks_see_mode_status_and_details(small):
    seen: list[tuple[ToolCall, ToolOutcome]] = []
    spec = small.tool("docs", after_call=lambda c, o: seen.append((c, o)))
    _run(spec, source="tables.md", ids=["T1"], rows="1-3", limit=1)
    call, outcome = seen[-1]
    assert (call.tool, call.mode, outcome.status) == ("docs", "ids", "ok")
    assert call.arguments == {"source": "tables.md", "ids": ["T1"], "rows": "1-3", "limit": 1}
    assert outcome.truncated and outcome.output_chars > 0
    assert outcome.source_kind == "path" and outcome.cached is None
    assert outcome.duration_ms >= 0


def test_after_call_runs_on_errors_and_sees_text_errors_as_errors():
    seen = []
    docs = Toolset(docs_dir=SMALL, errors="return")
    spec = docs.tool(after_call=lambda c, o: seen.append(o))
    assert _run(spec, ids=["S1"]).startswith("error: ")
    assert seen[-1].status == "error"
    assert seen[-1].error_class == "ToolError"
    assert "PATH#ID" in seen[-1].error


def test_before_call_can_refuse(small):
    seen = []

    def deny(call):
        raise PermissionError("not for you")

    spec = small.tool(before_call=deny, after_call=lambda c, o: seen.append(o))
    with pytest.raises(PermissionError):
        _run(spec)
    assert seen[-1].status == "denied" and seen[-1].error == "not for you"


def test_a_failing_after_call_is_logged_not_raised(small, caplog):
    def broken(call, outcome):
        raise RuntimeError("telemetry down")

    spec = small.tool(after_call=broken)
    with caplog.at_level(logging.ERROR, logger="mdpeek.mcp"):
        assert _run(spec, source="tables.md")
    assert "after_call hook failed" in caplog.text


def test_hooks_share_the_callers_context(small):
    request = contextvars.ContextVar("request", default=None)
    seen = []

    def before(call):
        request.set("user-1")

    async def after(call, outcome):
        seen.append(request.get())

    asyncio.run(small.tool(before_call=before, after_call=after).fn())
    assert seen == ["user-1"]


def test_wrap_is_outermost(small):
    order = []

    def wrap(fn, name):
        async def wrapped(**kwargs):
            order.append(f"wrap:{name}")
            return await fn(**kwargs)

        return wrapped

    spec = small.tool("docs", before_call=lambda c: order.append("before"), wrap=wrap)
    _run(spec)
    assert order == ["wrap:docs", "before"]


def test_error_type_converts_mdpeek_errors(small):
    class FrameworkError(Exception):
        pass

    spec = small.tool(error_type=FrameworkError)
    with pytest.raises(FrameworkError, match="PATH#ID"):
        _run(spec, ids=["S1"])


# -- the tool's shape ------------------------------------------------------------


def test_signature_matches_the_settings():
    import inspect

    assert "sql" in inspect.signature(Toolset(docs_dir=SMALL).tool().fn).parameters
    assert "sql" not in inspect.signature(Toolset(docs_dir=SMALL, sql=False).tool().fn).parameters
    assert "format" in inspect.signature(Toolset(docs_dir=SMALL, formats=True).tool().fn).parameters
    assert "help" in inspect.signature(Toolset(docs_dir=SMALL).tool().fn).parameters


def test_tool_names_are_checked(small):
    assert small.tool("read_docs").name == "read_docs"
    with pytest.raises(ValueError, match="invalid tool name"):
        small.tool("read docs")


def test_description_stays_compact():
    """Every session pays for the description: keep it small; detail lives in help."""
    docs = Toolset(docs_dir=SMALL, url_allow=["example.com"])
    assert len(docs.description("docs")) < 700
    assert "help=True" in docs.description("docs")
    assert len(docs.instructions("docs")) < 600


def test_help_returns_the_full_guide(small):
    text = small.call_sync(help=True)
    assert text.startswith("# mdpeek: read the docs directory")
    assert 'mdpeek(ids=["a.md#T1"], rows="10-20"' in text
    assert "sql" not in Toolset(docs_dir=SMALL, sql=False).call_sync(help=True)
    assert small.call_sync(help=True, grep="ignored") == text


def test_help_uses_the_registered_name_and_reaches_hooks(small):
    seen = []
    spec = small.tool("docs", after_call=lambda c, o: seen.append((c.mode, o.status)))
    assert _run(spec, help=True).startswith("# docs: ")
    assert seen == [("help", "ok")]


def test_register_uses_only_what_the_server_accepts(small):
    class Server:
        def __init__(self):
            self.registered = {}

        def tool(self, name=None, description=None, annotations=None, structured_output=None):
            def decorator(fn):
                self.registered = {
                    "name": name,
                    "fn": fn,
                    "annotations": annotations,
                    "structured_output": structured_output,
                }
                return fn

            return decorator

    server = Server()
    spec = small.register(server, name="docs")
    assert server.registered["name"] == "docs"
    assert server.registered["structured_output"] is False
    assert server.registered["fn"] is spec.fn
    assert spec.annotations["readOnlyHint"] is True


def test_importing_the_module_loads_no_mcp_library():
    code = (
        "import sys, mdpeek.mcp; "
        "print(any(m.split('.')[0] in ('mcp', 'fastmcp') for m in sys.modules))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


# -- guidance and host context -------------------------------------------------


def test_host_text_wraps_description_and_help(small):
    spec = small.tool(
        "docs",
        description_prefix="IMPORTANT: start here.",
        description_suffix="Owned by the data team.",
        help_prefix="These docs cover the platform.",
        help_suffix="Questions: #data-help.",
    )
    assert spec.description.startswith("IMPORTANT: start here.\n\nRead the docs directory")
    assert spec.description.endswith("\n\nOwned by the data team.")
    text = _run(spec, help=True)
    assert text.startswith("These docs cover the platform.\n\n# docs: ")
    assert text.rstrip().endswith("Questions: #data-help.")


def test_description_replacement_is_still_wrapped(small):
    spec = small.tool(description="Custom.", description_prefix="Before.")
    assert spec.description == "Before.\n\nCustom."


def test_help_catalog_lists_documents_and_respects_the_cap():
    docs = Toolset(docs_dir=FIXTURES / "library", catalog_lines=2)
    text = docs.call_sync(help=True)
    catalog = text.split("## Documents\n\n", 1)[1].splitlines()
    assert len(catalog) == 3 and catalog[-1].startswith("- … 7 more")
    assert "## Documents" not in Toolset(docs_dir=FIXTURES / "library", catalog_lines=0).help()


def test_parameters_are_documented_when_pydantic_is_available(small):
    pytest.importorskip("pydantic")
    import inspect

    param = inspect.signature(small.tool().fn).parameters["ids"]
    assert "whole files" in param.annotation.__metadata__[0].description


def test_grep_lines_setting(small):
    assert "> " in Toolset(docs_dir=FIXTURES / "library").call_sync(grep="installer")
    assert "> " not in Toolset(docs_dir=FIXTURES / "library", grep_lines=0).call_sync(
        grep="installer"
    )


def test_bare_paths_and_folders_in_ids():
    docs = Toolset(docs_dir=FIXTURES / "library")
    assert docs.call_sync(ids=["guides/install.md"], full=True).count("Run the installer.") == 1
    with pytest.raises(ToolError, match="is a folder"):
        docs.call_sync(ids=["guides"])
    with pytest.raises(ToolError, match="empty ID"):
        docs.call_sync(ids=["guides/install.md#"])
