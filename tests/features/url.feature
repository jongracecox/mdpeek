Feature: URL sources and caching
  A URL is fetched once and cached on disk, so repeated calls on the same
  document don't download it again. Output from the cache starts with a line
  saying when the copy was fetched.

  Background:
    Given a URL "/guide.md" serving:
      """
      # Guide
      Welcome.
      ## Install
      Run it.
      """

  Scenario: Viewing a URL
    When I run "mdpeek {server}/guide.md -d 1"
    Then the output is:
      """
      [S1] Guide
      Welcome.
        [S1.1] Install (1 ln)
      """
    And the server received 1 request

  Scenario: The next call uses the cache and says so
    Given the time is "2026-11-20 09:00"
    When I run "mdpeek {server}/guide.md --structure"
    Given the time is "2026-11-20 09:30"
    When I run "mdpeek {server}/guide.md --structure"
    Then the output is:
      """
      (cached 2026-11-20 09:00Z)
      [S1] Guide (1)
        [S1.1] Install (1)
      """
    And the server received 1 request

  Scenario: An expired copy is fetched again
    Given the time is "2026-11-20 09:00"
    When I run "mdpeek {server}/guide.md"
    Given the time is "2026-11-20 10:01"
    When I run "mdpeek {server}/guide.md --structure"
    Then the output is:
      """
      [S1] Guide (1)
        [S1.1] Install (1)
      """
    And the server received 2 requests

  Scenario: A longer TTL keeps using the cached copy
    Given the time is "2026-11-20 09:00"
    When I run "mdpeek {server}/guide.md"
    Given the time is "2026-11-20 15:00"
    When I run "mdpeek {server}/guide.md --ttl 86400 -s S1.1"
    Then the output is:
      """
      (cached 2026-11-20 09:00Z)
      [S1.1] Install
      Run it.
      """

  Scenario: Refresh ignores the cache and updates it
    Given the time is "2026-11-20 09:00"
    When I run "mdpeek {server}/guide.md"
    Given the URL "/guide.md" now serves:
      """
      # Guide v2
      """
    When I run "mdpeek {server}/guide.md --refresh --structure"
    Then the output is:
      """
      [S1] Guide v2 (0)
      """
    When I run "mdpeek {server}/guide.md --structure"
    Then the output is:
      """
      (cached 2026-11-20 09:00Z)
      [S1] Guide v2 (0)
      """
    And the server received 2 requests

  Scenario: No cache
    When I run "mdpeek {server}/guide.md --no-cache"
    And I run "mdpeek {server}/guide.md --no-cache"
    Then the output does not start with "(cached"
    And the server received 2 requests

  Scenario: Headers are sent, cached separately, and never stored
    When I run "mdpeek {server}/guide.md -H 'Authorization: Bearer s3cret'"
    Then the last request had the header "Authorization: Bearer s3cret"
    When I run "mdpeek {server}/guide.md -H 'Authorization: Bearer other'"
    Then the server received 2 requests
    And no cached file contains "s3cret"

  Scenario: Data formats report the cache on stderr, keeping stdout parseable
    Given a URL "/data.md" serving:
      """
      | a | b |
      |---|---|
      | 1 | 2 |
      """
    And the time is "2026-11-20 09:00"
    When I run "mdpeek {server}/data.md --table T1 --format csv"
    And I run "mdpeek {server}/data.md --table T1 --format csv"
    Then the output is:
      """
      a,b
      1,2
      """
    And stderr contains:
      """
      mdpeek: (cached 2026-11-20 09:00Z)
      """

  Scenario: A missing page
    When I run "mdpeek {server}/missing.md"
    Then the exit code is 2
    And stderr contains:
      """
      HTTP 404 Not Found
      """

  Scenario: URL options with a file are rejected
    Given a markdown file containing:
      """
      # A
      """
    When I run "mdpeek doc.md --refresh -H 'X: y'"
    Then the exit code is 2
    And stderr contains:
      """
      mdpeek: --header, --refresh only apply to URL sources
      """
