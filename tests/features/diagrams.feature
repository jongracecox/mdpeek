Feature: Diagrams
  Mermaid, PlantUML, Graphviz and D2 diagrams are replaced by one summary
  line in document output, and can be opened by ID.

  Background:
    Given a markdown file containing:
      """
      # Flow
      How orders move:

      ```mermaid
      flowchart LR
          A[order] --> B{paid?}
          B -- yes --> C[ship]
          B -- no --> D[hold]
      ```

      Then they ship.

      ## Graph
      ```dot
      digraph G { a -> b }
      ```
      """

  Scenario: Diagrams are summarised in document output
    When I run "mdpeek doc.md --full"
    Then the output is:
      """
      [S1] Flow
      How orders move:

      [D1] mermaid flowchart (4 lines)

      Then they ship.
        [S1.1] Graph
      [D2] graphviz digraph (1 line)
      """

  Scenario: Stubs and structure count diagrams
    When I run "mdpeek doc.md --structure"
    Then the output is:
      """
      [S1] Flow (10, 1 diagram)
        [S1.1] Graph (3, 1 diagram)
      """

  Scenario: Opening one diagram prints its bare source
    When I run "mdpeek doc.md --diagram D1"
    Then the output is:
      """
      flowchart LR
          A[order] --> B{paid?}
          B -- yes --> C[ship]
          B -- no --> D[hold]
      """

  Scenario: Several diagrams are labelled and fenced
    When I run "mdpeek doc.md --diagram D2 --diagram D1"
    Then the output is:
      """
      [D2] S1.1 graphviz digraph (1 line)
      ```dot
      digraph G { a -> b }
      ```

      [D1] S1 mermaid flowchart (4 lines)
      ```mermaid
      flowchart LR
          A[order] --> B{paid?}
          B -- yes --> C[ship]
          B -- no --> D[hold]
      ```
      """

  Scenario: Listing diagrams, scoped by section
    When I run "mdpeek doc.md --diagrams"
    Then the output is:
      """
      [D1] S1 mermaid flowchart (4 lines)
      [D2] S1.1 graphviz digraph (1 line)
      """
    When I run "mdpeek doc.md --diagrams -s S1.1"
    Then the output is:
      """
      [D2] S1.1 graphviz digraph (1 line)
      """

  Scenario: Diagrams inline on request
    When I run "mdpeek doc.md -s S1.1 --full --no-diagram-summaries"
    Then the output is:
      """
      [S1.1] Graph
      [D2]
      ```dot
      digraph G { a -> b }
      ```
      """

  Scenario: Diagram as JSON
    When I run "mdpeek doc.md --diagram D2 --format json"
    Then the output is:
      """
      {"id":"D2","section":"S1.1","language":"graphviz","kind":"digraph","title":null,"lines":1,"source":"digraph G { a -> b }\n"}
      """

  Scenario Outline: Invalid diagram requests
    When I run "mdpeek doc.md <args>"
    Then the exit code is 2
    And stderr contains:
      """
      <message>
      """

    Examples:
      | args                          | message                                                   |
      | --diagram D9                  | no diagram 'D9'; available: D1, D2                        |
      | --diagrams --format csv       | --format csv does not apply to diagrams                   |
      | --diagram D1 -s S1            | --section cannot be combined with --table, --diagram      |
      | --diagrams --structure        | --structure cannot be combined with --table, --tables     |
      | --diagram D1 --table T1       | not allowed with argument                                 |
      | --format json                 | --format only applies with                                |
