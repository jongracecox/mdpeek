Feature: Default view
  The default view shows content down to depth 1 and lists the next level
  of headings as stubs with their line counts.

  Background:
    Given a markdown file containing:
      """
      # Overview
      Intro text.

      ## Goals
      One.
      Two.

      ## Reference
      Ref body.
      ### Details
      Deep.

      # Appendix
      Last.
      """

  Scenario: Top-level sections with stubs for their children
    When I run "mdpeek doc.md"
    Then the output is:
      """
      [S1] Overview
      Intro text.
        [S1.1] Goals (2 ln)
        [S1.2] Reference (1 ln, 1 sub)
      [S2] Appendix
      Last.
      """
    And the exit code is 0

  Scenario: Depth 2 shows the second level and stubs the third
    When I run "mdpeek doc.md --depth 2"
    Then the output is:
      """
      [S1] Overview
      Intro text.
        [S1.1] Goals
      One.
      Two.
        [S1.2] Reference
      Ref body.
          [S1.2.1] Details (1 ln)
      [S2] Appendix
      Last.
      """

  Scenario: Preamble before the first heading is section S0
    Given a markdown file containing:
      """
      Some preamble.

      # Title
      Body.
      """
    When I run "mdpeek doc.md"
    Then the output is:
      """
      [S0]
      Some preamble.
      [S1] Title
      Body.
      """

  Scenario: Markdown heading markers are not repeated in the output
    Given a markdown file containing:
      """
      ## Only level two
      Text.
      """
    When I run "mdpeek doc.md"
    Then the output is:
      """
      [S1] Only level two
      Text.
      """
