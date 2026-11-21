# Using mdpeek in an MCP server

mdpeek ships a ready-made MCP tool. Add it to your server and your agents can
read large markdown a piece at a time (a map first, then only the sections,
tables and code blocks they need) instead of loading whole files into
context.

- [Quick start](#quick-start)
- [What the agent sees](#what-the-agent-sees)
- [Supported servers](#supported-servers)
- [Configuration](#configuration)
- [Telemetry and access control: hooks](#telemetry-and-access-control-hooks)
- [Other ways to integrate](#other-ways-to-integrate)
- [Errors](#errors)
- [Security](#security)
- [Testing your integration](#testing-your-integration)

## Quick start

```sh
uv add mdpeek          # or: pip install mdpeek
```

mdpeek doesn't depend on any MCP library: it uses the one your server already
has.

```python
from mcp.server.fastmcp import FastMCP   # or MCPServer (mcp 2.x), or fastmcp.FastMCP
from mdpeek.mcp import Toolset

server = FastMCP("my-server")

docs = Toolset(docs_dir="docs")          # the agent may read docs/ and below, nothing else
docs.register(server, name="docs")       # adds one tool, called "docs"
```

Optionally, tell the model about it in your server's instructions:

```python
server = FastMCP("my-server", instructions=docs.instructions("docs"))
```

## What the agent sees

One tool. What it does depends on which argument is given:

| Call | Result |
|------|--------|
| `docs()` | The map: the directory tree with file titles, sizes and headings, fitted to 150 lines. |
| `docs(source="guides/install.md")` | One file's outline: `[S1.2] Title (12)` per heading. |
| `docs(source="guides/install.md", full=True)` | The whole file (cut at `max_output_chars`). |
| `docs(ids=["guides/install.md#S1.2", "guides/deploy.md#T1"])` | Those sections, tables, diagrams (`D1`), code blocks (`F1`) or front matter (`meta`). |
| `docs(show="tables")` | One line per table (or `diagrams`, `fences`, `meta`), grouped by file. |
| `docs(grep="retry\|timeout")` | Sections with matching lines, files with most matches first. |
| `docs(source="guides/deploy.md", sql="select ...")` | Read-only SQL over that file's tables (`t1`, `t2`, ...). |

The other parameters refine those calls: `depth` and `full` for sections,
`rows` (`"10-20"`), `cols` (`"name,region"`) and `limit` for tables and
SQL.

The tool's description is kept short (about 300 characters), because every
session pays for it, and ends with "Call with help=True for how it works".
`docs(help=True)` returns the full guide: every call form, the ID scheme, the
rules and the limits. `docs.description(name)` and `docs.help(name)` return
both texts if you want to show or extend them.

A session usually goes map → search → fetch:

```text
docs()                                 → tree of the docs directory
docs(grep="retention")                 → guides/storage.md: [S2.1], [S4]
docs(ids=["guides/storage.md#S2.1"])   → that section, its subsections as stubs
```

Output is compact text, not JSON. Things the agent may want to act on come
last, as `note:` lines:

```text
| env | url |
|---|---|
| dev | dev.example |
note: query: showing the first 1 rows; raise limit (up to 500) or refine the query
```

## Supported servers

`register()` works with any server whose `tool()` decorator takes `name`,
`description` and `annotations`. Tested in CI:

| Library | Server class |
|---------|--------------|
| `mcp` 1.x (official SDK) | `mcp.server.fastmcp.FastMCP` |
| `mcp` 2.x (official SDK) | `mcp.server.mcpserver.MCPServer` |
| `fastmcp` | `fastmcp.FastMCP` |

Subclasses work too. mdpeek supports Python 3.10 to 3.15.

## Configuration

Settings that limit what the tool can reach belong to `Toolset`; settings
about how it appears belong to `register()`. One `Toolset` can be
registered more than once, under different names.

```python
docs = Toolset(
    docs_dir="docs",
    url_allow=["https://docs.example.com/"],
    sql=True,
    max_output_chars=20_000,
)
```

| `Toolset(...)` | Default | |
|----------------|---------|---|
| `docs_dir` | none | The only place the tool may read files. Every `source` must resolve inside it (symlinks included). Without it, the tool reads no files. |
| `url_allow` | none | URLs the tool may fetch: a prefix (`https://docs.example.com/guides/`), a host (`docs.example.com`) or a wildcard (`*.example.com`). Checked on every redirect. Empty means no URLs. |
| `url_headers` | none | Headers sent with every fetch, for example an API token. The agent cannot add headers. |
| `allow_private_networks` | `False` | Allow URLs that resolve to loopback, private or link-local addresses. |
| `cache`, `ttl` | `"memory"`, 3600 | Cache for fetched URLs: `"memory"`, `"disk"`, `None`, or your own `Cache`. |
| `fetch_timeout` | 30 | Seconds. |
| `engine` | `"auto"` | SQL engine: `sqlite`, or `duckdb` with `mdpeek[duckdb]`. |
| `sql` | `True` | `False` removes the `sql` parameter. |
| `query_timeout` | 10 | Seconds before a query is stopped. |
| `tables` | defaults | A `TableSettings`: how tables are summarised in sections. |
| `diagram_summaries` | `True` | Show diagrams in sections as one-line stubs. |
| `default_limit`, `max_limit` | 50, 500 | Rows returned by SQL; the agent can ask for up to `max_limit`. |
| `budget` | 150 | Lines for the directory map and directory-wide lists. |
| `max_output_chars` | 40,000 | Hard cap on one result, with a note saying it was cut. |
| `formats` | `False` | Add a `format` parameter (`csv`, `json`, ...) for machine consumers. |
| `errors` | `"raise"` | Or `"return"`: see [Errors](#errors). |

| `register(server, ...)` / `tool(...)` | Default | |
|---------------------------------------|---------|---|
| `name` | `"mdpeek"` | The tool's name. |
| `description` | built in | Replace the short description. `docs.description(name)` gives the default to extend; keep the pointer to `help=True`. |
| `before_call`, `after_call`, `wrap` | none | See [hooks](#telemetry-and-access-control-hooks). |

## Telemetry and access control: hooks

Three hooks let a server record and control calls without wrapping mdpeek's
code.

```python
from mdpeek.mcp import ToolCall, ToolOutcome

def record(call: ToolCall, outcome: ToolOutcome) -> None:
    metrics.emit(
        "tool_call",
        tool=call.tool,               # the registered name
        mode=call.mode,               # map | ids | show | grep | sql
        status=outcome.status,        # ok | error | denied
        duration_ms=outcome.duration_ms,
        error_class=outcome.error_class,
        output_chars=outcome.output_chars,
        truncated=outcome.truncated,  # a row, tree or output cap was hit
    )

def check(call: ToolCall) -> None:
    if not current_user_may_read_docs():
        raise PermissionError("docs are not available to you")

docs.register(server, name="docs", before_call=check, after_call=record)
```

- **`after_call(call, outcome)`** runs after every call, even one that failed
  or was refused. If it raises, the error is logged on the `mdpeek.mcp`
  logger and the agent's result is unchanged, so a telemetry bug never breaks
  the tool.
- **`before_call(call)`** runs first. Raise `PermissionError` to refuse the
  call; `after_call` then sees `status="denied"`.
- **`wrap(fn, name)`** applies decorators you already have, outermost:
  `wrap=lambda fn, name: my_timer(name)(fn)`. A decorator that uses
  `functools.wraps` keeps the tool's schema intact.

Both hooks may be plain functions or `async def`. They run in the tool's own
async context, not a worker thread, so context variables your server sets per
request (the caller's identity, a request ID) are visible in them.

`ToolOutcome` also has `error` (the message the agent saw), `source_kind`
(`docs_dir`, `path` or `url`) and `cached` (URL sources).

`call.arguments` holds the arguments as the agent sent them, which can
include SQL or search text. mdpeek never logs them; record them only if your
privacy rules allow.

If your server marks a call as failed when a tool returns an error as text,
`after_call` makes that unnecessary: with `errors="return"`, the agent gets
the message as text but `outcome.status` is still `"error"`.

## Other ways to integrate

**Write the tool yourself** when you want your own name, docstring or
parameters, and call the toolset from it. Hooks don't run here; use your own
decorators.

```python
@server.tool()
async def handbook(ids: list[str] | None = None, grep: str | None = None) -> str:
    """Browse the handbook: no arguments for the map, ids to read, grep to search."""
    return await docs.call(ids=ids, grep=grep)
```

**Register by hand**, or with a framework `register()` doesn't know:

```python
spec = docs.tool("docs", after_call=record)   # ToolSpec(name, fn, description, annotations)
server.tool(name=spec.name, description=spec.description)(spec.fn)
```

`spec.fn` is an `async def` with a real signature, type hints and docstring.
`docs.call_sync(...)` runs the same call from sync code or tests.

## Errors

A bad call fails with a message that says what to do instead:

```text
no section 'S9'; nearby: S1, S2
'../secrets.md' is outside the docs directory; give a path inside it
pass only one of grep, sql
only read-only queries are allowed (SELECT or WITH ... SELECT)
```

By default (`errors="raise"`) the tool raises, and the server returns an MCP
error result (`isError: true`) with that message. `register()` raises it as
the server library's own `ToolError`, because some libraries hide the message
of any other exception.

With `errors="return"`, the message comes back as ordinary text starting
`error: `, for servers whose convention is never to raise.

Messages and notes never include the docs directory's absolute path.

## Security

The tool is read-only, and was built for input from a model, which a prompt
injection may have steered:

- **Files**: only inside `docs_dir`. Absolute paths, `..` and symlinks that
  lead outside are refused; symlinked files that lead outside are left out of
  the map.
- **SQL**: only `SELECT` (and `WITH ... SELECT`). sqlite runs under an
  allow-list authoriser, so `ATTACH`, `VACUUM INTO`, `PRAGMA` and writes are
  refused; DuckDB runs with external access off, so it cannot read or write
  files. Queries stop after `query_timeout` and fetch at most `max_limit`
  rows.
- **URLs**: off unless `url_allow` is set; every redirect is checked against
  it; non-public addresses are refused unless `allow_private_networks`; the
  agent cannot set headers; responses over 50 MB are refused.
- **Output**: capped at `max_output_chars`.

The tool is annotated `readOnlyHint=True`, `destructiveHint=False`,
`idempotentHint=True`, and `openWorldHint` only when URLs are allowed.

## Testing your integration

Call the tool directly; you don't need a client:

```python
def test_docs_tool_reads_the_handbook():
    docs = Toolset(docs_dir="docs")
    assert docs.call_sync().startswith("./ ")
    assert "Install" in docs.call_sync(grep="install")
```

To check the registration end to end, connect your server's in-memory
client, list the tools, and call `docs` with `{}`.
