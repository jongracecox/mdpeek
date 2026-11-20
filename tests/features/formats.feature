Feature: Output formats for table data

  Background:
    Given a markdown file containing:
      """
      | Name | Score |
      |------|-------|
      | a, b | 1 |
      | c |  |
      """

  Scenario: CSV is plain data with original headers
    When I run "mdpeek doc.md --table T1 --format csv"
    Then the output is:
      """
      Name,Score
      "a, b",1
      c,
      """

  Scenario: TSV
    When I run "mdpeek doc.md --table T1 --format tsv --cols score"
    Then the output is:
      """
      Score
      1
      ""
      """

  Scenario: JSON uses typed values and SQL names
    When I run "mdpeek doc.md --table T1 --format json"
    Then the output is:
      """
      {"id":"T1","section":"S0","columns":["Name","Score"],"names":["name","score"],"types":["TEXT","INTEGER"],"rows":[["a, b",1],["c",null]],"total":2,"shown":2,"warnings":[]}
      """

  Scenario: JSON Lines has one object per row
    When I run "mdpeek doc.md --table T1 --format jsonl"
    Then the output is:
      """
      {"name":"a, b","score":1}
      {"name":"c","score":null}
      """

  Scenario: Table list as JSON
    When I run "mdpeek doc.md --tables --format jsonl"
    Then the output is:
      """
      {"id":"T1","section":"S0","cols":2,"rows":2,"columns":["Name","Score"],"names":["name","score"],"types":["TEXT","INTEGER"],"warnings":[],"error":null}
      """
