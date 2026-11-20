Feature: Directories
  Pointing mdpeek at a directory shows its markdown files as a tree. Every
  entry is named by its path, so any of them can be opened with mdpeek.
  Directories show totals of everything below them.

  Background:
    Given the fixture directory "library" as "docs"

  Scenario: The top level by default
    When I run "mdpeek docs"
    Then the output is:
      """
      docs/ Handbook (9 files, 3 dirs, 37 lines)
        README.md Handbook (2 lines)
        guides/ Guides (4 files, 1 dir, 16 lines)
        reference/ (2 files, 8 lines)
        changelog.md Changelog (5 lines, 2 sections)
        notes.md Part one +2 (6 lines, 3 sections)
      """

  Scenario: Levels expand subdirectories
    When I run "mdpeek docs/ --levels 2"
    Then the output is:
      """
      docs/ Handbook (9 files, 3 dirs, 37 lines)
        README.md Handbook (2 lines)
        guides/ Guides (4 files, 1 dir, 16 lines)
          README.md Guides (2 lines)
          advanced/ (1 file, 2 lines)
          deploy.md Deploy (7 lines, 1 table)
          install.md Install (5 lines, 2 sections)
        reference/ (2 files, 8 lines)
          api.md API (6 lines, 3 sections)
          glossary.md (2 lines)
        changelog.md Changelog (5 lines, 2 sections)
        notes.md Part one +2 (6 lines, 3 sections)
      """

  Scenario: First limits the entries shown in each directory
    When I run "mdpeek docs -L 2 -n 2"
    Then the output is:
      """
      docs/ Handbook (9 files, 3 dirs, 37 lines)
        README.md Handbook (2 lines)
        guides/ Guides (4 files, 1 dir, 16 lines)
          README.md Guides (2 lines)
          advanced/ (1 file, 2 lines)
          … 2 more (2 files, 12 lines)
        … 3 more (1 dir, 2 files, 19 lines)
      """

  Scenario: Opening a subdirectory
    When I run "mdpeek docs/guides --levels 2"
    Then the output is:
      """
      docs/guides/ Guides (4 files, 1 dir, 16 lines)
        README.md Guides (2 lines)
        advanced/ (1 file, 2 lines)
          tuning.md Tuning (2 lines)
        deploy.md Deploy (7 lines, 1 table)
        install.md Install (5 lines, 2 sections)
      """

  Scenario: A file's only top-level heading is its title
    Given a markdown file "notes/one.md" containing:
      """
      Intro before the title.

      # Release notes
      ## Added
      ## Fixed
      """
    When I run "mdpeek notes"
    Then the output is:
      """
      notes/ (1 file, 5 lines)
        one.md Release notes (5 lines, 2 sections)
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
      site/ Site (2 files, 2 lines)
        index.md Site (1 line)
        about.md About (1 line)
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
      repo/ (1 file, 1 line)
        guide.md Guide (1 line)
      """

  Scenario: Exclude skips files and directories by name or path
    When I run "mdpeek docs -L 2 --exclude reference --exclude 'guides/*.md'"
    Then the output is:
      """
      docs/ Handbook (4 files, 2 dirs, 15 lines)
        README.md Handbook (2 lines)
        guides/ (1 file, 1 dir, 2 lines)
          advanced/ (1 file, 2 lines)
        changelog.md Changelog (5 lines, 2 sections)
        notes.md Part one +2 (6 lines, 3 sections)
      """

  Scenario: Include replaces the default markdown patterns
    When I run "mdpeek docs -L 3 --include 'tuning.*' --include '*.txt'"
    Then the output is:
      """
      docs/ (2 files, 3 dirs, 3 lines)
        assets/ (1 file, 1 line)
          logo.txt (1 line)
        guides/ (1 file, 1 dir, 2 lines)
          advanced/ (1 file, 2 lines)
            tuning.md Tuning (2 lines)
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
    When I run "mdpeek docs -L 2 -d 1"
    Then the output is:
      """
      docs/ Handbook (9 files, 3 dirs, 37 lines)
        README.md Handbook (2 lines)
        guides/ Guides (4 files, 1 dir, 16 lines)
          README.md Guides (2 lines)
          advanced/ (1 file, 2 lines)
          deploy.md Deploy (7 lines, 1 table)
          install.md Install (5 lines, 2 sections)
            [S1.1] Linux (1)
            [S1.2] macOS (1)
        reference/ (2 files, 8 lines)
          api.md API (6 lines, 3 sections)
            [S1.1] List (0)
            [S1.2] Create (0)
            [S1.3] Delete (0)
          glossary.md (2 lines)
        changelog.md Changelog (5 lines, 2 sections)
          [S1.1] 1.1 (1)
          [S1.2] 1.0 (1)
        notes.md Part one +2 (6 lines, 3 sections)
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
    When I run "mdpeek manual -d 2 -n 2"
    Then the output is:
      """
      manual/ (1 file, 7 lines)
        guide.md Guide (7 lines, 6 sections)
          [S1.1] One (0)
            [S1.1.1] One A (0)
            [S1.1.2] One B (0)
          [S1.2] Two (0)
          … 2 more (2 sections, 2 lines)
      """

  Scenario: Depth stops at the limit and counts the hidden subsections
    Given a markdown file "manual/guide.md" containing:
      """
      # Guide
      ## One
      ### One A
      """
    When I run "mdpeek manual -d 1"
    Then the output is:
      """
      manual/ (1 file, 3 lines)
        guide.md Guide (3 lines, 2 sections)
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
      [T1] S1 table 2 cols × 2 rows
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
    When I run "mdpeek flows -d 1"
    Then the output is:
      """
      flows/ (1 file, 10 lines)
        orders.md Orders (10 lines, 2 sections, 1 diagram)
          [S1.1] Flow (4, 1 diagram)
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
      [D1] S1 mermaid flowchart (2 lines)
      ```mermaid
      flowchart LR
          A --> B
      ```

      ==> billing.md <==
      [D1] S1 graphviz digraph (1 line)
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
      | --diagrams                                                | --diagrams only applies to a file                                   |
      | -s orders.md --fences                                     | --fences cannot be combined with -s, --table, --diagram or --fence  |
