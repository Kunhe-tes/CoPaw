# Context Reference Default Discovery Design

## Goal

When the Console composer opens the `@` reference menu with an empty query, it
must show every available skill, at most three MCP tools, and no workspace
files. A non-empty query keeps the existing bounded search-result behavior.

## Root cause

The client already removes files and limits the initial MCP-tool display to
three items. The discovery endpoint applies `MAX_RESULTS_PER_GROUP` (four) to
every category before returning its response, so the client cannot display all
skills.

## Design

`ContextReferenceDirectory.discover` will distinguish the empty-query default
from a typed search:

- Empty query: return all discovered skills and the existing bounded MCP tool
  list; do not discover or return files.
- Non-empty query: filter each category by the query and retain the existing
  four-result cap per category.

The Console client remains the presentation authority for the initial menu: it
shows all received skills, slices MCP tools to three, and excludes files.

## Error handling and compatibility

Existing cache, discovery timeouts, and per-category error isolation are
unchanged. The response schema does not change. Existing callers using a typed
query retain their current result cap.

## Verification

Add a backend endpoint regression test with more than four skills to prove an
empty query returns all of them, while typed results remain capped. Run the
focused Python endpoint tests and the existing focused Console mention tests.
