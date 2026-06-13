## ADDED Requirements

### Requirement: Current source can configure tool result compaction
The system SHALL allow manager or admin users to configure tool result compaction for the current request source from the system config page.

#### Scenario: Manager saves source tool result compaction config
- **WHEN** a manager updates tool result compaction values on the current source system config page
- **THEN** the system SHALL persist the values under the current source system config without requiring a source selector

#### Scenario: Non-manager cannot edit source tool result compaction config
- **WHEN** a user without manager or admin role opens the system config page
- **THEN** the system SHALL prevent access to the editable tool result compaction controls

### Requirement: Source tool result config supports explicit override fields
The system SHALL support the following current-source tool result compaction fields: `enabled`, `recent_n`, `old_max_bytes`, `recent_max_bytes`, and `retention_days`.

#### Scenario: Valid config is accepted
- **WHEN** source config contains boolean `enabled`, integer `recent_n`, integer `old_max_bytes`, integer `recent_max_bytes`, and integer `retention_days` within supported ranges
- **THEN** the system SHALL accept the config and expose it in current-source raw config

#### Scenario: Invalid config is rejected
- **WHEN** source config contains unsupported types or out-of-range tool result compaction values
- **THEN** the system SHALL reject the update instead of silently saving invalid thresholds

### Requirement: Unconfigured source inherits Agent runtime config
The system SHALL continue using the existing Agent runtime `tool_result_compact` configuration when the current source has no explicit `tool_result_compact` override.

#### Scenario: Source has no override
- **WHEN** a request runs under a source whose raw system config does not contain `tool_result_compact`
- **THEN** tool result compaction SHALL use the Agent runtime `tool_result_compact` values

#### Scenario: Source has partial override
- **WHEN** a request runs under a source whose raw system config contains only some `tool_result_compact` fields
- **THEN** explicitly configured fields SHALL override Agent runtime values and missing fields SHALL inherit Agent runtime values

### Requirement: Source override controls runtime truncation and compaction
The system SHALL apply the resolved tool result compaction config to both tool result history compaction and immediate tool output truncation.

#### Scenario: Source recent max bytes affects read file truncation
- **WHEN** the current source config explicitly sets `tool_result_compact.recent_max_bytes`
- **THEN** file-read tool output truncation SHALL use that value for the request context

#### Scenario: Source config affects tool result history compaction
- **WHEN** the current source config explicitly sets tool result compaction thresholds
- **THEN** the memory compaction hook SHALL pass the resolved thresholds to tool result compaction

#### Scenario: Source disables tool result compaction
- **WHEN** the current source config sets `tool_result_compact.enabled` to `false`
- **THEN** the memory compaction hook SHALL skip tool result compaction for that request

### Requirement: System config page preserves unrelated source config
The system SHALL preserve unknown or unrelated source system config keys when saving tool result compaction values from the system config page.

#### Scenario: Unknown keys survive save
- **WHEN** current source raw config contains keys not managed by the system config page
- **THEN** saving tool result compaction values SHALL keep those keys unchanged

#### Scenario: Default-equivalent overrides are pruned
- **WHEN** saved tool result compaction fields are equivalent to registered default values and no other source config remains
- **THEN** the system SHALL remove the unnecessary explicit current-source config record

### Requirement: Saved config refreshes effective source config
The system SHALL refresh the frontend effective source config after a successful current-source tool result compaction save.

#### Scenario: Save refreshes effective config
- **WHEN** a manager successfully saves tool result compaction settings
- **THEN** the Console SHALL reload effective source config for the active source before reporting the save as complete
