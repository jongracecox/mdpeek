Feature: Tables in document output
  Large tables are replaced by a one-line summary with an ID. Small tables
  stay inline under an ID label, so every table can be referenced.

  Background:
    Given a markdown file containing:
      """
      # Data
      Small table:

      | key | value |
      |-----|-------|
      | a | 1 |

      ## Wide
      | c1 | c2 | c3 | c4 | c5 | c6 | c7 |
      |----|----|----|----|----|----|----|
      | 1 | 2 | 3 | 4 | 5 | 6 | 7 |

      ## Deep
      | id | name |
      |----|------|
      | 1 | a |
      | 2 | b |
      | 3 | c |
      | 4 | d |
      | 5 | e |
      | 6 | f |
      | 7 | g |
      | 8 | h |
      | 9 | i |
      | 10 | j |
      | 11 | k |
      """

  Scenario: Wide and deep tables are summarised, small ones stay inline
    When I run "mdpeek doc.md --full"
    Then the output is:
      """
      [S1] Data
      Small table:

      [T1]
      | key | value |
      |-----|-------|
      | a | 1 |
        [S1.1] Wide
      [T2] 7×1
        [S1.2] Deep
      [T3] 2×11: id, name
      """

  Scenario: Inline tables show SQL column names unless raw names are asked for
    Given a markdown file containing:
      """
      | Item Name | Unit Price ($) |
      |:----------|---------------:|
      | bolt | 0.25 |
      """
    When I run "mdpeek doc.md --full"
    Then the output is:
      """
      [S0]
      [T1]
      | item_name | unit_price |
      |:----------|---------------:|
      | bolt | 0.25 |
      """
    When I run "mdpeek doc.md --full --raw-column-names"
    Then the output is:
      """
      [S0]
      [T1]
      | Item Name | Unit Price ($) |
      |:----------|---------------:|
      | bolt | 0.25 |
      """

  Scenario: Stubs and structure lines count tables
    When I run "mdpeek doc.md --structure"
    Then the output is:
      """
      [S1] Data (5, 1 tbl)
        [S1.1] Wide (3, 1 tbl)
        [S1.2] Deep (13, 1 tbl)
      """

  Scenario: A table inside a blockquote is ordinary content
    Given a markdown file containing:
      """
      # Quote
      > | a | b |
      > |---|---|
      > | 1 | 2 |
      """
    When I run "mdpeek doc.md"
    Then the output is:
      """
      [S1] Quote
      > | a | b |
      > |---|---|
      > | 1 | 2 |
      """
