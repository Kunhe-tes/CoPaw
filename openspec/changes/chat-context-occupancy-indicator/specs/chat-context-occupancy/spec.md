## ADDED Requirements

### Requirement: Backend SHALL expose persisted context occupancy
The system SHALL expose a read-only API that returns persisted context occupancy for a requested chat session in the current tenant/source/agent scope. The occupancy SHALL be computed as estimated used context tokens divided by the active Agent `running.max_input_length`.

#### Scenario: Occupancy request for an existing session
- **WHEN** the Console requests context occupancy for an existing session id
- **THEN** the backend SHALL return `used_tokens`, `max_input_length`, `ratio`, `status`, and `estimated`
- **AND** `max_input_length` SHALL equal the current Agent running configuration value
- **AND** `ratio` SHALL equal `used_tokens / max_input_length` capped only for display-status calculation, not for the raw returned token values

#### Scenario: Occupancy request excludes draft input
- **WHEN** the user has unsent text in the Console composer
- **THEN** the occupancy response SHALL NOT include that unsent composer text in `used_tokens`

### Requirement: Occupancy SHALL represent effective next Main Agent input context
The occupancy estimate SHALL include persisted state and fixed runtime context that would actually enter the next Main Agent model input after completed compaction. It SHALL include system prompt, completed compressed summary, effective history messages, and compacted tool results; it SHALL exclude already-compacted raw history and cumulative tokens billed by completed model calls.

#### Scenario: Compacted history exists
- **WHEN** a session contains raw history that has already been compacted into a completed compressed summary
- **THEN** the occupancy estimate SHALL count the completed compressed summary
- **AND** it SHALL NOT count the already-compacted raw history as if it would still enter the next model input

#### Scenario: Fixed runtime context exists in an otherwise empty chat
- **WHEN** a session has little or no visible chat history but the Main Agent has fixed runtime context such as system prompt
- **THEN** the occupancy estimate SHALL include that fixed runtime context
- **AND** the indicator SHALL NOT imply the context window is completely empty solely because visible messages are empty

### Requirement: Occupancy status SHALL classify display risk
The backend or frontend SHALL classify occupancy into display status values using the agreed thresholds: `normal` for less than 70%, `warning` for 70% to less than 90%, `danger` for 90% to less than 100%, and `overflow` for 100% or greater. These thresholds SHALL only drive visual state and tooltip wording; they SHALL NOT block submission or change compaction behavior.

#### Scenario: Warning threshold is reached
- **WHEN** the occupancy ratio is at least 0.70 and less than 0.90
- **THEN** the displayed indicator SHALL use the warning visual state
- **AND** submitting a message SHALL remain allowed by the existing chat submission rules

#### Scenario: Overflow threshold is reached
- **WHEN** the occupancy ratio is at least 1.00
- **THEN** the displayed indicator SHALL use the overflow visual state
- **AND** the system SHALL NOT reject submission solely because the display status is `overflow`

### Requirement: Backend SHALL cache occupancy estimates with deterministic invalidation
The backend SHALL cache computed occupancy estimates and SHALL invalidate them when the scoped session state version or relevant Agent running/compaction configuration fingerprint changes. Cache entries SHALL be scoped at least by tenant/source scope, agent id, session id, session state version, and running/compaction config fingerprint.

#### Scenario: Unchanged session and config
- **WHEN** the same scoped session occupancy is requested repeatedly without session state or relevant config changes
- **THEN** the backend MAY return the cached estimate
- **AND** the response SHALL preserve the same occupancy semantics as a fresh calculation

#### Scenario: Session state changes
- **WHEN** the session state is saved after new messages, compaction, or tool-result compaction
- **THEN** the next occupancy request SHALL miss or invalidate the old cache entry
- **AND** it SHALL compute against the new effective persisted context

#### Scenario: Running configuration changes
- **WHEN** `running.max_input_length` or relevant context/tool compaction configuration changes
- **THEN** the next occupancy request SHALL miss or invalidate the old cache entry
- **AND** it SHALL return values computed against the new configuration

### Requirement: Console Chat SHALL render a quiet circular indicator beside submit
The Console Chat composer SHALL render a circular context occupancy indicator immediately to the left of the submit button. The default composer state SHALL show only the ring fill and color; it SHALL NOT show persistent percentage text beside or inside the ring.

#### Scenario: Occupancy value is available
- **WHEN** the current chat has an available occupancy estimate
- **THEN** the composer SHALL show a circular ring to the left of the submit button
- **AND** the ring fill SHALL reflect the occupancy ratio
- **AND** the ring color SHALL reflect the occupancy status
- **AND** no persistent percentage text SHALL be shown in the composer

#### Scenario: Occupancy value is unavailable
- **WHEN** no occupancy estimate is available or estimation fails
- **THEN** the composer SHALL show a grey empty ring
- **AND** the composer layout SHALL remain stable

### Requirement: Indicator tooltip SHALL expose approximate details
The circular indicator SHALL expose approximate context details only on hover or focus. Tooltip content SHALL communicate that values are estimates and SHALL include approximate used tokens, max context tokens, percentage, and status explanation. The tooltip SHALL NOT display update time in the first version.

#### Scenario: User hovers the indicator
- **WHEN** the user hovers or focuses the occupancy ring
- **THEN** the tooltip SHALL show approximate used tokens and max context tokens
- **AND** it SHALL show the approximate percentage and status explanation
- **AND** it SHALL use estimated wording such as "约" or equivalent localized copy

#### Scenario: Value is unavailable
- **WHEN** the user hovers or focuses the unavailable grey ring
- **THEN** the tooltip SHALL state that context occupancy is temporarily unavailable

### Requirement: Frontend SHALL refresh occupancy on stable chat events
The Console Chat frontend SHALL refresh context occupancy on page entry, active session switch, chat history reload, model or Agent running configuration changes, and stream completion. It SHALL NOT poll continuously and SHALL NOT refresh while the user is only typing draft input.

#### Scenario: Session switch
- **WHEN** the user switches from one chat session to another
- **THEN** the frontend SHALL request occupancy for the newly active session

#### Scenario: Message stream completes
- **WHEN** a generating chat stream completes
- **THEN** the frontend SHALL request occupancy once for that session after persisted state has stabilized

#### Scenario: User types draft input
- **WHEN** the user edits unsent composer text
- **THEN** the frontend SHALL NOT refresh occupancy solely because the draft text changed

### Requirement: Frontend SHALL keep refreshes non-disruptive
The Console Chat frontend SHALL keep the previous ring value visible while a refresh is in flight and SHALL NOT show a spinner or "updating" label. During generation, it SHALL keep the previous value and refresh once generation completes.

#### Scenario: Refresh starts with a previous value
- **WHEN** an occupancy refresh starts and the composer already has a previous value
- **THEN** the frontend SHALL keep displaying the previous ring value
- **AND** it SHALL NOT show a loading spinner or updating label

#### Scenario: Generation is in progress
- **WHEN** the current chat is generating
- **THEN** the frontend SHALL keep the previous occupancy value during generation
- **AND** it SHALL refresh occupancy after the stream completes
