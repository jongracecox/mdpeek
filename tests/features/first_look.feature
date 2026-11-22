Feature: First look
  Running mdpeek on a directory or file with no options gives the most useful
  first look that fits in 150 lines, then suggests what to run next. The
  suggestions go to stderr, after the output, so the output itself stays
  clean for pipes.

  Scenario: A directory tree shows each file's summary
    Given the fixture directory "library" as "docs"
    When I run "mdpeek docs -L 1"
    Then the output is:
      """
      docs/ Handbook (9 files, 3 dirs, 37 ln)
        README.md Handbook (2 ln) — Start here.
        guides/ Guides (4 files, 1 dir, 16 ln)
        reference/ (2 files, 8 ln)
        changelog.md Changelog (5 ln, 2 sec) — Fixes.
        notes.md Part one +2 (6 ln, 3 sec) — First.
      """

  Scenario: A summary comes from front matter, else the first sentence
    Given a markdown file "kb/venues.md" containing:
      """
      ---
      title: Venues
      summary: Venue rows and their history.
      ---
      ## Schema
      Venue tables.
      """
    And a markdown file "kb/plain.md" containing:
      """
      # Plain

      Install it first. Then run it.
      """
    When I run "mdpeek kb"
    Then the output contains:
      """
        plain.md Plain (3 ln) — Install it first.
      """
    And the output contains:
      """
        venues.md Venues (6 ln, 1 sec) — Venue rows and their history.
      """

  Scenario: A directory suggests what to run next
    Given the fixture directory "library" as "docs"
    When I run "mdpeek docs"
    Then stderr contains:
      """
      mdpeek: next: mdpeek docs --grep 'term1|term2'  (sections that mention any term, by file)
      mdpeek:       mdpeek docs/guides/deploy.md  (one file)
      mdpeek:       mdpeek docs -d 1 --budget 400  (each file's headings, as far as fits)
      mdpeek:       mdpeek docs --tables  (1 tbl across the files)
      """

  Scenario: A small file is shown whole
    Given a markdown file containing:
      """
      # Guide
      Read this.
      ## Install
      Run it.
      ### Linux
      Use the package.
      """
    When I run "mdpeek doc.md"
    Then the output is:
      """
      [S1] Guide
      Read this.
        [S1.1] Install
      Run it.
          [S1.1.1] Linux
      Use the package.
      """

  Scenario: A long file shows its top-level content and points at the biggest section
    Given the fixture "large/handbook.md" as "handbook.md"
    When I run "mdpeek handbook.md"
    Then the output contains:
      """
      [S1] Introduction
      """
    And stderr contains:
      """
      mdpeek: top-level content shown: the file is 4283 ln, over the 150-line budget
      mdpeek: next: mdpeek handbook.md -s S11  (open a section; add --full for all of it)
      mdpeek:       mdpeek handbook.md --grep 'term1|term2'  (sections that mention any term)
      mdpeek:       mdpeek handbook.md --structure  (the whole outline)
      mdpeek:       mdpeek handbook.md --tables  (6 tbl; then --table ID or --sql)
      """

  Scenario: Asking for a mode turns the first look off
    Given a markdown file containing:
      """
      # Guide
      Read this.
      ## Install
      Run it.
      """
    When I run "mdpeek doc.md -d 1"
    Then the output is:
      """
      [S1] Guide
      Read this.
        [S1.1] Install (1 ln)
      """
