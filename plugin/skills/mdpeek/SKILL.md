---
name: mdpeek
description: Use mdpeek instead of reading a large markdown file whole. Reach for it before opening a markdown file longer than about 150 lines, a markdown or docs URL (README, guide, spec), or a directory of markdown files, and whenever you only need part of a document (one section, a table, a code example, a diagram).
---

# Reading markdown with mdpeek

`mdpeek` shows a markdown document progressively: an outline first, then
only the parts you ask for. Large tables, diagrams and code blocks get IDs
so you can fetch them on their own. Use it to save context on any markdown
that is long, remote, or spread over many files.

## When to use it

- A local `.md` file longer than ~150 lines (check with `wc -l` if unsure).
- A markdown URL: `mdpeek https://…/README.md` fetches and caches it.
- A directory of markdown files: `mdpeek docs/` shows a tree.
- You need one fact, section, table, code example or diagram, not the
  whole document.

For a short file, just read it.

## The basic loop

1. **Outline:** `mdpeek FILE --structure` (add `-d 2` to limit depth).
   Every heading has an ID like `S3.2`, with its line count.
2. **Open what you need:** `mdpeek FILE -s S3.2` (repeat `-s` for several).
   Large tables (`[T4]`), diagrams (`[D1]`) and code blocks (`F` IDs, see
   `--fences`) show up as one-line summaries with IDs.
3. **Drill into one thing:** `--table T4` (schema and first rows),
   `--sql "select … from t4"`, `--diagram D1`, or `--fence F2`.
4. Use `--full -s ID` only for the leaf section you actually need.

IDs come from the document structure, not heading text, and stay stable
between calls. A `(cached …)` line means the content came from mdpeek's
cache; add `--refresh` if it may have changed.

## Full guide

Before your first real use in a session, run:

```sh
mdpeek --agent-instructions
```

It prints the complete, current command guide (tables and SQL, diagrams,
fenced blocks, URLs and caching, directories). If your mdpeek is too old to
have that flag, use `mdpeek --help`.

## If mdpeek isn't installed

Run it without installing: `uvx mdpeek FILE …` (or
`uvx --from 'mdpeek[duckdb]' mdpeek …` for the DuckDB SQL engine). To
install: `uv tool install mdpeek`, `pipx install mdpeek`, or
`brew install jongracecox/tap/mdpeek`.
