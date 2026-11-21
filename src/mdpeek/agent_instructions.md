# mdpeek: read large markdown a piece at a time

Use mdpeek instead of reading a whole markdown file or URL: get the outline,
then open only the parts you need.
`mdpeek SOURCE [options]`; SOURCE is a file, directory, http(s) URL or `-`.

## Navigate

```sh
mdpeek doc.md --structure           # outline: [S2.1] Title (own line count)
mdpeek doc.md --structure -d 2      # first 2 heading levels only
mdpeek doc.md                       # top-level content, next level as stubs
mdpeek doc.md -s S2.1 -s S4         # those sections, subsections as stubs
mdpeek doc.md -s S2 -d 2            # a section plus one level below it
mdpeek doc.md -s S2 --full          # a section and all its subsections
mdpeek doc.md --grep 'retry|limit'  # sections with matching lines (regex)
mdpeek doc.md --meta                # front matter (`[meta] (N)` in output)
```

IDs come from heading position, never heading text. `S0` is content before
the first heading. Line counts exclude subsections. In content, large tables
and diagrams appear as one-line `[Tn]` / `[Dn]` stubs.

## Tables

```sh
mdpeek doc.md --tables              # [T3] S5.2 table 6 cols × 320 rows: city, ...
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
mdpeek doc.md --diagrams            # [D1] S3.1 mermaid flowchart "Title" (17 lines)
mdpeek doc.md --diagram D1          # its bare source
mdpeek doc.md --fences              # every fenced block: [F1] S2.2 bash (4 lines)
mdpeek doc.md --fence F1            # its bare source, ready to pipe
mdpeek doc.md --fence F1 --fence F4 # several: each labelled and fenced
```

`T`, `D` and `F` IDs are global, so don't add `-s` to `--table`, `--diagram`
or `--fence`. `--no-diagram-summaries` shows diagrams inline. Diagrams and
fences take `--format json|jsonl`, not csv/tsv.

## Directories

```sh
mdpeek docs/                        # tree fitted to 150 lines; stderr says what's next
mdpeek docs/ --budget 400           # a bigger tree
mdpeek docs/ -L 2 -n 5              # fixed: 2 levels, first 5 entries; no budget
mdpeek docs/ -d 1                   # also each file's headings
mdpeek docs/ --grep install         # by file, most matches first
mdpeek docs/ -s guides/install.md#S1.2 -s notes.md   # a section, a whole file
mdpeek docs/ --tables                # every table, by file; also --diagrams, --fences, --meta
mdpeek docs/ --table guides/deploy.md#T1             # also --diagram, --fence
mdpeek docs/ --exclude reference --include '*.md'    # gitignore-style globs
```

Trees show file titles and line/section/table counts. `-L` limits directory
levels, `-n` entries per level; giving `-L`, `-d` or `-n` turns the budget off. Address files as
`PATH#ID`, relative to the directory; IDs are the file's own. `--sql` works
on one file only.

## URLs

Fetched once and cached for an hour; cached output starts with `(cached ...)`.
Options: `-H 'Name: value'`, `--refresh`, `--no-cache`, `--ttl SECONDS`.

Errors and truncation notes go to stderr as `mdpeek: ...`; a bad ID or
option exits 2. `mdpeek --help` lists every option.
