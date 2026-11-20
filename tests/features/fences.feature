Feature: Fenced blocks
  Every fenced block has an ID, so a single code example can be pulled
  without reading its whole section. Fences stay inline in document output.

  Background:
    Given a markdown file containing:
      """
      # Setup
      Install:

      ```bash
      pip install example
      ```

      ## Configure
      ```toml
      [tool.example]
      level = 3
      ```

      ```mermaid
      graph TD
          a --> b
      ```

      ```
      plain block
      ```
      """

  Scenario: Listing fenced blocks
    When I run "mdpeek doc.md --fences"
    Then the output is:
      """
      [F1] S1 bash (1 line)
      [F2] S1.1 toml (2 lines)
      [F3] S1.1 mermaid (2 lines) = D1
      [F4] S1.1 plain (1 line)
      """

  Scenario: Pulling one block prints its bare source
    When I run "mdpeek doc.md --fence F2"
    Then the output is:
      """
      [tool.example]
      level = 3
      """

  Scenario: Pulling several blocks labels and fences each
    When I run "mdpeek doc.md --fence F1 --fence F4"
    Then the output is:
      """
      [F1] S1 bash (1 line)
      ```bash
      pip install example
      ```

      [F4] S1.1 plain (1 line)
      ```
      plain block
      ```
      """

  Scenario: Listing is scoped by section, and full shows each block
    When I run "mdpeek doc.md --fences -s S1.1 --full"
    Then the output contains:
      """
      [F4] S1.1 plain (1 line)
      ```
      plain block
      ```
      """

  Scenario: Fences stay inline in document output
    When I run "mdpeek doc.md -s S1 --full -d 1"
    Then the output is:
      """
      [S1] Setup
      Install:

      ```bash
      pip install example
      ```
      """

  Scenario: Fenced block as JSON
    When I run "mdpeek doc.md --fence F1 --format json"
    Then the output is:
      """
      {"id":"F1","section":"S1","language":"bash","lines":1,"diagram":null,"source":"pip install example\n"}
      """

  Scenario Outline: Invalid fence requests
    When I run "mdpeek doc.md <args>"
    Then the exit code is 2
    And stderr contains:
      """
      <message>
      """

    Examples:
      | args                    | message                                       |
      | --fence F9              | no fenced block 'F9'; available: F1, F2, F3, F4 |
      | --fences --format tsv   | --format tsv does not apply to fenced blocks  |
      | --fence F1 -s S1        | --section cannot be combined with --table, --diagram or --fence |
      | --fence F1 --diagram D1 | not allowed with argument                     |
