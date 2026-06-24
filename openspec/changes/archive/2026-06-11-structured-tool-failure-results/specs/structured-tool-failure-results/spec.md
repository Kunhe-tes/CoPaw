## ADDED Requirements

### Requirement: Failed tool invocations SHALL persist a Structured Tool Failure Result
The system SHALL persist failed tool invocations using a canonical structured `tool_result` payload with `isError=true`, a non-empty `content` collection, and an `error_type` string instead of representing failure only as successful plain-text output.

#### Scenario: Local tool raises Tool Execution Error
- **WHEN** a Swe-controlled local tool raises a `ToolExecutionError`
- **THEN** the tool execution entrypoint SHALL convert that failure into a persisted structured failed `tool_result`
- **AND** the persisted result SHALL set `isError=true`
- **AND** the persisted result SHALL include the declared `error_type`

#### Scenario: MCP tool returns an error result
- **WHEN** an MCP tool completes with an error result identified by `isError=true`
- **THEN** the persisted `tool_result` SHALL preserve that invocation as a structured failed tool result
- **AND** the system SHALL NOT downgrade it into a success-shaped plain-text output

#### Scenario: Runtime denies or times out a tool call
- **WHEN** the runtime itself fails a tool invocation through hook denial, auto-deny, approval denial, or local hard timeout
- **THEN** the runtime SHALL persist that outcome using the same structured failed `tool_result` contract
- **AND** the runtime SHALL NOT emit a bespoke plain-text-only failure payload for that invocation

### Requirement: Tool execution SHALL normalize unexpected failures into the canonical failure contract
The system SHALL normalize non-contract exceptions raised during Swe-controlled tool execution into structured failed `tool_result` payloads instead of letting those exceptions escape as unstructured tool output.

#### Scenario: Local tool raises a generic exception
- **WHEN** a Swe-controlled local tool raises an exception other than `ToolExecutionError`
- **THEN** the tool execution entrypoint SHALL catch that exception
- **AND** the persisted failed `tool_result` SHALL use the canonical structured failure contract
- **AND** the persisted result SHALL use `error_type="unexpected_tool_error"` unless a more specific mapping applies

#### Scenario: Known tool transport error is mapped to a specific error type
- **WHEN** a Swe-controlled tool execution path fails with a recognized transport or subsystem exception such as an MCP error or timeout
- **THEN** the tool execution entrypoint SHALL convert that failure into a structured failed `tool_result`
- **AND** the persisted result SHALL use a specific mapped `error_type` rather than the generic unexpected-error fallback

### Requirement: Structured Tool Failure Result SHALL preserve raw failure detail for model reasoning
The canonical structured failed `tool_result` contract SHALL preserve raw failure detail in its `content` blocks so the model can continue reasoning from the failure without depending on runner-generated summaries.

#### Scenario: Tool execution error includes raw failure detail
- **WHEN** a failed tool invocation is persisted as a structured failed `tool_result`
- **THEN** the result SHALL include non-empty failure detail in `content`
- **AND** that failure detail SHALL remain available in persisted tool output for later model turns

#### Scenario: Tool Error Summary remains a separate presentation concern
- **WHEN** a failed tool invocation is persisted as a structured failed `tool_result`
- **THEN** the system SHALL treat bounded `tool_error` summaries as a separate presentation-layer derivation
- **AND** the persisted structured failure result SHALL remain the canonical source for raw failure detail and failure type
