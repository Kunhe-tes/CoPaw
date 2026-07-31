## MODIFIED Requirements

### Requirement: Hook configuration SHALL support prompt handlers
The system SHALL support a `prompt` hook handler type in tenant, agent, and
skill hook configuration.

#### Scenario: Tenant prompt handler config is accepted
- **WHEN** tenant hook configuration defines a handler with `type="prompt"` and a non-empty `prompt`
- **AND** the handler is configured under a supported prompt hook event
- **THEN** the system SHALL parse the handler as a prompt hook handler
- **AND** the handler SHALL retain common fields including `if`, `timeout`, `statusMessage`, `once`, and `failPolicy`

#### Scenario: Agent or skill prompt handler config is accepted
- **WHEN** agent configuration or a skill `hooks/hooks.json` defines a valid prompt handler
- **THEN** the system SHALL parse it and, for a skill, load it into session hook state using the existing namespaced handler-id rules

#### Scenario: Empty or overridden prompt handler rules are rejected
- **WHEN** a prompt handler has an empty `prompt` or includes model/provider routing or prompt-template fields
- **THEN** the system SHALL reject the handler configuration during validation

#### Scenario: Prompt handler defaults to fail closed
- **WHEN** a hook configuration omits a prompt handler's `failPolicy`
- **THEN** the parsed handler SHALL use `failPolicy="block"`

### Requirement: Prompt handlers SHALL only be valid on supported lifecycle events
The system SHALL allow prompt handlers only on `SessionStart`,
`UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, and
`Stop`.

#### Scenario: Prompt handler is valid on Stop
- **WHEN** hook configuration defines a `prompt` handler under `Stop`
- **THEN** the system SHALL accept the handler configuration

#### Scenario: Prompt handler is rejected on the removed BeforeStop event
- **WHEN** hook configuration defines a prompt handler under `BeforeStop`
- **THEN** the system SHALL reject the handler configuration during validation

### Requirement: Prompt handlers SHALL assemble model input with fixed layers
The system SHALL construct prompt handler model input using a platform-owned
scaffold before and after the hook business rules.

#### Scenario: Model input preserves fixed layer order
- **WHEN** a prompt handler is executed
- **THEN** the model input SHALL include the platform fixed scaffold, configured business rules, prompt-safe HookContext JSON, and structured output constraints in that order

#### Scenario: HookContext is injected as JSON data
- **WHEN** a prompt handler is executed
- **THEN** the system SHALL serialize a prompt-safe copy of `HookContext.to_handler_payload()` as JSON
- **AND** the platform scaffold SHALL instruct the model to treat those values as data rather than instructions

#### Scenario: Stop prompt handler receives its candidate response
- **WHEN** a prompt handler is executed for `Stop`
- **THEN** the runtime context SHALL include the candidate assistant response being evaluated
- **AND** the handler SHALL NOT be expected to infer it from `prompt` or `transcript_path`

## ADDED Requirements

### Requirement: Stop prompt handlers SHALL produce completion-gate judgments
The system SHALL treat prompt handler output for `Stop` as a completion-gate
judgment.

#### Scenario: Stop prompt allow or block output is parsed
- **WHEN** a `Stop` prompt handler model response is a JSON object with exactly `decision="allow"` or `decision="block"` and a non-empty string `reason`
- **THEN** the runtime SHALL use that completion-gate judgment

#### Scenario: Invalid Stop prompt output follows failPolicy
- **WHEN** a `Stop` prompt handler output has a missing or unsupported decision, or extra fields
- **THEN** the handler SHALL treat the output as invalid
- **AND** the event outcome SHALL follow the handler's configured `failPolicy`

#### Scenario: Non-Stop prompt deny remains valid
- **WHEN** a prompt handler on `SessionStart`, `UserPromptSubmit`, or `PreToolUse` returns exactly `decision="deny"` with a non-empty reason
- **THEN** the handler SHALL preserve the deny judgment semantics for that event
