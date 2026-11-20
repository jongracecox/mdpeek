Feature: Showing tables on demand
  Table IDs from document output can be opened directly, sliced by rows and
  columns, or listed together.

  Background:
    Given a markdown file containing:
      """
      # Inventory
      | ID | Item Name | Qty | Price |
      |----|-----------|-----|-------|
      | 1 | bolt | 100 | 0.25 |
      | 2 | nut | 250 | 0.1 |
      | 3 | washer | 75 | 0.05 |
      | 4 | screw | 300 | 0.15 |
      | 5 | rivet | 40 | 0.3 |
      | 6 | pin | 60 | 0.2 |
      | 7 | clip | 90 | 0.12 |

      ## Suppliers
      | name | city |
      |------|------|
      | Acme | Springfield |
      """

  Scenario: Opening a table shows its schema and a preview, using SQL names
    When I run "mdpeek doc.md --table T1"
    Then the output is:
      """
      [T1] S1 table 4 cols × 7 rows
      columns: id INTEGER, item_name TEXT, qty INTEGER, price REAL
      | id | item_name | qty | price |
      |---|---|---|---|
      | 1 | bolt | 100 | 0.25 |
      | 2 | nut | 250 | 0.1 |
      | 3 | washer | 75 | 0.05 |
      | 4 | screw | 300 | 0.15 |
      | 5 | rivet | 40 | 0.3 |
      """
    And stderr contains:
      """
      mdpeek: T1: showing 5 of 7 rows (use --rows, --limit or --full)
      """

  Scenario: Full shows every row
    When I run "mdpeek doc.md --table T1 --full --cols id"
    Then the output is:
      """
      [T1] S1 table 4 cols × 7 rows
      columns: id INTEGER
      | id |
      |---|
      | 1 |
      | 2 |
      | 3 |
      | 4 |
      | 5 |
      | 6 |
      | 7 |
      """

  Scenario: Rows and columns by name or original header
    When I run "mdpeek doc.md --table t1 --rows 6- --cols 'item name,price'"
    Then the output is:
      """
      [T1] S1 table 4 cols × 7 rows
      columns: item_name TEXT, price REAL
      | item_name | price |
      |---|---|
      | pin | 0.2 |
      | clip | 0.12 |
      """

  Scenario: The schema flags text columns that are partly numeric
    Given a markdown file containing:
      """
      | value | colour |
      |-------|--------|
      | 1.99 | red |
      | 2.0 | orange |
      | 10 or greater | green |
      """
    When I run "mdpeek doc.md --table T1 --rows 1"
    Then the output contains:
      """
      columns: value TEXT (2/3 numeric), colour TEXT
      """

  Scenario: Listing every table
    When I run "mdpeek doc.md --tables"
    Then the output is:
      """
      [T1] S1 table 4 cols × 7 rows: id, item_name, qty, price
      [T2] S1.1 table 2 cols × 1 row: name, city
      """

  Scenario: Original headers on request
    When I run "mdpeek doc.md --table T1 --rows 1 --raw-column-names"
    Then the output is:
      """
      [T1] S1 table 4 cols × 7 rows
      columns: id INTEGER, item_name TEXT ("Item Name"), qty INTEGER, price REAL
      | ID | Item Name | Qty | Price |
      |---|---|---|---|
      | 1 | bolt | 100 | 0.25 |
      """

  Scenario: Listing with original headers
    When I run "mdpeek doc.md --tables --raw-column-names -s S1"
    Then the output contains:
      """
      [T1] S1 table 4 cols × 7 rows: ID, Item Name, Qty, Price
      """

  Scenario: Listing is scoped by section
    When I run "mdpeek doc.md --tables -s S1.1"
    Then the output is:
      """
      [T2] S1.1 table 2 cols × 1 row: name, city
      """

  Scenario: Several tables in full
    When I run "mdpeek doc.md --table T2 --table T1 --rows 1"
    Then the output is:
      """
      [T2] S1.1 table 2 cols × 1 row
      columns: name TEXT, city TEXT
      | name | city |
      |---|---|
      | Acme | Springfield |

      [T1] S1 table 4 cols × 7 rows
      columns: id INTEGER, item_name TEXT, qty INTEGER, price REAL
      | id | item_name | qty | price |
      |---|---|---|---|
      | 1 | bolt | 100 | 0.25 |
      """

  Scenario Outline: Invalid table requests
    When I run "mdpeek doc.md <args>"
    Then the exit code is 2
    And stderr contains:
      """
      <message>
      """

    Examples:
      | args                     | message                                                  |
      | --table T9               | no table 'T9'; available: T1, T2                         |
      | --table T1 --rows 9-3    | invalid row range '9-3'                                  |
      | --table T1 --cols colour | T1 has no column 'colour'; columns: id, item_name        |
      | --rows 1                 | --rows only applies with --table, --tables or --sql      |
      | --table T1 --structure   | --structure cannot be combined with --table, --tables    |
      | --table T1 -s S1         | --section cannot be combined with --table                |
      | --tables --depth 2       | --depth cannot be combined with --table, --tables        |
