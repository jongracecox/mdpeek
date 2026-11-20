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

  Scenario: File options are rejected for a directory
    When I run "mdpeek docs --section S1 --structure"
    Then the exit code is 2
    And stderr contains:
      """
      mdpeek: --section, --structure only apply to a file; run mdpeek on a file in 'docs' to use them
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
