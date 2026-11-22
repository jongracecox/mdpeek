Feature: Directories
  Pointing mdpeek at a directory shows its markdown files as a tree. Every
  entry is named by its path, so any of them can be opened with mdpeek.
  Directories show totals of everything below them.

  Background:
    Given the fixture directory "library" as "docs"

  Scenario: One level of the tree
    When I run "mdpeek docs -L 1 --no-summaries"
    Then the output is:
      """
      docs/ Handbook (9 files, 3 dirs, 37 ln)
        README.md Handbook (2 ln)
        guides/ Guides (4 files, 1 dir, 16 ln)
        reference/ (2 files, 8 ln)
        changelog.md Changelog (5 ln, 2 sec)
        notes.md Part one +2 (6 ln, 3 sec)
      """

  Scenario: Levels expand subdirectories
    When I run "mdpeek docs/ --levels 2 --no-summaries"
    Then the output is:
      """
      docs/ Handbook (9 files, 3 dirs, 37 ln)
        README.md Handbook (2 ln)
        guides/ Guides (4 files, 1 dir, 16 ln)
          README.md Guides (2 ln)
          advanced/ (1 file, 2 ln)
          deploy.md Deploy (7 ln, 1 tbl)
          install.md Install (5 ln, 2 sec)
        reference/ (2 files, 8 ln)
          api.md API (6 ln, 3 sec)
          glossary.md (2 ln)
        changelog.md Changelog (5 ln, 2 sec)
        notes.md Part one +2 (6 ln, 3 sec)
      """

  Scenario: First limits the entries shown in each directory
    When I run "mdpeek docs -L 2 -n 2 --no-summaries"
    Then the output is:
      """
      docs/ Handbook (9 files, 3 dirs, 37 ln)
        README.md Handbook (2 ln)
        guides/ Guides (4 files, 1 dir, 16 ln)
          README.md Guides (2 ln)
          advanced/ (1 file, 2 ln)
          … 2 more (2 files, 12 ln)
        … 3 more (1 dir, 2 files, 19 ln)
      """

  Scenario: Opening a subdirectory
    When I run "mdpeek docs/guides --levels 2 --no-summaries"
    Then the output is:
      """
      docs/guides/ Guides (4 files, 1 dir, 16 ln)
        README.md Guides (2 ln)
        advanced/ (1 file, 2 ln)
          tuning.md Tuning (2 ln)
        deploy.md Deploy (7 ln, 1 tbl)
        install.md Install (5 ln, 2 sec)
      """

  Scenario: A file's only top-level heading is its title
    Given a markdown file "notes/one.md" containing:
      """
      Intro before the title.

      # Release notes
      ## Added
      ## Fixed
      """
    When I run "mdpeek notes -L 1 --no-summaries"
    Then the output is:
      """
      notes/ (1 file, 5 ln)
        one.md Release notes (5 ln, 2 sec)
      """

  Scenario: An index file titles its directory
    Given a markdown file "site/index.md" containing:
      """
      # Site
      """
    And a markdown file "site/about.md" containing:
      """
      # About
      """
    When I run "mdpeek site"
    Then the output is:
      """
      site/ Site (2 files, 2 ln)
        index.md Site (1 ln)
        about.md About (1 ln)
      """

  Scenario: Hidden, tool and markdown-free directories are skipped
    Given a markdown file "repo/guide.md" containing:
      """
      # Guide
      """
    And a markdown file "repo/.cache/old.md" containing:
      """
      # Old
      """
    And a markdown file "repo/node_modules/pkg/readme.md" containing:
      """
      # Package
      """
    And a file "repo/src/main.txt" containing:
      """
      not markdown
      """
    When I run "mdpeek repo"
    Then the output is:
      """
      repo/ (1 file, 1 ln)
        guide.md Guide (1 ln)
      """

  Scenario: Exclude skips files and directories by name or path
    When I run "mdpeek docs -L 2 --exclude reference --exclude 'guides/*.md' --no-summaries"
    Then the output is:
      """
      docs/ Handbook (4 files, 2 dirs, 15 ln)
        README.md Handbook (2 ln)
        guides/ (1 file, 1 dir, 2 ln)
          advanced/ (1 file, 2 ln)
        changelog.md Changelog (5 ln, 2 sec)
        notes.md Part one +2 (6 ln, 3 sec)
      """

  Scenario: Include replaces the default markdown patterns
    When I run "mdpeek docs -L 3 --include 'tuning.*' --include '*.txt' --no-summaries"
    Then the output is:
      """
      docs/ (2 files, 3 dirs, 3 ln)
        assets/ (1 file, 1 ln)
          logo.txt (1 ln)
        guides/ (1 file, 1 dir, 2 ln)
          advanced/ (1 file, 2 ln)
            tuning.md Tuning (2 ln)
      """

  Scenario: A directory with no markdown
    Given an empty directory "empty"
    When I run "mdpeek empty"
    Then the output is:
      """
      empty/ (0 files)
      """

  Scenario: File options are rejected for a directory tree
    When I run "mdpeek docs --structure --rows 3"
    Then the exit code is 2
    And stderr contains:
      """
      mdpeek: --rows, --structure only apply to a file; use -s PATH or --table PATH#ID, or run mdpeek on a file in the directory
      """

  Scenario: Directory options are rejected for a file
    When I run "mdpeek docs/notes.md --levels 2"
    Then the exit code is 2
    And stderr contains:
      """
      mdpeek: --levels only applies to a directory
      """

  Scenario: URL options are rejected for a directory
    When I run "mdpeek docs --ttl 5"
    Then the exit code is 2
    And stderr contains:
      """
      mdpeek: --ttl only applies to URL sources
      """

  Scenario: Depth lists each file's headings below its title
    When I run "mdpeek docs -L 2 -d 1 --no-summaries"
    Then the output is:
      """
      docs/ Handbook (9 files, 3 dirs, 37 ln)
        README.md Handbook (2 ln)
        guides/ Guides (4 files, 1 dir, 16 ln)
          README.md Guides (2 ln)
          advanced/ (1 file, 2 ln)
          deploy.md Deploy (7 ln, 1 tbl)
          install.md Install (5 ln, 2 sec)
            [S1.1] Linux (1)
            [S1.2] macOS (1)
        reference/ (2 files, 8 ln)
          api.md API (6 ln, 3 sec)
            [S1.1] List (0)
            [S1.2] Create (0)
            [S1.3] Delete (0)
          glossary.md (2 ln)
        changelog.md Changelog (5 ln, 2 sec)
          [S1.1] 1.1 (1)
          [S1.2] 1.0 (1)
        notes.md Part one +2 (6 ln, 3 sec)
          [S1] Part one (1)
          [S2] Part two (1)
          [S3] Part three (1)
      """

  Scenario: First also limits the sections under each heading
    Given a markdown file "manual/guide.md" containing:
      """
      # Guide
      ## One
      ### One A
      ### One B
      ## Two
      ## Three
      ## Four
      """
    When I run "mdpeek manual -d 2 -n 2 --no-summaries"
    Then the output is:
      """
      manual/ (1 file, 7 ln)
        guide.md Guide (7 ln, 6 sec)
          [S1.1] One (0)
            [S1.1.1] One A (0)
            [S1.1.2] One B (0)
          [S1.2] Two (0)
          … 2 more (2 sec, 2 ln)
      """

  Scenario: Depth stops at the limit and counts the hidden subsections
    Given a markdown file "manual/guide.md" containing:
      """
      # Guide
      ## One
      ### One A
      """
    When I run "mdpeek manual -d 1 --no-summaries"
    Then the output is:
      """
      manual/ (1 file, 3 ln)
        guide.md Guide (3 ln, 2 sec)
          [S1.1] One (0, 1 sub)
      """

  Scenario: Sections from several files in one call
    When I run "mdpeek docs -s guides/install.md#S1.2 -s notes.md -s guides/install.md#s1.1"
    Then the output is:
      """
      ==> guides/install.md <==
      [S1.2] macOS
      Run it too.
      [S1.1] Linux
      Run the installer.

      ==> notes.md <==
      [S1] Part one
      First.
      [S2] Part two
      Second.
      [S3] Part three
      Third.
      """

  Scenario: Fetched sections take the file modes
    When I run "mdpeek docs -s guides/install.md --structure"
    Then the output is:
      """
      ==> guides/install.md <==
      [S1] Install (0)
        [S1.1] Linux (1)
        [S1.2] macOS (1)
      """

  Scenario: A table from a file in the directory
    When I run "mdpeek docs --table guides/deploy.md#T1"
    Then the output is:
      """
      ==> guides/deploy.md <==
      [T1] S1 2×2
      columns: env TEXT, url TEXT
      | env | url |
      |---|---|
      | dev | dev.example |
      | prod | example |
      """

  Scenario: Data formats print the table alone
    When I run "mdpeek docs --table guides/deploy.md#T1 --format csv"
    Then the output is:
      """
      env,url
      dev,dev.example
      prod,example
      """

  Scenario Outline: Bad references on a directory
    When I run "mdpeek docs <args>"
    Then the exit code is 2
    And stderr contains:
      """
      mdpeek: <message>
      """

    Examples:
      | args                                                            | message                                                                   |
      | -s guides/nope.md                                               | no file 'guides/nope.md'; nearby: README.md, deploy.md, install.md        |
      | -s S1                                                           | no file 'S1'; on a directory, name the file: PATH#S1                      |
      | -s guides/install.md#S9                                         | guides/install.md: no section 'S9'; nearby: S1                            |
      | --table guides/deploy.md#T7                                     | guides/deploy.md: no table 'T7'                                           |
      | -s ../outside.md                                                | '../outside.md' is outside the directory                                  |
      | --table guides/deploy.md                                        | --table needs PATH#ID on a directory, got 'guides/deploy.md'              |
      | -s notes.md -L 2                                                | --levels cannot be combined with -s, --table, --diagram or --fence on a directory |
      | --table guides/deploy.md#T1 --table notes.md#T1 --format csv    | --format csv takes tables from one file at a time                         |

  Scenario: The tree counts diagrams
    Given a markdown file "flows/orders.md" containing:
      """
      # Orders
      ## Flow
      ```mermaid
      flowchart LR
          A --> B
      ```
      ## Setup
      ```sh
      make run
      ```
      """
    When I run "mdpeek flows -d 1 --no-summaries"
    Then the output is:
      """
      flows/ (1 file, 10 ln)
        orders.md Orders (10 ln, 2 sec, 1 diag)
          [S1.1] Flow (4, 1 diag)
          [S1.2] Setup (3)
      """

  Scenario: One diagram or fenced block from a directory prints its bare source
    Given a markdown file "flows/orders.md" containing:
      """
      # Orders
      ```mermaid
      flowchart LR
          A --> B
      ```
      ```sh
      make run
      ```
      """
    When I run "mdpeek flows --fence orders.md#F2"
    Then the output is:
      """
      make run
      """

  Scenario: Diagrams from several files are each labelled and fenced
    Given a markdown file "flows/orders.md" containing:
      """
      # Orders
      ```mermaid
      flowchart LR
          A --> B
      ```
      """
    And a markdown file "flows/billing.md" containing:
      """
      # Billing
      ```dot
      digraph G { a -> b }
      ```
      """
    When I run "mdpeek flows --diagram orders.md#D1 --diagram billing.md#d1"
    Then the output is:
      """
      ==> orders.md <==
      [D1] S1 mermaid flowchart (2 ln)
      ```mermaid
      flowchart LR
          A --> B
      ```

      ==> billing.md <==
      [D1] S1 graphviz digraph (1 ln)
      ```dot
      digraph G { a -> b }
      ```
      """

  Scenario Outline: Bad diagram and fence references on a directory
    Given a markdown file "flows/orders.md" containing:
      """
      # Orders
      ```mermaid
      flowchart LR
      ```
      """
    And a markdown file "flows/billing.md" containing:
      """
      # Billing
      ```sh
      make bill
      ```
      """
    When I run "mdpeek flows <args>"
    Then the exit code is 2
    And stderr contains:
      """
      mdpeek: <message>
      """

    Examples:
      | args                                                      | message                                                             |
      | --diagram orders.md#D9                                    | orders.md: no diagram 'D9'; available: D1                           |
      | --fence orders.md                                         | --fence needs PATH#ID on a directory, got 'orders.md'               |
      | --fence orders.md#F1 --fence billing.md#F1 --format json  | --format json takes fenced blocks from one file at a time           |
      | -s orders.md --fences                                     | --fences cannot be combined with -s, --table, --diagram or --fence  |

  Scenario: By default the tree expands as far as fits the budget
    When I run "mdpeek docs --no-summaries"
    Then the output is:
      """
      docs/ Handbook (9 files, 3 dirs, 37 ln)
        README.md Handbook (2 ln)
        guides/ Guides (4 files, 1 dir, 16 ln)
          README.md Guides (2 ln)
          advanced/ (1 file, 2 ln)
            tuning.md Tuning (2 ln)
          deploy.md Deploy (7 ln, 1 tbl)
          install.md Install (5 ln, 2 sec)
            [S1.1] Linux (1)
            [S1.2] macOS (1)
        reference/ (2 files, 8 ln)
          api.md API (6 ln, 3 sec)
            [S1.1] List (0)
            [S1.2] Create (0)
            [S1.3] Delete (0)
          glossary.md (2 ln)
        changelog.md Changelog (5 ln, 2 sec)
          [S1.1] 1.1 (1)
          [S1.2] 1.0 (1)
        notes.md Part one +2 (6 ln, 3 sec)
          [S1] Part one (1)
          [S2] Part two (1)
          [S3] Part three (1)
      """

  Scenario: The budget expands directory levels before headings
    When I run "mdpeek docs --budget 13 --no-summaries"
    Then the output is:
      """
      docs/ Handbook (9 files, 3 dirs, 37 ln)
        README.md Handbook (2 ln)
        guides/ Guides (4 files, 1 dir, 16 ln)
          README.md Guides (2 ln)
          advanced/ (1 file, 2 ln)
            tuning.md Tuning (2 ln)
          deploy.md Deploy (7 ln, 1 tbl)
          install.md Install (5 ln, 2 sec)
        reference/ (2 files, 8 ln)
          api.md API (6 ln, 3 sec)
          glossary.md (2 ln)
        changelog.md Changelog (5 ln, 2 sec)
        notes.md Part one +2 (6 ln, 3 sec)
      """
    And stderr contains:
      """
      mdpeek: tree: showing -L 3 to fit --budget 13; -d 1 is 23 ln
      """

  Scenario: A small budget limits the entries shown
    When I run "mdpeek docs --budget 4 --no-summaries"
    Then the output is:
      """
      docs/ Handbook (9 files, 3 dirs, 37 ln)
        README.md Handbook (2 ln)
        guides/ Guides (4 files, 1 dir, 16 ln)
        … 3 more (1 dir, 2 files, 19 ln)
      """
    And stderr contains:
      """
      mdpeek: tree: showing -L 1 -n 2 to fit --budget 4; -L 2 is 7 ln
      """

  Scenario: Options given with a budget stay fixed
    When I run "mdpeek docs --budget 5 -d 1 --no-summaries"
    Then the output is:
      """
      docs/ Handbook (9 files, 3 dirs, 37 ln)
        README.md Handbook (2 ln)
        guides/ Guides (4 files, 1 dir, 16 ln)
        reference/ (2 files, 8 ln)
        … 2 more (2 files, 11 ln)
      """
    And stderr contains:
      """
      mdpeek: tree: showing -L 1 -d 1 -n 3 to fit --budget 5; -L 2 is 14 ln
      """

  Scenario: When nothing fits, the smallest tree is shown
    When I run "mdpeek docs --budget 2 --no-summaries"
    Then the output is:
      """
      docs/ Handbook (9 files, 3 dirs, 37 ln)
        README.md Handbook (2 ln)
        … 4 more (2 dirs, 2 files, 35 ln)
      """
    And stderr contains:
      """
      mdpeek: tree: -L 1 -n 1 is 3 ln, the smallest tree, over --budget 2
      """

  Scenario: The budget only applies to the tree
    When I run "mdpeek docs -s notes.md --budget 50"
    Then the exit code is 2
    And stderr contains:
      """
      mdpeek: --budget cannot be combined with -s, --table, --diagram or --fence on a directory
      """

  Scenario: Grep across a directory groups sections by file, most matches first
    When I run "mdpeek docs --grep 'run|first'"
    Then the output is:
      """
      docs/ (4 matches in 3 files)
        guides/install.md Install (2 matches)
          [S1.1] Linux (1 match)
          [S1.2] macOS (1 match)
        changelog.md Changelog (1 match)
          [S1.2] 1.0 (1 match)
        notes.md Part one +2 (1 match)
          [S1] Part one (1 match)
      """

  Scenario: First limits the files and the sections in each
    When I run "mdpeek docs --grep 'run|first' -n 1"
    Then the output is:
      """
      docs/ (4 matches in 3 files)
        guides/install.md Install (2 matches)
          [S1.1] Linux (1 match)
          … 1 more (1 sec, 1 match)
        … 2 more (2 files, 2 matches)
      """

  Scenario: Grep results fit the budget
    When I run "mdpeek docs --grep 'run|first' --budget 6"
    Then the output is:
      """
      docs/ (4 matches in 3 files)
        guides/install.md Install (2 matches)
          [S1.1] Linux (1 match)
          … 1 more (1 sec, 1 match)
        … 2 more (2 files, 2 matches)
      """
    And stderr contains:
      """
      mdpeek: grep: showing -n 1 to fit --budget 6 (first N files, first N sections in each)
      """

  Scenario: Grep with no matches in a directory
    When I run "mdpeek docs --grep nothing-here"
    Then the output is:
      """
      docs/ (0 matches)
      """
    And stderr contains:
      """
      mdpeek: grep: no matches for 'nothing-here'
      """

  Scenario: Grep searches only the included files
    When I run "mdpeek docs --grep 'run|first' --exclude guides"
    Then the output is:
      """
      docs/ (2 matches in 2 files)
        changelog.md Changelog (1 match)
          [S1.2] 1.0 (1 match)
        notes.md Part one +2 (1 match)
          [S1] Part one (1 match)
      """

  Scenario Outline: Grep options on a directory
    When I run "mdpeek docs --grep run <args>"
    Then the exit code is 2
    And stderr contains:
      """
      mdpeek: <message>
      """

    Examples:
      | args               | message                                  |
      | -L 2               | --levels cannot be combined with --grep  |
      | -d 1               | --depth cannot be combined with --grep   |
      | -s notes.md        | --section cannot be combined with --grep |

  Scenario: Tables across a directory, grouped by file
    When I run "mdpeek docs --tables"
    Then the output is:
      """
      docs/ (1 tbl in 1 file)
        guides/deploy.md Deploy (1 tbl)
          [T1] S1 2×2: env, url
      """

  Scenario: Listed items as JSON lines carry their path
    When I run "mdpeek docs --tables --format jsonl"
    Then the output is:
      """
      {"path":"guides/deploy.md","id":"T1","section":"S1","cols":2,"rows":2,"columns":["env","url"],"names":["env","url"],"types":["TEXT","TEXT"],"warnings":[],"error":null}
      """

  Scenario: Diagrams and fenced blocks across a directory, in tree order
    Given a markdown file "flows/orders.md" containing:
      """
      # Orders
      ## Flow
      ```mermaid
      flowchart LR
          A --> B
      ```
      ## Setup
      ```sh
      make run
      ```
      """
    And a markdown file "flows/billing.md" containing:
      """
      # Billing
      ```dot
      digraph G { a -> b }
      ```
      """
    When I run "mdpeek flows --fences"
    Then the output is:
      """
      flows/ (3 fences in 2 files)
        billing.md Billing (1 fence)
          [F1] S1 dot (1 ln) = D1
        orders.md Orders (2 fences)
          [F1] S1.1 mermaid (2 ln) = D1
          [F2] S1.2 sh (1 ln)
      """
    When I run "mdpeek flows --diagrams --budget 4"
    Then the output is:
      """
      flows/ (2 diag in 2 files)
        billing.md Billing (1 diag)
          [D1] S1 graphviz digraph (1 ln)
        … 1 more (1 file, 1 diag)
      """
    And stderr contains:
      """
      mdpeek: diagrams: showing -n 1 to fit --budget 4 (first N files, first N diagrams in each)
      """

  Scenario: A directory with nothing to list
    When I run "mdpeek docs --diagrams"
    Then the output is:
      """
      docs/ (0 diag)
      """

  Scenario Outline: Listing options on a directory
    When I run "mdpeek docs <args>"
    Then the exit code is 2
    And stderr contains:
      """
      mdpeek: <message>
      """

    Examples:
      | args                          | message                                                                               |
      | --tables --full               | --full cannot be combined with --tables on a directory; open items with --table PATH#ID |
      | --diagrams -L 2               | --levels cannot be combined with --diagrams on a directory                            |
      | --fences --format csv         | --format csv does not apply to --fences; use md, json or jsonl                        |
      | --tables -n 1 --format json   | --first cannot be combined with --format json                                         |
