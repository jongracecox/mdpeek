Feature: Selecting sections
  --section limits output to the given section IDs. Depth then counts from
  each selected section, which is depth 1.

  Background:
    Given a markdown file containing:
      """
      # 1. Intro / Overview
      Intro.
      ## Setup
      Install it.
      ### Linux
      apt.
      # Usage
      Use it.
      """

  Scenario: One section in the default view
    When I run "mdpeek doc.md -s S1.1"
    Then the output is:
      """
      [S1.1] Setup
      Install it.
        [S1.1.1] Linux (1 ln)
      """

  Scenario: Several sections keep the order they were given
    When I run "mdpeek doc.md -s S2 -s S1.1.1"
    Then the output is:
      """
      [S2] Usage
      Use it.
      [S1.1.1] Linux
      apt.
      """

  Scenario: Section IDs ignore the document's own numbering and slashes
    When I run "mdpeek doc.md --structure -s S1"
    Then the output is:
      """
      [S1] 1. Intro / Overview (1)
        [S1.1] Setup (1)
          [S1.1.1] Linux (1)
      """

  Scenario: IDs are case-insensitive
    When I run "mdpeek doc.md --full -s s1.1"
    Then the output contains:
      """
      [S1.1] Setup
      """

  Scenario: Unknown section suggests nearby IDs
    When I run "mdpeek doc.md -s S1.4"
    Then the exit code is 2
    And the output is empty
    And stderr contains:
      """
      mdpeek: no section 'S1.4'; nearby: S1.1
      """
