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

> Early development. URL sources are on the way.

## Install

```sh
uv tool install mdpeek     # or: pipx install mdpeek
```

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

`FILE` can be `-` to read from stdin.

## Tables

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

## Python API

```python
from mdpeek import Document

doc = Document.from_path("guide.md")
print(doc.structure())
print(doc.view(depth=2, sections=["S1.2"]))
section = doc.get("S1.2")  # Section(id, title, level, depth, start, end, ...)

table = doc.table("T4")     # Table(headers, rows, sql_names, types, ...)
table.to_records()          # [{"region": "north", "revenue": 1200.5, ...}, ...]
result = doc.query("select region from t4 where growth > 0.1")  # Engine.AUTO
result.columns, result.rows, result.engine
```

## License

MIT
