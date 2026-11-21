Feature: Front matter
  A metadata block at the very top of a file, fenced by "---" (YAML) or "+++"
  (TOML), is front matter. mdpeek recognises it by its fences alone and never
  interprets its keys. Document output shows a one-line "[meta]" marker with
  the block's line count, and "--meta" prints the block itself.

  Background:
    Given a markdown file containing:
      """
      ---
      title: Example
      tags: [a, b]
      ---

      Intro.

      # First
      Body.
      """

  Scenario: Document output shows a marker in place of the block
    When I run "mdpeek doc.md"
    Then the output is:
      """
      [meta] (2)
      [S0]
      Intro.
      [S1] First
      Body.
      """

  Scenario: Structure lists the marker first
    When I run "mdpeek doc.md --structure"
    Then the output is:
      """
      [meta] (2)
      [S0] (1)
      [S1] First (1)
      """

  Scenario: Front matter alone does not make a preamble
    Given a markdown file "bare.md" containing:
      """
      +++
      title = "Example"
      +++

      # First
      Body.
      """
    When I run "mdpeek bare.md --structure"
    Then the output is:
      """
      [meta] (1)
      [S1] First (1)
      """

  Scenario: Section output leaves the marker out
    When I run "mdpeek doc.md -s S1"
    Then the output is:
      """
      [S1] First
      Body.
      """

  Scenario: Printing the block gives its bare contents
    When I run "mdpeek doc.md --meta"
    Then the output is:
      """
      title: Example
      tags: [a, b]
      """

  Scenario: Front matter as JSON
    When I run "mdpeek doc.md --meta --format json"
    Then the output is:
      """
      {"format":"yaml","lines":2,"source":"title: Example\ntags: [a, b]\n"}
      """

  Scenario: A file without front matter
    Given a markdown file "plain.md" containing:
      """
      # First
      Body.
      """
    When I run "mdpeek plain.md --meta"
    Then the exit code is 0
    And the output is empty
    And stderr contains:
      """
      mdpeek: no front matter
      """

  Scenario: An unclosed block is ordinary text
    Given a markdown file "open.md" containing:
      """
      ---
      title: Example

      # First
      """
    When I run "mdpeek open.md --structure"
    Then the output is:
      """
      [S0] (2)
      [S1] First (0)
      """

  Scenario: Front matter of every file in a directory, in tree order
    Given a markdown file "kb/a.md" containing:
      """
      ---
      title: A
      ---
      # A
      """
    And a markdown file "kb/b.md" containing:
      """
      # B
      """
    And a markdown file "kb/sub/c.md" containing:
      """
      +++
      title = "C"
      +++
      """
    When I run "mdpeek kb --meta"
    Then the output is:
      """
      ==> sub/c.md <==
      title = "C"

      ==> a.md <==
      title: A
      """

  Scenario: Directory front matter as JSON lines
    Given a markdown file "kb/a.md" containing:
      """
      ---
      title: A
      ---
      """
    When I run "mdpeek kb --meta --format jsonl"
    Then the output is:
      """
      {"path":"a.md","format":"yaml","lines":1,"source":"title: A\n"}
      """

  Scenario: Directory front matter as JSON
    Given a markdown file "kb/a.md" containing:
      """
      ---
      title: A
      ---
      """
    When I run "mdpeek kb --meta --format json"
    Then the output is:
      """
      [{"path":"a.md","format":"yaml","lines":1,"source":"title: A\n"}]
      """

  Scenario Outline: Invalid directory front matter requests
    Given a markdown file "kb/a.md" containing:
      """
      # A
      """
    When I run "mdpeek kb --meta <args>"
    Then the exit code is 2
    And stderr contains:
      """
      <message>
      """

    Examples:
      | args          | message                                                    |
      | -L 2          | --levels cannot be combined with --meta on a directory     |
      | --structure   | --structure cannot be combined with --meta on a directory  |
      | --format tsv  | --format tsv does not apply to front matter                |

  Scenario Outline: Invalid front matter requests
    When I run "mdpeek doc.md <args>"
    Then the exit code is 2
    And stderr contains:
      """
      <message>
      """

    Examples:
      | args                  | message                                          |
      | --meta -s S1          | --section cannot be combined with --meta         |
      | --meta --structure    | --structure cannot be combined with --meta       |
      | --meta --format csv   | --format csv does not apply to front matter      |
      | --meta --tables       | not allowed with argument                        |
      | --meta --grep x       | --meta cannot be combined with --grep            |
