Feature: Navigating a large document
  The handbook fixture is several thousand lines long. An agent should be
  able to find answers in it with a handful of small calls.

  Background:
    Given the fixture "large/handbook.md" as "handbook.md"

  Scenario: Top-level outline
    When I run "mdpeek handbook.md --structure -d 1"
    Then the output is:
      """
      [meta] (3)
      [S0] (2)
      [S1] Introduction (17, 3 sub)
      [S2] Getting Started (4, 3 sub)
      [S3] Architecture / Design (4, 4 sub)
      [S4] Configuration (6, 3 sub)
      [S5] Operations (3, 3 sub)
      [S6] Hardware (5, 2 sub)
      [S7] Security (5, 3 sub)
      [S8] Troubleshooting (5, 3 sub)
      [S9] API Reference (5, 2 sub)
      [S10] Field Guide (5, 6 sub)
      [S11] Regional Playbooks (5, 6 sub)
      [S12] Case Studies (4, 6 sub)
      [S13] Release Notes (2, 3 sub)
      [S14] Appendix (5, 1 sub)
      """

  Scenario: Drilling down six levels
    When I run "mdpeek handbook.md --structure -s S9.2.1.1"
    Then the output is:
      """
      [S9.2.1.1] GET /depots/{id} (3)
        [S9.2.1.1.1] Parameters (5)
          [S9.2.1.1.1.1] Query string (3)
          [S9.2.1.1.1.2] Body (5)
      """

  Scenario: A planted fact in a deep section
    When I run "mdpeek handbook.md -s S4.2.1.1 --full"
    Then the output contains:
      """
      The default retry limit is 7 attempts, with an exponential backoff that
      """

  Scenario: The deep table is summarised, then queried
    When I run "mdpeek handbook.md -s S5.2"
    Then the output contains:
      """
      [T3] 6×320: depot_id, city, region, capacity_t, opened, manager
      """
    When I run "mdpeek handbook.md --engine sqlite --sql "select city, capacity_t from t3 where depot_id = 'D-0217'""
    Then the output is:
      """
      | city | capacity_t |
      |---|---|
      | Port Avalon | 4120 |
      """

  Scenario: One cell of the wide table
    When I run "mdpeek handbook.md --table T4 --rows 14 --cols sensor,ch_09"
    Then the output is:
      """
      [T4] S6.2.1 24×40
      columns: sensor TEXT, ch_09 REAL
      | sensor | ch_09 |
      |---|---|
      | S-14 | 0.137 |
      """
