## ADDED Requirements

### Requirement: System prompt SHALL expose current runtime time context
The final SystemPrompt SHALL include the current runtime date-time in the configured user timezone, with precision to seconds, and SHALL preserve timezone and weekday information in the same prompt field.

#### Scenario: Prompt includes current local date-time
- **WHEN** the runner builds environment context for an agent request
- **THEN** the final SystemPrompt SHALL include one runtime time field containing `YYYY-MM-DD HH:MM:SS`, timezone, and weekday
- **AND** the field SHALL represent the current time in the configured user timezone

#### Scenario: Invalid configured timezone falls back to UTC
- **WHEN** the configured user timezone is invalid during environment context construction
- **THEN** the final SystemPrompt SHALL still include the runtime time field
- **AND** the field SHALL use UTC as the timezone label and value basis

### Requirement: System prompt SHALL expose current source identity
The final SystemPrompt SHALL include the current request `source_id` as part of runtime environment context so the model can distinguish which source the request belongs to.

#### Scenario: Prompt includes explicit source identity
- **WHEN** an agent request is executed with `source_id=portal`
- **THEN** the final SystemPrompt SHALL include a runtime source field with value `portal`

#### Scenario: Missing source identity stays explicit
- **WHEN** an agent request is executed without a provided `source_id`
- **THEN** the final SystemPrompt SHALL still include the runtime source field
- **AND** the field SHALL use an explicit missing-value placeholder instead of omitting the field
- **AND** the system SHALL NOT substitute `"default"` unless the request actually provided `source_id=default`
