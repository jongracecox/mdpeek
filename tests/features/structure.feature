Feature: Structure mode
  Structure mode lists headings only, each with its own line count.

  Background:
    Given a markdown file containing:
      """
      # Overview
      Intro text.
      ## Goals
      One.
      Two.
      ### Stretch
      Maybe.
      # Appendix
      Last.
      """

  Scenario: Full heading tree by default
    When I run "mdpeek doc.md --structure"
    Then the output is:
      """
      [S1] Overview (1)
        [S1.1] Goals (2)
          [S1.1.1] Stretch (1)
      [S2] Appendix (1)
      """

  Scenario: Depth limits the tree and counts the hidden children
    When I run "mdpeek doc.md --structure --depth 1"
    Then the output is:
      """
      [S1] Overview (1, 1 sub)
      [S2] Appendix (1)
      """

  Scenario: Headings inside code fences and quotes are not sections
    Given the fixture "small/nested_headings.md" as "nested.md"
    When I run "mdpeek nested.md --structure"
    Then the output is:
      """
      [S0] (7)
      [S1] Real (1)
      """
