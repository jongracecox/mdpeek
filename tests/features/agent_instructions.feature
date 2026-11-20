Feature: Agent instructions
  Agents can ask mdpeek how to use it, without a document.

  Scenario: Print the agent guide
    When I run "mdpeek --agent-instructions"
    Then the exit code is 0
    And the output contains:
      """
      # mdpeek: read large markdown a piece at a time
      """
    And the output contains:
      """
      mdpeek doc.md --structure
      """

  Scenario: The agent guide ignores a source
    Given a markdown file containing:
      """
      # A
      """
    When I run "mdpeek doc.md --agent-instructions"
    Then the exit code is 0
    And the output contains:
      """
      mdpeek doc.md --sql
      """
