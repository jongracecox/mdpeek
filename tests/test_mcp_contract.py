"""The tool registered on a real MCP server and called through a client.

Runs against whichever MCP library is installed: the official SDK
(``FastMCP`` in 1.x, ``MCPServer`` in 2.x) or standalone fastmcp. The
``tests_mcp`` nox session runs it once per library; without one it skips.
"""

import asyncio
import importlib.util
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from mdpeek.mcp import Toolset

LIBRARY = Path(__file__).parent / "fixtures" / "library"


def _framework() -> str | None:
    if importlib.util.find_spec("fastmcp") is not None:
        return "fastmcp"
    if importlib.util.find_spec("mcp") is None:
        return None
    if importlib.util.find_spec("mcp.server.mcpserver") is not None:
        return "mcp2"
    return "mcp1"


FRAMEWORK = _framework()
pytestmark = pytest.mark.skipif(FRAMEWORK is None, reason="no MCP library installed")


def _server():
    if FRAMEWORK == "fastmcp":
        from fastmcp import FastMCP

        return FastMCP("test")
    if FRAMEWORK == "mcp2":
        from mcp.server.mcpserver import MCPServer

        return MCPServer("test")
    from mcp.server.fastmcp import FastMCP

    return FastMCP("test")


@asynccontextmanager
async def _client(server):
    if FRAMEWORK == "fastmcp":
        from fastmcp import Client

        async with Client(server) as client:
            yield client
    elif FRAMEWORK == "mcp2":
        from mcp.client import Client

        async with Client(server) as client:
            yield client
    else:
        from mcp.shared.memory import create_connected_server_and_client_session

        async with create_connected_server_and_client_session(server._mcp_server) as client:
            yield client


def _tools(listed):
    return getattr(listed, "tools", listed)


def _get(obj, *names):
    """The first attribute that exists: MCP SDK 2.x renamed fields to snake_case."""
    for name in names:
        if name in type(obj).model_fields:
            return getattr(obj, name)
    raise AttributeError(names[0])


async def _call(client, name, arguments):
    """(is_error, text, structured) for one call, whatever the client's style."""
    if FRAMEWORK == "fastmcp":
        from fastmcp.exceptions import ToolError

        try:
            result = await client.call_tool(name, arguments)
        except ToolError as exc:
            return True, str(exc), None
        return result.is_error, result.content[0].text, result.structured_content
    result = await client.call_tool(name, arguments)
    return (
        _get(result, "isError", "is_error"),
        result.content[0].text,
        _get(result, "structuredContent", "structured_content"),
    )


def _run(coro):
    return asyncio.run(coro)


def test_registers_one_read_only_tool_with_the_chosen_name():
    server = _server()
    Toolset(docs_dir=LIBRARY).register(server, name="docs")

    async def go():
        async with _client(server) as client:
            return _tools(await client.list_tools())

    tools = _run(go())
    assert [t.name for t in tools] == ["docs"]
    tool = tools[0]
    props = _get(tool, "inputSchema", "input_schema")["properties"]
    assert set(props) == {
        "source",
        "ids",
        "show",
        "grep",
        "sql",
        "depth",
        "full",
        "rows",
        "cols",
        "limit",
    }
    assert "enum" in json.dumps(props["show"])
    assert _get(tool.annotations, "readOnlyHint", "read_only_hint") is True
    assert "docs()" in tool.description


def test_sql_off_removes_the_parameter():
    server = _server()
    Toolset(docs_dir=LIBRARY, sql=False).register(server, name="docs")

    async def go():
        async with _client(server) as client:
            tool = _tools(await client.list_tools())[0]
            return _get(tool, "inputSchema", "input_schema")["properties"]

    assert "sql" not in _run(go())


def test_call_returns_text_only():
    server = _server()
    Toolset(docs_dir=LIBRARY).register(server, name="docs")

    async def go():
        async with _client(server) as client:
            return await _call(client, "docs", {"source": "guides/install.md"})

    is_error, text, structured = _run(go())
    assert not is_error
    assert text.startswith("[S1] Install")
    assert not structured


def test_errors_reach_the_client_as_tool_errors():
    server = _server()
    Toolset(docs_dir=LIBRARY).register(server, name="docs")

    async def go():
        async with _client(server) as client:
            return await _call(client, "docs", {"source": "../outside.md"})

    is_error, text, _ = _run(go())
    assert is_error
    assert "outside the docs directory" in text


def test_hooks_run_around_a_real_call():
    server = _server()
    seen = []
    Toolset(docs_dir=LIBRARY).register(
        server,
        name="docs",
        before_call=lambda call: seen.append(("before", call.mode)),
        after_call=lambda call, out: seen.append(("after", call.mode, out.status)),
    )

    async def go():
        async with _client(server) as client:
            await _call(client, "docs", {"grep": "install"})
            await _call(client, "docs", {"ids": ["nope.md#S1"]})

    _run(go())
    assert seen == [
        ("before", "grep"),
        ("after", "grep", "ok"),
        ("before", "ids"),
        ("after", "ids", "error"),
    ]


def test_host_decorators_via_wrap_keep_the_schema():
    import functools

    calls = []

    def timed(name):
        def decorator(fn):
            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                calls.append(name)
                return await fn(*args, **kwargs)

            return wrapper

        return decorator

    class HostServer(type(_server())):
        pass

    server = HostServer("test")
    Toolset(docs_dir=LIBRARY).register(server, name="docs", wrap=lambda fn, name: timed(name)(fn))

    async def go():
        async with _client(server) as client:
            tool = _tools(await client.list_tools())[0]
            outcome = await _call(client, "docs", {"show": "tables"})
            return _get(tool, "inputSchema", "input_schema")["properties"], outcome

    props, (is_error, text, _) = _run(go())
    assert "ids" in props and "show" in props
    assert not is_error and "[T1]" in text
    assert calls == ["docs"]


def test_hand_written_tool_calls_the_toolset():
    server = _server()
    docs = Toolset(docs_dir=LIBRARY)

    @server.tool()
    async def handbook(ids: list[str] | None = None, grep: str | None = None) -> str:
        """Browse the handbook."""
        return await docs.call(ids=ids, grep=grep)

    async def go():
        async with _client(server) as client:
            return await _call(client, "handbook", {"ids": ["guides/install.md#S1.1"]})

    is_error, text, _ = _run(go())
    assert not is_error and "Linux" in text
