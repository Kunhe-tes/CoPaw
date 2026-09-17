## ADDED Requirements

### Requirement: Runtime messages SHALL use only standard roles
The system SHALL create, persist, restore, expose, and send runtime messages using only `system`, `user`, `assistant`, and `tool` roles. The system MUST NOT create or send a `developer` role message.

#### Scenario: New runtime messages exclude developer role
- **WHEN** the runtime creates messages for a new agent turn
- **THEN** every message SHALL use `system`, `user`, `assistant`, or `tool`
- **AND** no message SHALL use `developer`

#### Scenario: Provider request excludes developer role
- **WHEN** the runtime formats a request for an OpenAI-compatible Provider
- **THEN** the formatted request SHALL NOT contain a `developer` role message
- **AND** the Provider layer SHALL NOT retry by downgrading `developer` to `user`

### Requirement: Hook additional context SHALL use system role
The system SHALL represent hook `additionalContext` as `system` role messages across memory, session persistence, chat history, and Provider requests.

#### Scenario: Tool hook context is persisted as system
- **WHEN** a tool hook returns non-empty `additionalContext`
- **THEN** the runtime SHALL append the hook context to agent memory with `role="system"`
- **AND** the saved session SHALL preserve `role="system"`

#### Scenario: Stop hook context is persisted as system
- **WHEN** a Stop hook returns non-empty `additionalContext`
- **THEN** the runner SHALL append the hook context to agent memory with `role="system"`

#### Scenario: Formatter preserves hook system role
- **WHEN** a hook system message appears after the first message in model history
- **THEN** the formatter SHALL preserve its `system` role
- **AND** it SHALL NOT convert the message to `developer` or `user`

#### Scenario: Chat API exposes hook context as system
- **WHEN** the chat detail API reads history containing hook additional context
- **THEN** the API SHALL expose that message with `role="system"`

### Requirement: Accepted plan execution context SHALL use tool role
The system SHALL provide a server-validated accepted plan to the execution turn as an internal tool result and SHALL NOT append the accepted plan to the main system prompt.

#### Scenario: Accepted plan is injected as valid tool exchange
- **WHEN** a normal execution turn contains an accepted plan loaded from the server plan store
- **THEN** the runtime SHALL inject a paired internal assistant tool call and `tool` result
- **AND** the tool result SHALL contain the bounded accepted plan execution context
- **AND** the tool call and result SHALL use matching identifiers

#### Scenario: Accepted plan does not modify system prompt
- **WHEN** an accepted plan is available for an execution turn
- **THEN** the main system prompt SHALL NOT contain the accepted plan execution context

#### Scenario: Untrusted accepted plan is not injected
- **WHEN** accepted plan data lacks the server plan store source marker
- **THEN** the runtime SHALL NOT inject an accepted plan tool exchange

#### Scenario: Plan Mode does not receive accepted execution context
- **WHEN** the current turn remains in Plan Mode
- **THEN** the runtime SHALL NOT inject an accepted plan tool exchange

#### Scenario: Internal plan exchange does not execute a tool
- **WHEN** the runtime injects an accepted plan tool exchange
- **THEN** it SHALL NOT invoke Toolkit, ToolGuard, hooks, approval flows, or frontend tool cards

### Requirement: Legacy developer history SHALL migrate to system role
The system SHALL accept legacy persisted history containing `developer` messages and SHALL migrate those messages to `system` at the session loading boundary without restoring the original role.

#### Scenario: Legacy session loads successfully
- **WHEN** a saved session contains a `developer` role message
- **THEN** session loading SHALL succeed
- **AND** the in-memory message SHALL use `role="system"`

#### Scenario: Migrated session no longer persists developer
- **WHEN** a legacy session has been loaded and saved again
- **THEN** the saved session SHALL contain `role="system"` for the migrated message
- **AND** it SHALL NOT contain `role="developer"`

#### Scenario: Legacy chat history remains readable
- **WHEN** the chat detail API reads a legacy history containing `developer`
- **THEN** the API SHALL return the message as `system`
- **AND** the request SHALL NOT fail because of the legacy role

### Requirement: Role troubleshooting documentation SHALL match runtime behavior
The project playbook SHALL describe hook contexts as system messages and accepted plan execution contexts as tool results, and SHALL NOT instruct operators to preserve or downgrade developer messages.

#### Scenario: Operator investigates message role failure
- **WHEN** an operator follows the message-role troubleshooting playbook
- **THEN** the documented checks SHALL point to hook system preservation, accepted plan tool exchange pairing, and legacy developer-to-system migration
