## Why

The user detail modal summarizes models, MCP tools, and skills used by a user, but operators cannot use those summaries to locate the sessions that produced the usage. Resource-driven session filtering makes the summary actionable while preserving the existing session review workflow.

## What Changes

- Make model, MCP tool, and skill usage tags in the user detail modal interactive session filters.
- Allow at most one resource filter at a time; selecting another resource replaces the current resource filter, and selecting the active tag clears it.
- Preserve the existing error-session filter and allow it to combine with the active resource filter.
- Keep the usage summary based on user-level statistics while a resource filter is active so filter choices do not disappear or change after session selection.
- Give the active resource tag a persistent selected style that is clearly distinguishable from unselected tags without relying on hover.
- Keep unselected model, MCP tool, and skill tags visually consistent, and collapse long tag lists behind an explicit expand/collapse control.
- Extend the sessions API and query service to filter sessions by model name, MCP server and tool name, or skill name with source, user, branch, date, pagination, and error constraints preserved.
- Reset pagination and selected-session detail consistently when the resource filter changes.

## Capabilities

### New Capabilities

- `user-detail-resource-session-filtering`: Defines resource-tag interaction, selected-state presentation, filter combination rules, and resource-aware session query behavior in the analytics user detail modal.

### Modified Capabilities

None.

## Impact

- Console analytics user detail modal, usage summary tags, session list state, and focused component tests.
- Console tracing API client session filter parameters.
- Monitor tracing sessions router and query service, including backend tests for exact resource matching and combined filters.
- No route removal, response-shape break, database migration, or change to existing callers that omit the new optional filters.
