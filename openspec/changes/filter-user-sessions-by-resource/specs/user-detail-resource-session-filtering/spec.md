## ADDED Requirements

### Requirement: Resource usage tags filter the session list
The user detail modal SHALL allow user-level model, MCP tool, and skill usage tags to filter the session list to sessions that used the selected resource during the modal's reporting period.

#### Scenario: Filter sessions by model
- **WHEN** an operator selects a model usage tag
- **THEN** the session list contains only sessions for the current user and reporting scope with an exact match for that model name

#### Scenario: Filter sessions by skill
- **WHEN** an operator selects a skill usage tag
- **THEN** the session list contains only sessions for the current user and reporting scope with a skill invocation whose skill name exactly matches the selected skill

#### Scenario: Filter sessions by MCP tool
- **WHEN** an operator selects an MCP tool usage tag
- **THEN** the session list contains only sessions for the current user and reporting scope with a completed MCP tool call matching both the selected MCP server and tool name

### Requirement: Resource filtering is single-select
The modal SHALL maintain at most one active resource filter across model, MCP tool, and skill resources.

#### Scenario: Replace the active resource filter
- **WHEN** one resource tag is active and the operator selects a different resource tag
- **THEN** the new resource replaces the previous resource as the only active resource filter

#### Scenario: Clear the active resource filter
- **WHEN** the operator selects the currently active resource tag again
- **THEN** the resource filter is cleared and the unfiltered session list for the remaining constraints is loaded

### Requirement: Selected resource tags have a persistent selected state
The modal SHALL render the active resource tag with a persistent visual and semantic selected state that is distinguishable from unselected tags without relying solely on hover or color.

#### Scenario: Display an active tag
- **WHEN** a resource filter is active
- **THEN** its tag has selected border, background, and text emphasis and exposes its pressed or selected state to assistive technology

#### Scenario: Move selected styling to another tag
- **WHEN** the operator replaces the active resource filter
- **THEN** the previous tag returns to its unselected style and only the newly active tag displays the selected state

#### Scenario: Clear selected styling
- **WHEN** the operator clears the active resource filter
- **THEN** no resource tag displays the selected state

#### Scenario: Display unselected tags
- **WHEN** no resource filter is active
- **THEN** model, MCP tool, and skill tags use the same neutral base tag treatment so skill tags are not visually confused with the selected state

### Requirement: Long resource tag lists are collapsible
The modal SHALL keep long model, MCP tool, and skill tag groups compact by default and allow operators to expand or collapse each group in place.

#### Scenario: Display a long tag group
- **WHEN** a resource tag group exceeds the compact display threshold or available preview height
- **THEN** the modal shows the group in a collapsed wrapped preview with an explicit expand control

#### Scenario: Expand and collapse a long tag group
- **WHEN** the operator activates the expand control for a collapsed tag group
- **THEN** the full tag group is shown in place and the control changes to a collapse action
- **WHEN** the operator activates the collapse control
- **THEN** the group returns to its compact preview without changing the active resource filter

#### Scenario: Keep the active tag discoverable in a collapsed group
- **WHEN** a resource tag group is collapsed and the active resource tag belongs to that group
- **THEN** the active tag remains visible in the collapsed preview

### Requirement: Resource filtering combines with error filtering
The modal SHALL combine an active resource filter with the existing error-session filter using AND semantics.

#### Scenario: Apply resource and error filters together
- **WHEN** a resource tag is active and the error-session filter is enabled
- **THEN** the session list contains only sessions that used the selected resource and contain an error

#### Scenario: Toggle error filtering without clearing resource selection
- **WHEN** the operator toggles the error-session filter while a resource tag is active
- **THEN** the resource tag remains selected and the session list reloads with the updated combined constraints

### Requirement: Resource filter changes reset session navigation state
The modal SHALL reset session navigation state when the active resource filter changes.

#### Scenario: Select or replace a resource filter
- **WHEN** the active resource filter is selected, replaced, or cleared
- **THEN** pagination returns to the first page, the previous selected session detail is cleared, and the list reloads using the current filters

#### Scenario: Auto-select the first filtered session
- **WHEN** a reloaded filtered result contains at least one session
- **THEN** the modal may apply its existing first-session auto-selection behavior to the first session in the new result set

### Requirement: User-level filter choices remain stable
The modal SHALL keep the usage summary based on user-level statistics while a resource filter is active.

#### Scenario: Select a session from a resource-filtered list
- **WHEN** a resource filter is active and the operator selects a filtered session
- **THEN** the model, MCP tool, and skill tags continue to represent the user's reporting-period usage and the active resource tag remains available and selected

#### Scenario: Select a session without a resource filter
- **WHEN** no resource filter is active and the operator selects a session
- **THEN** the modal may continue showing the selected session's statistics according to existing behavior

### Requirement: Sessions API validates and applies resource filters
The sessions API SHALL accept an optional discriminated resource filter, apply it consistently to result and count queries, and reject incomplete or unsupported resource identities.

#### Scenario: Request sessions without a resource filter
- **WHEN** a caller omits the resource filter
- **THEN** the endpoint preserves its existing session-list behavior

#### Scenario: Request sessions with a valid resource filter
- **WHEN** a caller supplies one supported resource type with its required exact identity fields
- **THEN** the endpoint returns matching sessions and a pagination total calculated using the same resource constraint

#### Scenario: Request sessions with an invalid resource filter
- **WHEN** a caller supplies an unsupported resource type or omits a required identity field
- **THEN** the endpoint returns a client error rather than ignoring or partially applying the filter

#### Scenario: Preserve existing session constraints
- **WHEN** a valid resource filter is combined with source, user, branch, date, session, pagination, or error constraints
- **THEN** all supplied constraints remain effective and tenant/source isolation is preserved
