Feature: What the MCP tool may reach
  The tool reads only inside its docs directory, runs only read-only SQL,
  and fetches only allowed URLs. A refused call explains what is allowed.

  Background:
    Given a docs directory from the fixture "library"

  Scenario Outline: Paths outside the docs directory are refused
    When the agent calls the tool with {"source": "<source>"}
    Then the call fails with a message containing "outside the docs directory"

    Examples:
      | source              |
      | ../secret.md        |
      | guides/../../x.md   |
      | /etc/passwd         |

  Scenario: A symlink that leads outside is refused
    Given a file outside the docs directory linked as "link.md"
    When the agent calls the tool with {"source": "link.md"}
    Then the call fails with a message containing "outside the docs directory"

  Scenario: A symlinked file that leads outside is left out of the map
    Given a file outside the docs directory linked as "link.md"
    When the agent calls the tool with {}
    Then the result ends with the note "skipped link.md: links outside the directory"

  Scenario Outline: SQL that is not a read-only query is refused
    When the agent calls the tool with {"source": "guides/deploy.md", "sql": "<sql>"}
    Then the call fails
    And no new file was created

    Examples:
      | sql                                 |
      | attach database 'copy.db' as copy   |
      | vacuum into 'copy.db'               |
      | pragma table_info(t1)               |
      | insert into t1 values ('a', 'b')    |

  Scenario: A refused query says what is allowed
    When the agent calls the tool with {"source": "guides/deploy.md", "sql": "attach database 'copy.db' as copy"}
    Then the call fails with a message containing "only read-only queries are allowed"

  Scenario: SQL can be turned off
    Given the tool is configured without SQL
    When the agent calls the tool with {"source": "guides/deploy.md", "sql": "select 1"}
    Then the call fails with a message containing "SQL is not enabled"

  Scenario: URLs are refused unless allowed
    When the agent calls the tool with {"source": "https://example.com/doc.md"}
    Then the call fails with a message containing "URL sources are not enabled"

  Scenario: Without a docs directory nothing on disk can be read
    Given the tool is configured without a docs directory
    When the agent calls the tool with {"source": "notes.md"}
    Then the call fails with a message containing "reading files is not enabled"
