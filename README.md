# mdpeek

Progressive exposure for markdown: navigate large markdown files by section,
without loading the whole document into context. Built for AI agents, handy
for humans.

> Early development. Table summaries, table queries and URL sources are on
> the way.

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

## Python API

```python
from mdpeek import Document

doc = Document.from_path("guide.md")
print(doc.structure())
print(doc.view(depth=2, sections=["S1.2"]))
section = doc.get("S1.2")  # Section(id, title, level, depth, start, end, ...)
```

## License

MIT
