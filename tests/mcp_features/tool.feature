Feature: The MCP tool
  One general-purpose tool reads a docs directory a piece at a time. Called
  with no arguments it shows the map; ids fetch sections, tables, diagrams
  and code blocks; show lists them; grep searches; sql queries a file's
  tables. Arguments are given as JSON, as an MCP client sends them.

  Background:
    Given a docs directory from the fixture "library"

  Scenario: Help explains how to call the tool
    When the agent calls the tool with {"help": true}
    Then the result starts with:
      """
      # mdpeek: read the docs directory a piece at a time
      """

  Scenario: No arguments show the map of the docs directory
    When the agent calls the tool with {}
    Then the result starts with:
      """
      ./ Handbook (9 files, 3 dirs, 37 ln)
        README.md Handbook (2 ln)
        guides/ Guides (4 files, 1 dir, 16 ln)
      """

  Scenario: A source file alone shows its outline
    When the agent calls the tool with {"source": "guides/install.md"}
    Then the result is:
      """
      [S1] Install (0)
        [S1.1] Linux (1)
        [S1.2] macOS (1)
      """

  Scenario: Full on a source file shows the whole file
    When the agent calls the tool with {"source": "guides/install.md", "full": true}
    Then the result is:
      """
      [S1] Install
        [S1.1] Linux
      Run the installer.
        [S1.2] macOS
      Run it too.
      """

  Scenario: IDs fetch items from several files, each labelled
    When the agent calls the tool with {"ids": ["guides/install.md#S1.1", "guides/deploy.md#T1"]}
    Then the result is:
      """
      ==> guides/install.md <==
      [S1.1] Linux
      Run the installer.

      ==> guides/deploy.md <==
      [T1] S1 2×2
      columns: env TEXT, url TEXT
      | env | url |
      |---|---|
      | dev | dev.example |
      | prod | example |
      """

  Scenario: Grep finds the sections that mention a topic
    When the agent calls the tool with {"grep": "install"}
    Then the result is:
      """
      ./ (2 matches in 1 file)
        guides/install.md Install (2 matches)
          [S1] Install (1 match)
          [S1.1] Linux (1 match)
      """

  Scenario: Show lists the tables across the directory
    When the agent calls the tool with {"show": "tables"}
    Then the result is:
      """
      ./ (1 tbl in 1 file)
        guides/deploy.md Deploy (1 tbl)
          [T1] S1 2×2: env, url
      """

  Scenario: SQL answers a question from a file's tables
    When the agent calls the tool with {"source": "guides/deploy.md", "sql": "select env from t1 order by env desc"}
    Then the result is:
      """
      | env |
      |---|
      | prod |
      | dev |
      """

  Scenario: A row limit says that more rows are available
    When the agent calls the tool with {"source": "guides/deploy.md", "sql": "select * from t1", "limit": 1}
    Then the result ends with the note "query: showing the first 1 rows; raise limit (up to 500) or refine the query"

  Scenario: Missing items are reported as notes, not errors
    When the agent calls the tool with {"ids": ["notes.md#S2", "notes.md#meta"]}
    Then the result is:
      """
      ==> notes.md <==
      [S2] Part two
      Second.
      note: notes.md: no front matter
      """
