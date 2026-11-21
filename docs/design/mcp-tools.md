# Design: mdpeek as a ready-made MCP tool

Status: **implemented** (see [Implementation notes](#implementation-notes)
for where the build differs from this design). The user guide is
[docs/mcp.md](../mcp.md).

## Goal

Anyone building an MCP server should be able to give their agents mdpeek's
progressive exposure with almost no engineering:

```sh
uv add mdpeek
```

```python
from mdpeek.mcp import Toolset

docs = Toolset(docs_dir="docs")      # the agent may read docs/ and below, nothing else
docs.register(server, name="docs")   # adds one tool, `docs`
```

The main use is a server that ships its own markdown (a knowledge base, a
reference, runbooks) and today returns whole files from a "get doc" tool. With
mdpeek the agent sees a map first and pulls only the sections, tables and
blocks it needs.

## Decisions

| Question | Decision |
|----------|----------|
| How a server gets the tool | **Option A**: a framework-neutral toolset in the base package, with a registration helper. No MCP library is imported by mdpeek. |
| How many tools | **One** general-purpose tool. |
| Tool name | Set at registration (`name=`), default `mdpeek`. |
| Python versions | **3.10 to 3.15**, tested as a matrix. |
| SQL | **On** by default, read-only: `ATTACH` and every other non-`SELECT` statement refused. |
| Filesystem | Optional `docs_dir` at registration. When set, `source` is confined to it and its subdirectories. |
| Telemetry | Hooks before and after each call, plus a `wrap` for a host's existing decorators. See [Hooks](#hooks). |
| Bare `PATH` in `ids` | Dropped: `source="guides/x.md"` already selects a file. |

Options B (a standalone `mdpeek mcp` server) and C (a FastMCP-specific
integration) were considered and set aside; see [Options considered](#options-considered).

## Requirements

### R1. Host compatibility profile

The design must fit a common shape of production server, without depending
on any one server:

| # | Host trait | What it means for mdpeek |
|---|------------|--------------------------|
| H1 | Built on the official `mcp` SDK's FastMCP (`mcp.server.fastmcp.FastMCP`, 1.x), often a **subclass** of it | Work with that class and subclasses; don't rely on fastmcp-2-only features. |
| H2 | Registers tools with `@server.tool()`, **stacking its own decorators** underneath: one that times each call and records its status, and gates that check the caller's access | The host must be able to apply those decorators to mdpeek's tool, and to see what happened inside it. |
| H3 | Tools are `async def` and return `str` (markdown) | Async entry point; blocking work off the event loop; text, not structured output. |
| H4 | Tools that swallow an exception and return error text **mark the call as errored** through a context variable, so telemetry still counts it as a failure | If mdpeek returns errors as text, it must still report the call as failed (the `after_call` hook does). |
| H5 | Stateless streamable HTTP: no per-session server state; per-request identity in context variables | Each call self-contained. Hooks run in the caller's async context so those variables are visible. |
| H6 | Filters `tools/list` by tool name (access control) | Stable tool name, chosen by the host. |
| H7 | Its doc tools serve a bundled `docs/` directory by relative path, use front matter, and grep | Maps onto `Library`, `PATH#ID` addressing and `docs_dir` confinement. |
| H8 | **Runs on Python 3.10** | mdpeek must support 3.10. |
| H9 | Tool descriptions come from docstrings with an `Args:` section | The tool's description is the agent's guide; keep it compact. |

### R2. Agent ergonomics and token cost

- A tool's name, description and input schema go to the client on every
  `tools/list` and usually stay in the model's context all session. One tool
  with a small schema is the cheapest shape.
- Output is mdpeek's existing compact text (`[S2.1] Title (12 ln)`,
  `[T3] S5.2 6×320: city, ...`), already tuned and tracked by
  `evals/baseline.json`. No new JSON shape.
- Notes the CLI writes to stderr (truncation, cached-at, skipped tables,
  "showing 50 of 320 rows") reach the agent as trailing `note:` lines.
- Errors say what to do next, as the CLI's do
  (`unknown section S9; did you mean S1.9?`).

### R3. Security

A CLI runs with the user's own rights on input the user chose. A tool in a
shared server runs on input chosen by a model, possibly steered by a prompt
injection.

- **Filesystem.** `Document.from_path` and `Library.from_path` read any path.
  The tool confines `source` to `docs_dir`: relative paths only, no `..`,
  symlinks resolved and checked against the directory.
- **URLs.** `source.fetch` fetches any http(s) URL and follows redirects. Off
  by default; when on, an allow-list checked on every redirect hop, private and
  loopback addresses refused, headers set by the host only, the existing 50 MB
  cap and timeout.
- **SQL.** Verified: `mdpeek doc.md --sql "attach database '/tmp/x.db' as x"`
  creates `/tmp/x.db`. See [SQL safe mode](#sql-safe-mode).
- **Output size.** A hard cap on characters per response, with a note.

## The tool

`<name>(source=None, ids=None, show=None, grep=None, sql=None, depth=None,
full=False, rows=None, cols=None, limit=None) -> str`

It is a general-purpose tool. Which of `ids`, `show`, `grep` and `sql` you
pass picks what it does, as the CLI's flags do. Pass at most one of them;
`ids` may also scope `show` and `grep` to sections.

| Call | Result |
|------|--------|
| `docs()` | The map. File: heading outline with line counts. Directory: the tree fitted to 150 lines, with a note on what to ask for next. `depth` narrows or widens it. |
| `docs(source="a.md")` | The outline of that file. |
| `docs(ids=["S2.1", "T3"])` | The content for each ID. Sections in view mode (subsections as stubs; `depth` for more, `full=True` for all), tables as column types and first rows (`rows="10-20"`, `cols="city,region"` to slice), diagrams and fenced blocks as bare source, `meta` as front matter. In a directory, IDs are `PATH#ID`. |
| `docs(show="tables")` | A one-line-per-item inventory of `tables`, `diagrams`, `fences` or `meta`, grouped by file in a directory. |
| `docs(grep="retry\|limit")` | Sections with matching lines; files ranked by matches in a directory. |
| `docs(sql="select ...", source="a.md")` | SQL over that file's tables (`t1`, `t2`, ...), capped by `limit`. |

IDs say what they point at (`S` section, `T` table, `D` diagram, `F` fenced
block, `meta`), which is what lets one `ids` parameter replace a tool per kind.

- `source` is a path relative to `docs_dir`, an allowed URL, or `None` for
  `docs_dir` itself.
- `format` (md, csv, json, ...) is left out of the schema by default; a host
  can turn it on (`formats=True`).
- Registered as read-only: `readOnlyHint=True`, `idempotentHint=True`,
  `openWorldHint` true only when URLs are on.
- Size defaults are the CLI's: view depth 1, 50 data rows, tree budget 150
  lines. The host can tighten them; the agent can ask for more up to a host
  maximum.
- A bad combination (`grep` with `sql`) returns a short error naming the fix.
- The description carries a five-line cheat sheet like the table above, so no
  separate guide tool is needed. A test caps the size of the serialised
  `tools/list` entry, as `test_guide_stays_compact` does for the CLI guide.

Example session (`docs_dir="docs"`, registered as `docs`):

```
docs()                                → tree of docs/ with titles and counts
docs(grep="retention")                → guides/storage.md: 3 matches in [S2.1], [S4]
docs(ids=["guides/storage.md#S2.1"])  → that section, subsections as stubs
docs(source="guides/storage.md", show="tables")
docs(source="guides/storage.md", sql="select tier, max(days) from t2 group by 1")
```

## Registration (Option A)

A new module `mdpeek/mcp.py` that imports no MCP library at the top level.

```python
from mdpeek.mcp import Toolset

docs = Toolset(
    docs_dir="docs",             # optional; confines source to docs/ and below
    urls=False,                  # or url_allow=["https://docs.example.com/"]
    cache="memory",              # memory | disk | a Cache object
    engine="sqlite",
    tables=TableSettings(max_rows=5),
    max_output_chars=40_000,
    errors="raise",              # or "return"
)
```

Three levels of integration:

1. **One line**: `docs.register(server, name="docs")`. It calls the
   decorator factory `server.tool(name=..., description=...,
   annotations=...)(fn)`, which the official SDK's FastMCP (checked on 1.26)
   and standalone fastmcp 2.x both offer. (`add_tool` is not portable: the
   official SDK takes a function, fastmcp 2.x a `Tool` object.) On the
   official SDK it also passes `structured_output=False`, so the `str` result
   is sent once as text, not also wrapped as structured content.
2. **With hooks** for telemetry and access control:
   `docs.register(server, name="docs", before_call=..., after_call=...,
   wrap=...)`. See [Hooks](#hooks).
3. **Hand-written** for a host that wants its own docstring or extra
   parameters:
   ```python
   @server.tool()
   @log_calls("handbook")
   async def handbook(ids: list[str] | None = None, grep: str | None = None) -> str:
       """Browse the handbook: no args for the map, ids to read, grep to search."""
       return await docs.call(ids=ids, grep=grep)
   ```

`docs.tool(name=...)` returns a `ToolSpec(name, fn, description,
annotations)` for any other framework: `fn` is an `async def` with full type
hints, an `Args:` docstring and a correct `__signature__`, so frameworks that
build schemas from signatures can wrap it. `docs.call_sync(...)` is the same
call for sync code and tests.

No `mcp` extra is needed: a host already has its MCP library, and mdpeek
imports `ToolAnnotations` lazily from whichever one is installed.

## Hooks

The host wants to record every call (duration, status, error class, plus its
own identity fields) and sometimes refuse one. It already does this with
decorators (H2), and returns errors as text while marking the call as failed
(H4). mdpeek knows things those decorators can't see: which mode ran, how big
the output was, whether it was truncated or came from cache, and whether an
error was turned into text.

### Options

| | Shape | For | Against |
|---|---|---|---|
| H-a | `wrap=` only: `register(server, wrap=lambda fn, name: log_calls(name)(fn))` | Zero new host code; reuses existing decorators unchanged. | The decorator sees only arguments and the returned string. With `errors="return"` it records failures as `ok`. |
| H-b | `before_call` / `after_call` callbacks with typed `ToolCall` / `ToolOutcome` objects | The host gets mdpeek's details; failures are always reported as failures; no decorator gymnastics. | A small new API to keep stable. |
| H-c | One `on_event(event)` observer receiving `start` / `end` / `error` events | One callback. | Untyped union of events; harder to deny a call; more to document. |

**Recommendation: H-b, plus `wrap` from H-a.** `wrap` lets a host keep its
existing gate and timing decorators on day one. `after_call` is the
post-call hook for telemetry, and `before_call` covers access checks and
setting up per-request context.

### Proposed API (H-b)

```python
@dataclass(frozen=True)
class ToolCall:
    tool: str                 # the registered name, e.g. "docs"
    mode: str                 # "map" | "ids" | "show" | "grep" | "sql"
    arguments: Mapping[str, Any]   # as received; may contain user text (sql, grep)

@dataclass(frozen=True)
class ToolOutcome:
    status: str               # "ok" | "error" | "denied"
    duration_ms: float
    error_class: str | None   # e.g. "SectionNotFound"
    error: str | None         # the message the agent saw
    source_kind: str          # "docs_dir" | "path" | "url"
    output_chars: int
    truncated: bool           # a row, tree or output cap was hit
    cached: bool | None       # URL sources only

before_call: Callable[[ToolCall], None | Awaitable[None]]
after_call:  Callable[[ToolCall, ToolOutcome], None | Awaitable[None]]
```

Rules:

- **Order:** `wrap` (outermost) → `before_call` → the work → `after_call`.
  `after_call` runs in a `finally`, so it sees errors and denials too.
- **Context:** hooks run in the tool's own async context, not the worker
  thread, so the host's context variables (request identity, current tool)
  are visible and can be set.
- **Denial:** `before_call` raising `PermissionError` refuses the call:
  status `denied`, and the error goes to the agent as any other.
- **Failures are failures:** with `errors="return"`, the agent gets the
  message as text, but `after_call` still sees `status="error"`. This
  removes the need for a host's "mark this call as errored" convention (H4).
- **Hooks never mask the outcome:** an exception in `after_call` is logged
  (`logging.getLogger("mdpeek.mcp")`) and swallowed, the same rule the host's
  telemetry follows. An exception in `before_call` propagates, because that
  is how denial works.
- **Privacy:** `arguments` can hold user text (SQL, grep patterns). mdpeek
  never logs it; the host chooses what to record.
- Sync or async callables are both accepted.

A host would wire its telemetry like this:

```python
def record(call: ToolCall, out: ToolOutcome) -> None:
    emit("tool_call", tool=call.tool, mode=call.mode, status=out.status,
         duration_ms=out.duration_ms, error_class=out.error_class,
         output_chars=out.output_chars, truncated=out.truncated)

docs.register(server, name="docs", after_call=record,
              wrap=lambda fn, name: check_access(name)(fn))
```

## SQL safe mode

SQL stays on by default, read-only. `engines.py` gains a `safe=True` mode,
which the tool always uses and the CLI may adopt later:

- **sqlite**: after the tables are loaded, install an allow-list authoriser
  that permits only `SQLITE_SELECT`, `SQLITE_READ`, `SQLITE_FUNCTION` and
  `SQLITE_RECURSIVE` and denies everything else. Checked on Python's sqlite3:
  it refuses `ATTACH` (no file created), `VACUUM INTO` (which goes through
  `ATTACH`), `PRAGMA`, `INSERT` and `CREATE`, and still allows joins,
  subqueries and recursive CTEs. An allow-list is safer than blocking `ATTACH`
  by name, because a new statement type is refused by default. The tool
  returns `only SELECT queries are allowed`.
- A progress-handler time limit (a recursive CTE can run forever) and a row
  cap instead of an unbounded `fetchall()`.
- **duckdb**: connect with `enable_external_access=false` and
  `lock_configuration=true`, which closes `read_csv('/etc/...')`,
  `COPY ... TO`, `ATTACH` and httpfs.

## Filesystem: `docs_dir`

- `Toolset(docs_dir="docs")` resolves the directory once. Every `source` is
  joined to it, resolved (following symlinks), and must stay inside it.
  Absolute paths and `..` that escape are refused with a message that names
  the allowed form (`source must be a path inside the docs directory, e.g.
  guides/install.md`).
- `source=None` means the directory itself, so the agent can work without
  ever passing `source`.
- With `docs_dir` set, the description says "paths are relative to the docs
  directory", and the map is the tree of that directory.

What happens **without** `docs_dir` is the one open choice:

| | Without `docs_dir` | For | Against |
|---|---|---|---|
| D-a | No filesystem access; only allowed URLs work | Safe by default; a forgotten setting can't expose the server's disk | A local stdio user must name a directory |
| D-b | Any path the process can read, like the CLI | Handy for a personal stdio server | One missing argument opens the whole disk to the model |

Recommendation: **D-a**. A personal server can pass `docs_dir="/"` (or
`docs_dir=Path.home()`) on purpose.

## Python 3.10 to 3.15

mdpeek uses two 3.11-only features: `enum.StrEnum` (`options.py`) and
`datetime.UTC` (`cache.py`). Both have small equivalents:
`class StrEnum(str, Enum)` with `__str__` returning the value (or
`enum.StrEnum` when available), and `timezone.utc`.

- `requires-python = ">=3.10"`, classifiers for 3.10 to 3.15.
- `PYTHON_VERSIONS` in `noxfile.py` and the `tests.yml` matrix become
  `3.10` … `3.15`. The duckdb and eval sessions stay on one version (the
  newest that duckdb publishes wheels for).
- An MCP contract session runs on the oldest and newest versions.
- 3.10 reached end of life in October 2026; supporting it can be dropped
  later without breaking the API.
- Check before merging: the `uv` used in CI must be able to install 3.15. The
  local `uv` lists only `3.15.0a1` for download (3.15.0 is installed from
  Homebrew), so CI may need a newer `uv` or `actions/setup-python`.

## Cross-cutting design

### An operations layer

Much of the CLI's behaviour lives in private functions in `cli.py` that mix
argument parsing, rendering and `print(..., file=sys.stderr)`:
`_show_directory`, `_fetch_from_directory`, `_show_tables`, `_run_sql`,
`_grep_directory`. It moves to `mdpeek/ops.py`, with functions that take
typed arguments and return `Output(text, notes, truncated)`. The CLI prints
the notes to stderr; the tool appends them as `note:` lines and reports
`truncated` to `after_call`. This is done first, on its own, with the existing
BDD features as the safety net: CLI output must not change.

### Sync and async

The core stays sync. The tool is `async` and runs the work in
`asyncio.to_thread`, because the official SDK's FastMCP (checked on 1.26)
calls a sync tool function directly on the event loop. Parsed documents are
cached per process in a small LRU keyed by `(path, mtime_ns, size)`; URL text
uses the existing cache.

### Errors

`mdpeek.mcp.ToolError(ValueError)` wraps the existing exceptions
(`SectionNotFound`, `TableNotFound`, `SelectionError`, `QueryError`,
`FetchError`, the confinement error) with the CLI's message text.

- `errors="raise"` (default): the exception propagates; FastMCP turns it into
  a result with `isError: true` and the message as text.
- `errors="return"`: the message comes back as text starting `error: `.
  `after_call` still reports `status="error"`.

Unexpected exceptions are never reworded; they propagate.

### Configuration reference (draft)

| Setting | Where | Default | Notes |
|---------|-------|---------|-------|
| `docs_dir` | `Toolset` | none | Confines `source`. Without it, no filesystem access (D-a). |
| `follow_symlinks` | `Toolset` | `True` | Targets must still resolve inside `docs_dir`. |
| `urls`, `url_allow` | `Toolset` | off | Prefix or host patterns; checked on each redirect. |
| `url_headers` | `Toolset` | none | Set by the host, sent only to matching URLs. |
| `allow_private_networks` | `Toolset` | `False` | Refuses loopback, link-local and private addresses. |
| `cache`, `ttl` | `Toolset` | `memory`, 3600 | As `Document.from_url`. |
| `engine` | `Toolset` | `auto` | `sqlite` or `duckdb`, always in safe mode. |
| `sql` | `Toolset` | `True` | `False` removes the `sql` parameter. |
| `tables`, `diagram_summaries` | `Toolset` | CLI defaults | As the Python API. |
| `default_limit`, `max_limit` | `Toolset` | 50, 500 | Rows per table or query result. |
| `max_output_chars` | `Toolset` | 40,000 | Hard cap, with a note. |
| `formats` | `Toolset` | `False` | Expose a `format` parameter. |
| `errors` | `Toolset` | `raise` | Or `return`. |
| `name` | `register` / `tool` | `mdpeek` | The tool's name. |
| `description` | `register` / `tool` | built in | Replace or extend the cheat sheet. |
| `before_call`, `after_call`, `wrap` | `register` / `tool` | none | See [Hooks](#hooks). |

Settings that limit access live on `Toolset`; settings about how the tool
appears live on `register`. One `Toolset` can then be registered twice under
different names, with different hooks.

## Testing

- **BDD features** under `tests/mcp_features/` (the CLI steps collect `tests/features` recursively), written as tool calls and
  their text results ("When the agent calls the tool with ids S2.1"). They
  specify the tool, not the CLI, so they sit apart from the CLI contract; the
  wording stays language-neutral.
- **Safety**: `..`, absolute paths, a symlink out of `docs_dir`, no
  `docs_dir`, a redirect to a disallowed host, a private address, `ATTACH`,
  `VACUUM INTO`, `PRAGMA`, duckdb `read_csv` and `COPY`, a runaway recursive
  CTE, output over the cap.
- **Hooks**: order; `after_call` on success, error, denial and
  `errors="return"`; a raising `after_call` doesn't change the result; a
  context variable set in `before_call` is visible in `after_call`; sync and
  async hooks.
- **Contract tests** that register the tool on a real server and call it
  through an in-memory client session, with the official `mcp` SDK and with
  standalone fastmcp: name, schema, annotations, text-only content, error
  results. A `tests_mcp` nox session runs it per library; the default run checks
  that importing `mdpeek.mcp` pulls in no MCP library.
- **Matrix**: `tests` on 3.10 to 3.15; `tests_mcp` on 3.10 and 3.15.
- **Token budget**: a test caps the size of the serialised `tools/list`
  entry; new `evals/` scenarios measure tool output and are recorded in
  `evals/baseline.json`.

## Documentation

- README: "Use from an MCP server", with the one-line registration, hooks, and
  the configuration table.
- The tool description is the agent's guide for MCP. `Toolset.instructions()`
  returns a short paragraph (under 600 characters) a host can append to its
  server `instructions`.
- `agent_instructions.md` covers the CLI. The MCP tool is a developer feature,
  documented in the README; the agent sees its own description.
- CONTRIBUTING: the ops layer, SQL safe mode, hooks, the `tests_mcp` session
  and the version matrix.

## Delivery order

One commit per step, rebase merged:

1. Python 3.10 support and the 3.10–3.15 matrix.
2. `ops.py` refactor (no behaviour change).
3. SQL safe mode, `docs_dir` confinement, URL allow-list with redirect checks.
4. `mdpeek.mcp`: the tool, registration, hooks, BDD features, contract tests,
   README.

## Options considered

- **A. Framework-neutral toolset with a registration helper.** Chosen. No
  new dependency, and the only option that lets a host keep its own telemetry
  and access control on the tool.
- **B. Standalone `mdpeek mcp` server.** Useful for desktop clients, but an
  existing server cannot add its own hooks to it, and it is a second process
  to deploy. A small add-on to A later if wanted.
- **C. FastMCP-native integration.** Ties mdpeek to MCP SDK versions (1.x
  to 2.x, or fastmcp), with an adapter per framework.
- **Two tools (map and read)** instead of one. Smaller schemas each, and
  separate access by name, but twice the fixed overhead and a choice for the
  agent to make.

## Open questions

1. Without `docs_dir`: no filesystem access (D-a, recommended), or any path
   like the CLI (D-b)?
2. Hooks: `before_call` / `after_call` plus `wrap` (recommended), or `wrap`
   alone, or a single `on_event` observer?

## Implementation notes

What changed between this design and the build:

- **MCP SDK 2.x is out.** `mcp.server.fastmcp` is gone; its successor is
  `mcp.server.mcpserver.MCPServer`, with the same `tool(name=, description=,
  annotations=, structured_output=)` decorator. Standalone fastmcp is at 4.x
  and turns structured output off with `output_schema=None`. `register()`
  checks which of those the server's `tool()` accepts. CI covers mcp 1.x,
  mcp 2.x and fastmcp on Python 3.10 and 3.15.
- **Error messages.** mcp 2.x shows the client only "Error executing tool
  NAME" for an ordinary exception. `register()` re-raises mdpeek's errors and
  refusals as the server library's own `ToolError`, which every library shows
  in full.
- **Annotations.** `ToolAnnotations.model_validate` takes the camelCase names
  in both SDK majors (2.x renamed the attributes to snake_case).
- **Python 3.14+.** `functools.wraps` copies `__annotate__`, not
  `__annotations__`, so the generated tool function defines `__annotate__`
  too; without it a host decorator applied through `wrap` loses the schema
  on fastmcp.
- **No absolute paths.** The directory map is headed `./` and notes and
  errors have the docs directory's path removed, so the server's file layout
  never reaches the agent.
- **SQL row cap.** Safe mode fetches `limit + 1` rows, so a note can say more
  rows exist without counting them all.
- **Short description, `help=True` for detail.** The tool description is
  about 300 characters and ends with "Call with help=True for how it works";
  `help=True` returns the full guide (call forms, ID scheme, rules, limits).
  This follows the convention of the servers it targets, and keeps the
  per-session cost low.
- **Tuned against a benchmark.** Headless agent sessions (Opus, Sonnet,
  Haiku) answered 22 multi-document questions over two private doc libraries
  (30 and 175 files), each graded against an answer key, comparing mdpeek
  with an existing topic-and-search docs tool and with plain Read/Grep/Glob.
  What moved the scores:
  - A description that teaches a way of working (start with `help=True`,
    keep searching after the obvious document) and a `help=True` that lists
    every document with its title and summary. Agents called help in every
    run with it and never without it.
  - Front matter `title`/`summary` (else first heading and first sentence)
    in the map and the list, so files are recognisable by topic.
  - Whole files by path in `ids` (the most common failed call before), grep
    results that show the matching lines, and parameter descriptions in the
    input schema.
  - Result: on the 175-file library mdpeek scored 83–91% across models
    against 79–86% for the topic-and-search tool and 81–86% for
    Read/Grep/Glob, in fewer calls. On the 30-file library all three were
    level. Remaining misses are mostly reasoning (the agent had read the
    document) rather than retrieval.
- **Host text wraps the defaults.** `description_prefix`/`_suffix` and
  `help_prefix`/`_suffix` let a server add its own context without losing
  the generic guidance.
- **Not yet done:** `evals/` scenarios for tool output. The tool reuses the
  CLI's renderers, which the existing scenarios already measure.
