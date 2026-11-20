Feature: Grep
  --grep lists the sections with lines matching a regular expression, so an
  agent can find where something is discussed before opening anything.
  Every line counts: headings, text, tables and fenced blocks. Matching is
  case-insensitive unless the pattern has a capital letter.

  Background:
    Given a markdown file containing:
      """
      # Setup
      Install the tool first.
      ## Linux
      Run apt install.
      Then install the plugin.
      ## Notes
      | step | command |
      |---|---|
      | 1 | install |
      """

  Scenario: Matching sections with their counts
    When I run "mdpeek doc.md --grep install"
    Then the output is:
      """
      [S1] Setup (1 match)
      [S1.1] Linux (2 matches)
      [S1.2] Notes (1 match)
      """

  Scenario: A capital letter makes the match case-sensitive
    When I run "mdpeek doc.md --grep Install"
    Then the output is:
      """
      [S1] Setup (1 match)
      """

  Scenario: Headings match too
    When I run "mdpeek doc.md --grep '^## '"
    Then the output is:
      """
      [S1.1] Linux (1 match)
      [S1.2] Notes (1 match)
      """

  Scenario: Section scope limits the search
    When I run "mdpeek doc.md --grep install -s S1.1"
    Then the output is:
      """
      [S1.1] Linux (2 matches)
      """

  Scenario: No matches
    When I run "mdpeek doc.md --grep nothing-here"
    Then the output is empty
    And the exit code is 0
    And stderr contains:
      """
      mdpeek: grep: no matches for 'nothing-here'
      """

  Scenario Outline: Bad grep usage
    When I run "mdpeek doc.md <args>"
    Then the exit code is 2
    And stderr contains:
      """
      mdpeek: <message>
      """

    Examples:
      | args                       | message                                                  |
      | --grep '('                 | invalid --grep pattern '(': missing ), unterminated subpattern |
      | --grep x --structure       | --structure cannot be combined with --grep               |
      | --grep x --table T1        | --table cannot be combined with --grep                   |
      | --grep x -n 2              | --first only applies to a directory                      |
