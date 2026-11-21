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
| `docs(help=True)` | The guide: how to research a question, every call form, the rules, and a list of every document with its title and one-line summary. |
| `docs()` | The map: the directory tree with each file's title, size and summary, fitted to 150 lines. |
| `docs(source="guides/install.md")` | One file's outline: `[S1.2] Title (12)` per heading. |
| `docs(ids=["guides/install.md", "faq.md"])` | Whole files, several per call (`full=True` adds every level). |
| `docs(ids=["guides/install.md#S1.2", "guides/deploy.md#T1"])` | Those sections, tables, diagrams (`D1`), code blocks (`F1`) or front matter (`meta`). |
| `docs(grep="retry\|timeout")` | Sections with matching lines, each followed by up to two of those lines; files with most matches first. |
| `docs(show="tables")` | One line per table (or `diagrams`, `fences`, `meta`), grouped by file. |
| `docs(source="guides/deploy.md", sql="select ...")` | Read-only SQL over that file's tables (`t1`, `t2`, ...). |

The other parameters refine those calls: `depth` and `full` for sections,
`rows` (`"10-20"`), `cols` (`"name,region"`) and `limit` for tables and
SQL. Each parameter carries a description in the input schema.

**Titles and summaries.** A document's title is its front matter `title`,
else its first heading. Its summary is the front matter `summary` (or
`description`), else the first sentence of its first paragraph, else its
first few section headings. Front matter makes the map and the help list
far more useful: a file whose first heading is "Schema" says little on its
own.

**The description teaches a way of working.** It is short (about 550
characters), points at `help=True`, and tells the agent that answers are
often split across documents, so it keeps searching after the obvious one.
In testing, agents always called `help=True` with this description and
never without it, and the document list is what led them to the less
obvious files. `docs.description(name)` and `docs.help(name)` return both
texts.

A session usually goes guide → search → read:

```text
docs(help=True)                        → how to work, and every document with its summary
docs(grep="retention|ttl|expiry")      → guides/storage.md [S2.1] with the matching lines
docs(ids=["guides/storage.md", "reference/limits.md"])   → both files, whole
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
| `grep_lines` | 2 | Matching lines shown under each section in grep results; 0 shows sections only. |
| `catalog_lines` | 300 | Documents listed in `help=True`; 0 leaves the list out. |
| `max_output_chars` | 40,000 | Hard cap on one result, with a note saying it was cut. |
| `formats` | `False` | Add a `format` parameter (`csv`, `json`, ...) for machine consumers. |
| `errors` | `"raise"` | Or `"return"`: see [Errors](#errors). |

| `register(server, ...)` / `tool(...)` | Default | |
|---------------------------------------|---------|---|
| `name` | `"mdpeek"` | The tool's name. |
| `description_prefix`, `description_suffix` | none | Your text before or after mdpeek's description, for example "IMPORTANT: start here before using other tools", or what the docs cover. |
| `help_prefix`, `help_suffix` | none | Your text before or after the `help=True` guide: aliases, house rules, where to ask. |
| `description` | built in | Replace mdpeek's description entirely (the prefix and suffix still wrap it). Keep the pointer to `help=True`. |
| `before_call`, `after_call`, `wrap` | none | See [hooks](#telemetry-and-access-control-hooks). |

### Adding your own context

The defaults are generic. Wrap them with what only your server knows: why
the docs matter, what they cover, aliases, where to ask.

```python
docs.register(
    server,
    name="docs",
    description_prefix=(
        "IMPORTANT: Start here before using other tools. These are the platform docs: "
        "naming conventions, client aliases and the rules for querying correctly."
    ),
    help_prefix="Client aliases: ACME = Acme Retail (catalog acme_prod).",
    help_suffix="If the docs don't answer it, ask in #data-help.",
)
```

Keep the prefix to a sentence or two: every session reads the description.

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
