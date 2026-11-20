Feature: Errors and usage

  Scenario: Missing file
    When I run "mdpeek missing.md"
    Then the exit code is 2
    And stderr contains:
      """
      mdpeek: cannot read 'missing.md': No such file or directory
      """

  Scenario: Depth must be at least 1
    Given a markdown file containing:
      """
      # A
      """
    When I run "mdpeek doc.md --depth 0"
    Then the exit code is 2
    And stderr contains:
      """
      must be a whole number of at least 1
      """

  Scenario: An empty document produces no output
    Given a markdown file containing:
      """
      """
    When I run "mdpeek doc.md"
    Then the output is empty
    And the exit code is 0
