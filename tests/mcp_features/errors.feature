Feature: How the MCP tool reports problems
  A bad call fails with a message that names the fix. A server can instead
  have problems returned as text that starts with "error:".

  Background:
    Given a docs directory from the fixture "library"

  Scenario: An unknown section suggests nearby IDs
    When the agent calls the tool with {"ids": ["guides/install.md#S9"]}
    Then the call fails with a message containing "no section 'S9'"

  Scenario: Only one of ids, show, grep and sql picks the action
    When the agent calls the tool with {"grep": "a", "sql": "select 1"}
    Then the call fails with a message containing "pass only one of grep, sql"

  Scenario: In a directory, IDs name their file
    When the agent calls the tool with {"ids": ["S1"]}
    Then the call fails with a message containing "name the file: PATH#ID"

  Scenario: Problems can be returned as text
    Given the tool is configured to return errors as text
    When the agent calls the tool with {"ids": ["guides/install.md#S9"]}
    Then the result starts with:
      """
      error: no section 'S9'
      """
