## Context

The analytics user detail modal currently loads user-level usage summaries and a paginated session list independently. Selecting a session replaces the summary data with session-level statistics, while the only list-level interaction filter is the existing error-session toggle. The sessions endpoint can filter by user, session, date, branch, and error state, but it cannot restrict sessions by a model, MCP tool, or skill recorded in tracing data.

The resource usage data already has stable identifiers: model name, skill name, and the composite MCP identity of server name plus tool name. Session membership can be derived from `swe_tracing_traces` for models and `swe_tracing_spans` for skills and MCP tools. The change crosses Console state, API contracts, monitor routing, and SQL query construction, so the filtering contract needs to be explicit before implementation.

## Goals / Non-Goals

**Goals:**

- Turn user-level model, MCP tool, and skill tags into exact-match session filters.
- Enforce one active resource filter across the three resource types while allowing combination with the existing error filter.
- Keep the filter choices stable by showing user-level usage summary data whenever a resource filter is active.
- Make the selected tag visibly and semantically distinct from unselected tags.
- Preserve pagination totals, source isolation, user, branch, date, and error constraints in resource-filtered queries.

**Non-Goals:**

- Multi-select, OR, or AND combinations across multiple resource tags.
- Filtering by non-MCP built-in tools.
- Changing the meaning or aggregation counts of the usage summary.
- Adding database columns or migrations.
- Redesigning unrelated analytics pages or the full user detail modal.

## Decisions

### Use one discriminated resource filter contract

The sessions API will accept an optional resource filter composed of a resource type and exact identity values. Supported types are `model`, `skill`, and `mcp_tool`. Model and skill filters require a resource name. MCP filters require both MCP server and tool name.

This mirrors the agreed single-selection interaction and prevents ambiguous combinations such as model plus skill from entering through the API. Separate independent query parameters were considered, but they would require precedence or combination semantics that the product explicitly does not support.

Invalid or incomplete resource filter combinations will return a client error rather than silently ignoring fields.

### Filter session membership in the database

Model membership will use exact `model_name` matches from tracing traces. Skill membership will use exact `skill_name` matches on `skill_invocation` spans. MCP tool membership will use exact `mcp_server` and `tool_name` matches on completed MCP tool-call spans.

The resource constraint will be added to both the count and data queries so pagination totals remain accurate. Querying the existing skill-trace endpoint and deduplicating sessions in the Console was rejected because trace pagination cannot produce correct session totals or stable session pagination.

### Keep resource identity separate from display labels

The Console will pass structured resource identity to tag callbacks. Display strings such as `tool (server)` will not be parsed to recover tool or server names. This avoids breakage when names contain punctuation or the display format changes.

### Centralize resource selection in the modal

`UserDetailModal` will own the active resource filter. `UserStatsHeader` will receive the active filter and a selection callback; it will remain responsible only for rendering tags and their selected state. Selecting the active identity clears the filter. Selecting another identity atomically replaces it.

Changing the resource filter resets the session page to one, clears the selected session and session-level statistics, reloads the filtered session list, and allows the existing first-result auto-selection behavior to run against the new result set.

### Keep user-level summary visible during resource filtering

When no resource filter is active, selecting a session may continue to show that session's statistics. When a resource filter is active, the summary will remain based on `userStats`, even after a filtered session is selected. This keeps every available filter tag stable and prevents the active filter from disappearing because the selected session summary has a narrower resource set.

### Give selected tags persistent visual and semantic state

Usage tags will become keyboard-operable controls. The active tag will receive a dedicated selected class and an accessible selected/pressed state. The selected treatment will use persistent border, background, text emphasis, and focus-visible styling so it remains distinguishable from unselected and hover states without relying on color alone. Existing resource tone differences may remain, but selected styling will be consistent across all three resource types.

The selected state will use existing Console design tokens or established local values. No new shared design-system rule is introduced by this scoped interaction.

### Combine resource and error filters with AND semantics

The resource filter and error-session filter can be active together. The returned session must satisfy both constraints. Resource tags do not clear the error filter, and toggling the error filter does not clear the resource filter.

### Use the modal's analytics date range for list filtering

Session requests from this modal will carry its existing start and end date inputs so resource membership, user summary, and session list refer to the same reporting period. Existing endpoint callers that omit dates retain their current behavior.

## Risks / Trade-offs

- [Resource subqueries may increase session-list query cost] -> Use exact-match predicates on existing source/session/skill/tool indexes, keep pagination in SQL, and add focused query tests; inspect query plans if representative data reveals regressions.
- [MCP tool names may collide across servers] -> Treat MCP server plus tool name as the resource identity everywhere.
- [Selected styling could be confused with the existing resource color] -> Apply a shared selected treatment and semantic pressed state in addition to each tag's base tone.
- [Filter changes can race with prior requests] -> Follow the modal's existing loading/state pattern and ensure state reset and fetch dependencies are deterministic; add interaction tests covering replacement and clearing.
- [Keeping global statistics while filtering differs from ordinary session selection] -> Limit that behavior to the period when a resource filter is active and expose the active selection directly on the tag.

## Migration Plan

1. Deploy the optional backend API and query support; existing clients remain compatible because the resource filter is optional.
2. Deploy the Console interaction using the new parameters.
3. Roll back the Console independently if needed; the unused optional backend parameters are harmless.
4. Roll back backend support only after the Console version using it is no longer deployed.

## Open Questions

None. Resource single-selection, error-filter combination, global-summary behavior, and visible selected-tag state have been accepted.
