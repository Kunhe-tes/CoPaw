## MODIFIED Requirements

### Requirement: Hook runtime SHALL emit supported agent lifecycle events
The system SHALL provide a unified hook runtime that can emit `SessionStart`,
`UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, and
`Stop` events with a structured HookContext. `BeforeStop` is not a supported
event and configuration using it SHALL be rejected.

#### Scenario: Runner emits user prompt event before normal processing
- **WHEN** an agent request contains a user prompt
- **THEN** the system SHALL emit `UserPromptSubmit` before command dispatch and agent reasoning
- **AND** matched hooks SHALL be able to block or enrich the prompt before it is processed

#### Scenario: Tool execution emits pre and post tool events
- **WHEN** an agent requests a tool call
- **THEN** the system SHALL emit `PreToolUse` before executing the tool
- **AND** the system SHALL emit `PostToolUse` after a successful tool execution
- **AND** the system SHALL emit `PostToolUseFailure` after a failed tool execution

#### Scenario: Runner emits Stop for a newly generated candidate response
- **WHEN** an agent turn produces a candidate assistant response
- **THEN** the system SHALL emit `Stop` once before treating that candidate as complete
- **AND** the HookContext SHALL include that candidate response

#### Scenario: Runner does not emit Stop without a current-turn candidate
- **WHEN** a turn produces no assistant response, or ends through a terminal tool-hook stop
- **THEN** the system SHALL NOT emit `Stop`
- **AND** a response from prior agent memory SHALL NOT be reused as a Stop candidate

## ADDED Requirements

### Requirement: Stop SHALL act as the unified completion gate
The system SHALL treat `Stop` as the only completion gate after a candidate
assistant response. Each matched handler may record its own side effects; the
merged decision determines whether the request can complete.

#### Scenario: Stop allows normal completion
- **WHEN** matched `Stop` handlers return `decision="allow"`
- **THEN** the candidate response SHALL be eligible for normal completion

#### Scenario: Stop blocks stopping and continues the agent
- **WHEN** a matched `Stop` handler returns `decision="block"` with a reason
- **AND** automatic continuation budget remains
- **THEN** the system SHALL convert the reason into an internal follow-up instruction
- **AND** the agent SHALL continue execution in the same request

#### Scenario: Stop block exhausts its continuation budget
- **WHEN** `Stop` returns `decision="block"` after its automatic continuation budget is exhausted
- **THEN** the system SHALL stop automatic continuation
- **AND** the system SHALL surface the latest block reason and mark the task incomplete

#### Scenario: Blocking handler failure does not continue the agent
- **WHEN** a `Stop` handler fails with `failPolicy="block"`
- **THEN** the system SHALL mark the task incomplete without scheduling an automatic follow-up
- **AND** the surfaced reason SHALL be the blocking handler failure reason

### Requirement: Stop SHALL support only allow and block decisions
The system SHALL require every `Stop` handler output to have a `decision` of
only `allow` or `block`. Unsupported or missing decisions SHALL follow the
handler failure policy.

#### Scenario: Stop output validation is event-specific
- **WHEN** a handler on another event returns output supported by that event
- **THEN** the system SHALL preserve that event's existing semantics
- **AND** the stricter Stop output contract SHALL not change unrelated events

### Requirement: Stop continuation SHALL be bounded and re-entry safe
The system SHALL prevent Stop-driven continuations from recursing or looping
indefinitely.

#### Scenario: Stop guard is scoped to the active completion path
- **WHEN** the runner is already executing the Stop hook path
- **THEN** it SHALL NOT recursively emit Stop
- **AND** it SHALL clear the guard before a scheduled follow-up turn starts

#### Scenario: Stop continuation budget is configured under current names
- **WHEN** a runtime configuration supplies `max_stop_turns` or `max_automatic_follow_up_turns`
- **THEN** the system SHALL use those budgets
- **AND** the removed `max_before_stop_turns` key SHALL be rejected
