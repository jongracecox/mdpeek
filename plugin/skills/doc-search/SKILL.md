---
name: doc-search
description: Strategy for answering a question from a documentation library (a docs/ directory, wiki export, runbooks, design notes, investigations) where the answer may be spread over several files. Use it when searching a doc store you haven't searched before, when a question needs more than one document, or for "list every reason", "how do I correctly", "what changed" or troubleshooting questions answered from docs.
---

# Searching a documentation library

In a doc library the answer is usually split. The obvious document gives a
plausible part of it; caveats, exceptions, later changes and specific values
live in other files, often in folders you would not think to open
(conventions, investigations, migrations, decisions, glossaries, client or
per-environment pages). Most wrong answers come from stopping after the
obvious document. Work in this order.

## 1. Survey the whole library (one or two calls)

```sh
mdpeek DOCS --budget 500        # every file with its title and size; top sections when they fit
mdpeek DOCS -d 1 --budget 1500  # more heading detail for a small library
```

Read the whole tree before choosing files. Note folders that hold later or
more specific truth: investigations, migrations, changelogs, decisions,
per-client or per-environment pages, glossaries and conventions.

## 2. Shortlist generously

List every file whose title or path could bear on any part of the question,
not just the best match. For "why", "list every" and troubleshooting
questions, err on the side of more.

## 3. Search wide, then narrow

```sh
mdpeek DOCS --grep 'term|synonym|table_name|status_value'   # sections per file, most matches first
```

Put many alternatives in one pattern: the user's words, synonyms, and the
exact table, column, status, flag and client names you have seen so far.
Then use your usual tools (Grep with context, Read) on the files that match.

## 4. Read the shortlisted files properly

Read short and medium files whole. For long files, take the outline
(`mdpeek FILE --structure`) and read every section that could matter
(`mdpeek FILE -s S2 -s S4.1`) rather than one. Facts hide in later sections.

## 5. Chase the split

After the obvious document, grep for the names it mentions (tables, columns,
statuses, clients, ticket or migration IDs) to find caveats and exceptions
elsewhere, and follow its cross-references. Check investigations,
migrations and changelogs for later changes to what a plan or overview says.

## 6. Resolve conflicts explicitly

When documents disagree, prefer the more specific one (a client page over a
general guide) and the more recent one (a migration or investigation over a
plan), and say which you followed and why.

## 7. Check before answering

Go through each part of the question and the file(s) that support it. If a
part rests on a single document, search once more for that topic. Name the
documents you used.

For questions a markdown table answers, query it instead of reading it:
`mdpeek FILE --tables`, then `mdpeek FILE --sql "select … from t1"`.
