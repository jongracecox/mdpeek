# mdpeek: read large markdown a piece at a time

Use mdpeek instead of reading whole markdown files or URLs: look first, then
open only what you need. `mdpeek SOURCE` (a file, directory, http(s) URL or
`-`) shows what fits in 150 lines; stderr suggests what to run next.

## Navigate

```sh
mdpeek doc.md                       # whole if short; else top level or outline
mdpeek doc.md --structure           # outline: [S2.1] Title (own line count)
mdpeek doc.md -d 1                  # top-level content, next level as stubs
mdpeek doc.md -s S2.1 -s S4         # those sections, subsections as stubs
mdpeek doc.md -s S2 -d 2            # a section plus one level below it
mdpeek doc.md -s S2 --full          # a section and all its subsections
mdpeek doc.md --grep 'retry|limit'  # sections with matching lines (regex)
mdpeek doc.md --meta                # front matter (`[meta] (N)` in output)
```

IDs come from heading position, not text; `S0` precedes the first heading.
Line counts exclude subsections. `ln` lines, `sec` sections, `tbl` tables,
`diag` diagrams; `6×320` is columns × rows. Large tables and diagrams appear
as one-line `[Tn]` / `[Dn]` stubs.

## Tables

```sh
mdpeek doc.md --tables              # [T3] S5.2 6×320: city, ...
mdpeek doc.md --tables -s S5        # only tables in S5
mdpeek doc.md --table T3            # column types and first 5 rows
mdpeek doc.md --table T3 --rows 10-20 --cols city,region
mdpeek doc.md --sql "select region, count(*) from t3 group by 1"
```

Tables load into SQL as `t1`, `t2`, ... (scoped by `-s`). Column names are
shown as their SQL names. Data stops at 50 rows (`--limit N`, `--full`);
`--format csv|tsv|json|jsonl` for machine output.

## Diagrams and code blocks

```sh
mdpeek doc.md --diagrams            # [D1] S3.1 mermaid flowchart "Title" (17 ln)
mdpeek doc.md --diagram D1          # its bare source
mdpeek doc.md --fences              # every block: [F1] S2.2 bash (4 ln)
mdpeek doc.md --fence F1            # its bare source, ready to pipe
mdpeek doc.md --fence F1 --fence F4 # several: each labelled and fenced
```

`T`, `D` and `F` IDs are global: no `-s` with `--table`, `--diagram` or
`--fence`. `--no-diagram-summaries` shows diagrams inline. Diagrams and
fences take `--format json|jsonl`.

## Directories

```sh
mdpeek docs/                        # tree: each file's title and summary, fitted
mdpeek docs/ --budget 400           # a bigger tree
mdpeek docs/ -L 2 -n 5              # fixed: 2 levels, first 5 entries; no budget
mdpeek docs/ -d 1                   # also each file's headings
mdpeek docs/ --grep install         # by file, most matches first
mdpeek docs/ -s guides/install.md#S1.2 -s notes.md   # a section, a whole file
mdpeek docs/ --tables                # by file; also --diagrams, --fences, --meta
mdpeek docs/ --table guides/deploy.md#T1             # also --diagram, --fence
mdpeek docs/ --exclude reference --include '*.md'    # gitignore-style globs
```

Titles and summaries come from front matter, else the first heading and
sentence (`--no-summaries`). `-L` limits levels, `-n` entries; `-L`, `-d`
or `-n` turns the budget off. Address files as `PATH#ID`, relative to the
directory. `--sql` works on one file only.

## URLs

Cached for an hour; cached output starts with `(cached ...)`.
Options: `-H 'Name: value'`, `--refresh`, `--no-cache`, `--ttl SECONDS`.

Notes and errors go to stderr as `mdpeek: ...`; a bad ID or option exits 2.
`mdpeek --help` lists every option.
