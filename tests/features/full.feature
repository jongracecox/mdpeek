Feature: Full mode
  Full mode shows all content. With a depth, nothing below it is shown.

  Background:
    Given a markdown file containing:
      """
      # Overview
      Intro text.
      ## Goals
      One.
      ### Stretch
      Maybe.
      """

  Scenario: Everything by default
    When I run "mdpeek doc.md --full"
    Then the output is:
      """
      [S1] Overview
      Intro text.
        [S1.1] Goals
      One.
          [S1.1.1] Stretch
      Maybe.
      """

  Scenario: Depth cuts off deeper sections without stubs
    When I run "mdpeek doc.md --full --depth 2"
    Then the output is:
      """
      [S1] Overview
      Intro text.
        [S1.1] Goals
      One.
      """

  Scenario: Structure and full cannot be combined
    When I run "mdpeek doc.md --full --structure"
    Then the exit code is 2
    And stderr contains:
      """
      not allowed with argument
      """
