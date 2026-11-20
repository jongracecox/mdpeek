Feature: SQL over tables
  Every table that parsed is loaded as t1, t2, ... with inferred column
  types. Scenarios pin the sqlite engine so results never depend on what is
  installed.

  Background:
    Given a markdown file containing:
      """
      # Orders
      | Order ID | Customer | Amount |
      |----------|----------|--------|
      | 1 | ana | 12.5 |
      | 2 | bo | 30 |
      | 3 | ana | 7.5 |

      ## Customers
      | customer | city |
      |----------|------|
      | ana | Lisbon |
      | bo | Oslo |
      """

  Scenario: Aggregate with SQL names
    When I run "mdpeek doc.md --engine sqlite --sql 'select customer, sum(amount) as total from t1 group by customer order by total desc'"
    Then the output is:
      """
      | customer | total |
      |---|---|
      | bo | 30.0 |
      | ana | 20.0 |
      """

  Scenario: Join across tables, as JSON
    When I run "mdpeek doc.md --engine sqlite --format json --sql 'select t1.order_id, t2.city from t1 join t2 using (customer) order by 1'"
    Then the output is:
      """
      {"engine":"sqlite","columns":["order_id","city"],"rows":[[1,"Lisbon"],[2,"Oslo"],[3,"Lisbon"]],"total":3,"shown":3}
      """

  Scenario: Results are limited, with a note on stderr
    When I run "mdpeek doc.md --engine sqlite --limit 1 --sql 'select order_id from t1 order by 1'"
    Then the output is:
      """
      | order_id |
      |---|
      | 1 |
      """
    And stderr contains:
      """
      mdpeek: query: showing 1 of 3 rows (use --limit or --full)
      """

  Scenario: Section scope controls which tables are loaded
    When I run "mdpeek doc.md --engine sqlite -s S1.1 --sql 'select count(*) as n from t2'"
    Then the output is:
      """
      | n |
      |---|
      | 2 |
      """

  Scenario: A table that could not be parsed is skipped
    Given table "T1" cannot be parsed
    When I run "mdpeek doc.md --engine sqlite --sql 'select * from t1'"
    Then the exit code is 2
    And stderr contains:
      """
      mdpeek: skipped T1 (not parsed: simulated parse failure)
      mdpeek: T1 could not be parsed: simulated parse failure
      """

  Scenario Outline: Invalid SQL requests
    When I run "mdpeek doc.md <args>"
    Then the exit code is 2
    And stderr contains:
      """
      <message>
      """

    Examples:
      | args                                         | message                                      |
      | --engine sqlite --sql 'select nope from t1'  | mdpeek: SQL error: no such column: nope      |
      | --engine sqlite --sql 'select 1' --rows 1    | --rows cannot be combined with --sql         |
      | --engine sqlite                              | --engine only applies with --sql             |
      | --sql 'select 1' --table T1                  | not allowed with argument                    |
