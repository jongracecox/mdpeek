Feature: Malformed tables
  Fixable problems are repaired and reported. A table that cannot be parsed
  keeps its ID, and --on-table-error decides how it is shown.

  Scenario: Ragged rows are fixed and reported
    Given a markdown file containing:
      """
      | a | b |
      |---|---|
      | 1 |
      | 1 | 2 | 3 |
      """
    When I run "mdpeek doc.md --tables"
    Then the output is:
      """
      [T1] S0 2×2: a, b (2 ragged rows fixed)
      """

  Scenario: Text without a delimiter row is not a table
    Given a markdown file containing:
      """
      a | b
      1 | 2
      """
    When I run "mdpeek doc.md --tables"
    Then the output is empty
    And the exit code is 0

  Scenario Outline: A table that cannot be parsed
    Given a markdown file containing:
      """
      # Data
      Before.

      | a | b |
      |---|---|
      | 1 | 2 |

      After.
      """
    And table "T1" cannot be parsed
    When I run "mdpeek doc.md --full --on-table-error <policy>"
    Then the output is:
      """
      <output>
      """

    Examples:
      | policy  | output                                                                                                   |
      | show    | [S1] Data\nBefore.\n\n[T1!] not parsed: simulated parse failure, raw text below\n\| a \| b \|\n\|---\|---\|\n\| 1 \| 2 \|\n\nAfter. |
      | summary | [S1] Data\nBefore.\n\n[T1!] not parsed: simulated parse failure\n\nAfter.                            |
      | exclude | [S1] Data\nBefore.\n\n\nAfter.                                                                            |

  Scenario: Opening a table that cannot be parsed shows the raw text
    Given a markdown file containing:
      """
      | a | b |
      |---|---|
      | 1 | 2 |
      """
    And table "T1" cannot be parsed
    When I run "mdpeek doc.md --table T1"
    Then the output is:
      """
      [T1!] S0 not parsed: simulated parse failure
      | a | b |
      |---|---|
      | 1 | 2 |
      """
