# mdpeek

Progressive exposure for markdown. An agent navigates a large markdown file
(or URL) by section and queries its tables, instead of reading the whole
document into context.

## Commands

```sh
uv sync                                 # Install dependencies
uv run mdpeek --version                 # Run locally
uv run pytest                           # Unit, doctest and BDD tests with coverage
uv run nox                              # Tests across Python 3.11–3.14
prek run --all-files                    # ruff, ty and hygiene hooks
uv tool install --force --reinstall .   # Install globally
```

## Conventions

- Test fixtures are synthetic.
- **Python ≥ 3.11.** The only runtime dependency is `markdown-it-py`. DuckDB is
  an optional extra (`mdpeek[duckdb]`) and must be imported lazily.
- **API options are `StrEnum`s** (in `options.py`). Functions accept either the
  enum or its string value; CLI `choices=` are derived from the enums.
- **Section IDs** (`S1`, `S1.3.2`, `S0` for preamble) and **table IDs**
  (`T1..Tn`) are internal and derived only from document structure, never
  from heading text.
- **CLI behaviour is specified in Gherkin** (`tests/features/*.feature`, run by
  pytest-bdd). These files are the contract for a possible future Rust CLI, so
  keep step wording language-neutral.
- **PRs are rebase merged**, so every commit on a branch lands on `main` as-is.
  Keep a branch to a short list of meaningful commits, one per logical change.
  Squash fixups, review tweaks and "fix typo" commits into the commit they belong
  to before merging.
- **Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)**:
  `<type>(<optional scope>): <imperative summary>`. Types: `feat`, `fix`,
  `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`. Use `!` or a
  `BREAKING CHANGE:` footer for breaking changes. Scopes are module names (e.g.
  `feat(tables): …`, `fix(cli): …`).
- Versions come from git tags (`hatch-vcs`); never add a `version` field.
- Releases: see CONTRIBUTING.md.
