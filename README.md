# mdpeek

[![pypi package](https://badge.fury.io/py/mdpeek.svg)](https://pypi.org/project/mdpeek)
[![release](https://github.com/jongracecox/mdpeek/actions/workflows/release.yml/badge.svg)](https://github.com/jongracecox/mdpeek/actions/workflows/release.yml)
[![GitHub last commit](https://img.shields.io/github/last-commit/jongracecox/mdpeek.svg)](https://github.com/jongracecox/mdpeek/commits/main)
[![GitHub](https://img.shields.io/github/license/jongracecox/mdpeek.svg)](https://github.com/jongracecox/mdpeek/blob/main/LICENSE)
[![downloads](https://pepy.tech/badge/mdpeek)](https://pepy.tech/project/mdpeek)
[![tests](https://github.com/jongracecox/mdpeek/actions/workflows/tests.yml/badge.svg)](https://github.com/jongracecox/mdpeek/actions/workflows/tests.yml)
![coverage](https://raw.githubusercontent.com/jongracecox/mdpeek/badges/coverage.svg)
[![GitHub stars](https://img.shields.io/github/stars/jongracecox/mdpeek.svg?style=social)](https://github.com/jongracecox/mdpeek/stargazers)

[![buymeacoffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/jongracecox)

Progressive exposure for markdown: navigate large markdown files by section,
without loading the whole document into context. Built for AI agents, handy
for humans.

> Early development.

## How much does it save?

On a 4,000-line synthetic handbook (~59k tokens if read whole), answering
seven typical questions with mdpeek took 0.2–1.1% of the tokens of reading
the file. See [evals/report.md](evals/report.md) for the scenarios.

## Install

```sh
uv tool install mdpeek             # or: pipx install mdpeek
brew install jongracecox/tap/mdpeek
```

The `duckdb` extra, for table queries, is only available with `uv` or `pipx`:
`uv tool install 'mdpeek[duckdb]'`.

## Usage

Start with the outline, then open only the sections you need:

```console
$ mdpeek guide.md --structure
[S1] Overview (3)
  [S1.1] Goals (5)
  [S1.2] Reference (40)
    [S1.2.1] API (18)
[S2] Appendix (2)

$ mdpeek guide.md -s S1.2
[S1.2] Reference
Reference intro...
  [S1.2.1] API (18 lines)
```

- Section IDs (`S1`, `S1.2.1`) come from the heading structure only, never
  from heading text, so they are unambiguous even when headings repeat or
  carry their own numbering. Content before the first heading is `S0`.
- Line counts are each section's own lines, excluding subsections.

| Command | Shows |
|---|---|
| `mdpeek FILE` | top-level content, with the next level as stubs |
| `mdpeek FILE -d N` | content down to depth N, stubs for depth N+1 |
| `mdpeek FILE --structure [-d N]` | headings and line counts only |
| `mdpeek FILE --full [-d N]` | all content (down to depth N) |
| `mdpeek FILE -s ID [-s ID ...]` | only those sections; depth counts from each |

`FILE` can be `-` to read from stdin, or an `http(s)://` URL.

For AI agents, `mdpeek --agent-instructions` prints a compact guide to every
feature (about 800 tokens). Point an agent at it from your `CLAUDE.md` or
`AGENTS.md`:

```markdown
Read large markdown files with mdpeek. Run `mdpeek --agent-instructions` first.
```

## Diagrams

Mermaid, PlantUML (`plantuml`/`puml`), Graphviz (`dot`/`graphviz`) and D2
fences are replaced by one line in document output; diagram source is rarely
worth reading inline and is mostly styling.

````console
$ mdpeek README.md -s S1.6.2
[S1.6.2] Thresholds
...
[D1] mermaid flowchart (19 lines)

$ mdpeek README.md --diagram D1
flowchart LR
    A([badge value]) --> B{"value < 2?"}
    ...
````

| Command | Shows |
|---|---|
| `--diagram ID` | the diagram's bare source, ready to pipe into a renderer; several IDs are each labelled and fenced |
| `--diagrams` | one summary line per diagram (scoped by `-s`); add `--full` for every source |
| `--no-diagram-summaries` | show diagrams inline in document output (under a `[Dn]` label) |

The summary gives the language, the diagram type where it's stated
(`flowchart`, `sequenceDiagram`, `digraph`, ...), its title if it has one,
and its line count. `--format json|jsonl` works for diagram output too.

## Fenced blocks

Every fenced block gets an ID (`F1`, `F2`, ...), so you can pull one code
example without reading its whole section. Fences stay inline in document
output; this is an inventory and a shortcut.

```console
$ mdpeek README.md --fences
[F1] S1.3.1 bash (1 line)
[F2] S1.3.2 python (11 lines)
[F7] S1.6.2 mermaid (19 lines) = D1
...
$ mdpeek README.md --fences | grep python     # filter with the usual tools
$ mdpeek README.md --fence F1 | sh               # one block: just the source
```

| Command | Shows |
|---|---|
| `--fence ID` | the block's bare source, ready to pipe on; several IDs are each labelled and fenced |
| `--fences` | section, language and line count per block (scoped by `-s`); `--full` shows each |

A fence with no language is listed as `plain`; a diagram fence also shows
its diagram ID (`= D1`). `--format json|jsonl` works here too.

## Front matter

A metadata block fenced at the very top of a file, by `---` (YAML) or `+++`
(TOML), is front matter. mdpeek recognises it by its fences only: there is
no standard set of keys, so it never reads `title` or anything else from it.
Document output shows a one-line marker with its line count in its place,
and `--meta` prints the block.

```console
$ mdpeek guide.md --structure
[meta] (3)
[S1] Guide (4)
$ mdpeek guide.md --meta
title: Guide
tags: [setup]
owner: docs
$ mdpeek docs/ --meta                # every file's, each under ==> PATH <==
```

`S0` is content after the front matter, so a file with front matter and no
preamble has no `S0`. `--format json|jsonl` gives
`{"format": "yaml", "lines": 3, "source": "..."}` (with `"path"` on a
directory). An unclosed block is ordinary text.

## URLs and caching

```console
$ mdpeek https://example.com/docs/guide.md --structure
[S1] Guide (4)
  ...
$ mdpeek https://example.com/docs/guide.md -s S1.2
(cached 2026-11-20 15:04Z)
[S1.2] Configuration
...
```

A URL is fetched once and cached on disk, so repeated calls on the same
document don't download it again. Output that came from the cache starts
with a `(cached …)` line giving the fetch time (for csv/tsv/json output it
goes to stderr, so the data stays parseable).

| Option | Effect |
|---|---|
| `-H 'Name: value'` | send a request header (repeatable); cached separately per header set, and header values are never written to the cache |
| `--ttl SECONDS` | reuse a cached copy younger than this (default 3600) |
| `--refresh` | fetch again and update the cache |
| `--no-cache` | neither read nor write the cache |
| `--timeout SECONDS` | network timeout (default 30) |

The cache lives in `$MDPEEK_CACHE_DIR`, else `$XDG_CACHE_HOME/mdpeek`, else
`~/.cache/mdpeek`, readable only by you. Requests identify as
`mdpeek/<version>`.

## Directories

Point mdpeek at a directory to see its markdown files as a tree. Every entry
is named by its path, so you open anything you see by pointing mdpeek at it.

```console
$ mdpeek docs/ -L 1
docs/ Handbook (9 files, 3 dirs, 37 lines)
  README.md Handbook (2 lines)
  guides/ Guides (4 files, 1 dir, 16 lines)
  reference/ (2 files, 8 lines)
  changelog.md Changelog (5 lines, 2 sections)
  notes.md Part one +2 (6 lines, 3 sections)

$ mdpeek docs/ -L 2 -n 2
docs/ Handbook (9 files, 3 dirs, 37 lines)
  README.md Handbook (2 lines)
  guides/ Guides (4 files, 1 dir, 16 lines)
    README.md Guides (2 lines)
    advanced/ (1 file, 2 lines)
    … 2 more (2 files, 12 lines)
  … 3 more (1 dir, 2 files, 19 lines)

$ mdpeek docs/guides -d 1
docs/guides/ Guides (4 files, 1 dir, 16 lines)
  README.md Guides (2 lines)
  advanced/ (1 file, 2 lines)
  deploy.md Deploy (7 lines, 1 table)
  install.md Install (5 lines, 2 sections)
    [S1.1] Linux (1)
    [S1.2] macOS (1)

$ mdpeek docs/ -s guides/install.md#S1.2 -s notes.md#S2
==> guides/install.md <==
[S1.2] macOS
Run it too.

==> notes.md <==
[S2] Part two
Second.
```

| Command | Shows |
|---|---|
| `mdpeek DIR` | as much of the tree as fits in 150 lines (see **Budget**) |
| `mdpeek DIR --budget LINES` | as much as fits in LINES; any `-L`, `-d` or `-n` given stays fixed |
| `mdpeek DIR -L N` | N directory levels expanded, subdirectories below collapsed to totals |
| `mdpeek DIR -d N` | each listed file's headings, N levels below its title |
| `mdpeek DIR -n N` | the first N entries of each directory and sections under each heading, then a `… K more` line |
| `mdpeek DIR -s PATH[#ID] ...` | whole files or sections from several files, each under `==> PATH <==`; `--structure`, `--full` and `-d` work as for a file |
| `mdpeek DIR --table PATH#ID ...` | tables from files in the directory; `--format` other than `md` takes one file at a time |
| `mdpeek DIR --tables`, `--diagrams`, `--fences` | every item's summary line, grouped by file |
| `mdpeek DIR --diagram PATH#ID ...`, `--fence PATH#ID ...` | diagrams or fenced blocks; one prints its bare source, several are each labelled under `==> PATH <==` |
| `mdpeek DIR --meta` | every file's front matter, each under `==> PATH <==`, in tree order |
| `--include GLOB` | list these files instead of `*.md` and `*.markdown`; repeatable |
| `--exclude GLOB` | skip matching files and directories; repeatable |

- **Budget:** with no `-L`, `-d` or `-n`, mdpeek expands directory levels
  until the next one would go over the budget (150 lines by default), then
  adds heading levels once every directory is shown. If even the top level
  is too long, it shows the first N entries that fit. A note on stderr says
  what it chose and what the next step would cost, e.g.
  `mdpeek: tree: showing -L 2 to fit --budget 150; -L 3 is 161 lines`.
  Giving `-L`, `-d` or `-n` without `--budget` turns the budget off.
- **Titles:** a file is labelled with its only top-level heading, or the
  first of several with `+N` for the rest. A directory takes its title from
  its `README.md` (or `index.md`), which is listed first.
- **Totals:** directories count every file, subdirectory and line below
  them, so the bulk of a large library is visible before you open it.
  A file's `sections` don't count its title.
- **Headings** with `-d` start below a file's title, so `-d 1` shows a
  single-title file's `##` sections. A file with several top-level headings
  lists those instead. Section IDs are the file's own, so `PATH#S1.2` from
  the tree is `mdpeek PATH -s S1.2`.
- **Paths** in `-s`, `--table`, `--diagram` and `--fence` are relative to the
  directory and must stay inside it.
- **Lists:** `--tables`, `--diagrams` and `--fences` list every item in the
  directory, grouped by file in tree order, and fit the budget the way
  `--grep` does. With `--format json` or `jsonl`, each item gains a `path`
  field and nothing is cut. `--sql` works on one file only.
- **Order:** the README, then subdirectories, then files, alphabetically.
- **Skipped:** hidden entries, `node_modules`, `__pycache__`, symlinked
  directories, and directories with no matching files.
- **Globs** match an entry's name or its path relative to the directory,
  gitignore-style: `*` stays within one directory and `**` crosses them
  (`guides/**/*.md`).

## Search

`--grep PATTERN` lists the sections with lines matching a regular
expression, so you can find where something is discussed before opening it.

```console
$ mdpeek guide.md --grep 'retry|timeout'
[S4.2] Network (3 matches)
[S4.2.1] Retries (5 matches)

$ mdpeek docs/ --grep 'run|first'
docs/ (4 matches in 3 files)
  guides/install.md Install (2 matches)
    [S1.1] Linux (1 match)
    [S1.2] macOS (1 match)
  changelog.md Changelog (1 match)
    [S1.2] 1.0 (1 match)
  notes.md Part one +2 (1 match)
    [S1] Part one (1 match)
```

- **Smart case:** matching ignores case unless the pattern has a capital
  letter.
- **Every line is searched:** headings, text, tables and fenced blocks. A
  line counts for the innermost section around it.
- **On a file,** `-s ID` limits the search to those sections.
- **On a directory,** files are grouped with the most matches first, and
  `--include` / `--exclude` choose the files. Results fit the line budget
  (150 by default): mdpeek picks the largest `-n` (first N files, and first N
  sections in each) that fits, and says so on stderr. `-n N` sets it
  yourself, and `--budget LINES` changes the budget.


Large tables cost a lot of context, so document output replaces them with a
one-line summary and an ID. Small tables stay inline under their ID.

```console
$ mdpeek report.md -s S2
[S2] Results
[T3] table 12 cols × 480 rows
[T4] table 3 cols × 20 rows: region, revenue, growth

$ mdpeek report.md --table T4 --rows 1-3
[T4] S2 table 3 cols × 20 rows
columns: region TEXT, revenue REAL, growth REAL
| region | revenue | growth |
|---|---|---|
| north | 1200.5 | 0.04 |
| south | 980 | 0.11 |
| east | 1430.25 | -0.02 |

$ mdpeek report.md --sql "select region from t4 where growth > 0.1"
| region |
|---|
| south |
```

| Command | Shows |
|---|---|
| `--table ID` | column names and types, and the first 5 rows; repeatable |
| `--table ID --full` | every row |
| `--table ID --rows 10-30 --cols a,b` | a slice; columns by name (original headers also accepted) |
| `--tables` | one summary line per table (scoped by `-s`); add `--full`/`--rows`/`--cols` to show each |
| `--sql QUERY` | SQL over every table (scoped by `-s`), loaded as `t1`, `t2`, … |
| `--format md\|csv\|tsv\|json\|jsonl` | output format for table data (default `md`) |
| `--limit N` | maximum rows shown (default 50) |

- **Summaries** replace tables wider than 6 columns or longer than 10 rows.
  Column names are listed only when they fit in 80 characters. Tune with
  `--table-max-cols`, `--table-max-rows`, `--table-header-max-chars`, or turn
  summaries off with `--no-table-summaries`.
- **Column names** are shown as their SQL names everywhere (summaries,
  inline tables, `--table` output), so what you see is what you query.
  Headers are lowercased, accents become plain ASCII, and every other run of
  non-alphanumeric characters becomes `_` (`Unit Price ($)` → `unit_price`,
  `Café / Bar` → `cafe_bar`). A leading digit gets a `c_` prefix, an empty
  header becomes `col_N`, and duplicates get `_2`, `_3`, …
  `--raw-column-names` shows the original headers instead (and adds them to
  the `--table` schema line).
- **Types** are inferred per column: INTEGER, REAL or TEXT; empty cells are
  NULL. A column is numeric only if every value is, so `1.99, 2.0, 10 or
  greater` is TEXT. The schema line flags such columns
  (`value TEXT (2/3 numeric)`), and a query that compares them with numbers
  fails with a hint to cast, e.g. `try_cast(value AS DOUBLE)` in DuckDB.
  sqlite doesn't fail on such comparisons, so mdpeek prints a note instead.
- **Quoted names:** using an original header in SQL (`select "Order ID" …`)
  is an error with a hint naming the column to use, never a silent string
  literal (sqlite's legacy behaviour).
- **SQL engines:** sqlite (built in) or DuckDB (`uv tool install 'mdpeek[duckdb]'`
  or `pip install 'mdpeek[duckdb]'`).
  The default `--engine auto` uses DuckDB when it is installed; set
  `MDPEEK_ENGINE=sqlite|duckdb` to choose a default.
- **Malformed tables:** ragged rows and bad characters are fixed and noted in
  the summary. A table that cannot be parsed keeps its ID (`[T3!]`), and
  `--on-table-error show|summary|exclude` controls how it appears.

## Claude Code plugin

This repository is also a Claude Code plugin marketplace. The plugin adds a
skill that tells Claude to use mdpeek on large markdown files, docs URLs and
markdown directories instead of reading them whole:

```text
/plugin marketplace add jongracecox/mdpeek
/plugin install mdpeek@mdpeek
```

The skill needs `mdpeek` on your `PATH` (any install method above), or falls
back to `uvx mdpeek`.

## Python API

```python
from mdpeek import Document

doc = Document.from_path("guide.md")
# or: Document.from_url(url, headers={...}, cache="memory" | "disk" | None, ttl=3600)
print(doc.structure())
print(doc.view(depth=2, sections=["S1.2"]))
section = doc.get("S1.2")  # Section(id, title, level, depth, start, end, ...)

table = doc.table("T4")     # Table(headers, rows, sql_names, types, ...)
table.to_records()          # [{"region": "north", "revenue": 1200.5, ...}, ...]
result = doc.query("select region from t4 where growth > 0.1")  # Engine.AUTO
result.columns, result.rows, result.engine

from mdpeek import Library

library = Library.from_path("docs/", exclude=["drafts"])
print(library.tree(levels=2, first=10, depth=1))
fit = library.fit(budget=150)  # TreeFit(levels, depth, first, lines, next_step, ...)
print(library.tree(levels=fit.levels, depth=fit.depth or None, first=fit.first))

from mdpeek.search import compile_pattern, section_hits

hits = section_hits(doc, compile_pattern("retry|timeout"))  # [(Section, count), ...]
print(library.grep(compile_pattern("install"), budget=150).text)
```

## License

MIT
