# subagent-runtime Specification

## Purpose
Define the bounded SubAgent runtime contract for synchronous readonly
delegation from the Main Agent, including definition validation, fresh context,
effective permissions, compact results, and run recording.
## Requirements
### Requirement: SubAgent definitions SHALL describe bounded runtime workers
The system SHALL provide named SubAgent definitions that include identity,
description, prompt contract, allowed tools, permission policy, isolation mode,
budget, routing metadata, lifecycle settings, and registration metadata.
Registration metadata SHALL include schema version, definition source, owner
scope, enabled state, timestamps, and optional creator identity.

#### Scenario: Built-in readonly definitions are available
- **WHEN** the SubAgent registry is initialized
- **THEN** it SHALL resolve `plan-researcher`, `risk-reviewer`, and `test-surface-analyzer` definitions

#### Scenario: Nested delegation is rejected at definition validation
- **WHEN** a SubAgent definition enables nested delegation
- **THEN** the registry SHALL reject the definition

#### Scenario: Unsupported tool names are rejected
- **WHEN** a SubAgent definition allows an unknown built-in tool name or an MVP-disabled capability such as MCP
- **THEN** the registry SHALL reject the definition with a structured validation error

#### Scenario: Definition source is recorded
- **WHEN** a SubAgent definition is registered or loaded
- **THEN** the registry SHALL preserve whether the definition is `builtin` or future `user` sourced and SHALL preserve the owning tenant/source/workspace scope

#### Scenario: Built-in definitions are immutable
- **WHEN** a caller attempts to replace a built-in definition through the user-definition path
- **THEN** the registry SHALL reject the replacement unless a future explicit override policy allows it

### Requirement: Registry SHALL be extension-ready for user-defined SubAgents
The system SHALL separate built-in definitions from future tenant/workspace
user-defined definitions through provider or store interfaces. MVP runtime
execution SHALL use one resolution and validation path regardless of definition
source, while public CRUD APIs and UI for custom definitions remain out of
scope.

#### Scenario: User definition store can be injected
- **WHEN** the SubAgent registry is initialized
- **THEN** it SHALL accept an optional user-definition store/provider in addition to the built-in provider

#### Scenario: User definition uses the same validation path
- **WHEN** a user-defined SubAgent definition is loaded from the store/provider
- **THEN** the registry SHALL validate it with the same schema, lifecycle, tool, permission, isolation, and output-contract checks used for built-in definitions

#### Scenario: Unsupported user definition is rejected
- **WHEN** a user-defined SubAgent requests custom model routing, skills, MCP tools, mutating tools, non-fresh context, non-shared workspace, memory, or nested delegation during the MVP
- **THEN** the registry SHALL reject or disable the definition with a structured validation error

#### Scenario: Duplicate definitions are not silently shadowed
- **WHEN** two definition sources provide the same SubAgent name and version
- **THEN** the registry SHALL reject the duplicate or mark the user-sourced definition invalid unless a future explicit override policy allows shadowing

### Requirement: Main agents SHALL delegate by structured DelegationSpec
The system SHALL accept SubAgent delegation through a structured
`DelegationSpec` that includes task identity, parent thread/session identity,
agent name, objective, background, mode context, scope, constraints, allowed and
forbidden actions, evidence requirements, budget, and return policy.

#### Scenario: Main agent delegates to a named SubAgent
- **WHEN** a main agent invokes `delegate_to_subagent` with a valid agent name and objective
- **THEN** the delegation manager SHALL create a SubAgent run and pass a validated `DelegationSpec` to the runtime

#### Scenario: Unknown SubAgent is rejected
- **WHEN** a main agent delegates to an unknown SubAgent name
- **THEN** the delegation manager SHALL return a structured failed result that identifies the unknown SubAgent

#### Scenario: Delegation records definition identity
- **WHEN** the delegation manager resolves a SubAgent definition
- **THEN** the resulting run SHALL record the resolved name, version, source, and owner scope used for that run

### Requirement: SubAgent context SHALL be fresh by default
The SubAgent runtime SHALL run MVP SubAgents with fresh context, no parent chat
history, and no persistent memory manager. The SubAgent input SHALL consist of
its system prompt, runtime environment summary, effective policy summary, output
contract, and the `DelegationSpec`.

#### Scenario: SubAgent does not load parent session history
- **WHEN** a SubAgent run starts from a parent session with existing messages
- **THEN** the SubAgent SHALL NOT load those parent session messages into its model input

#### Scenario: SubAgent receives only delegated task context
- **WHEN** the runtime builds the SubAgent input
- **THEN** the input SHALL include the `DelegationSpec` and SHALL NOT include the main agent scratchpad or previous tool output logs

#### Scenario: SubAgent uses its definition system prompt
- **WHEN** a SubAgent `SWEAgent` is created
- **THEN** its controlling system prompt SHALL come from the SubAgent definition, runtime safety contract, effective policy summary, output contract, and bounded environment summary
- **AND** it SHALL NOT rely on appending the SubAgent prompt to the normal main-agent system prompt

#### Scenario: Persistent memory is disabled
- **WHEN** a SubAgent `SWEAgent` is created
- **THEN** it SHALL be created with persistent memory management disabled and SHALL NOT register `memory_search`

#### Scenario: Workspace skills are disabled
- **WHEN** a SubAgent `SWEAgent` is created
- **THEN** workspace skills SHALL NOT be loaded and skill-provided tools or hook handlers SHALL NOT be registered for that SubAgent

### Requirement: SubAgents SHALL inherit the parent model
The SubAgent runtime SHALL use the parent/main agent's active model
configuration for all MVP SubAgent runs.

#### Scenario: SubAgent definition declares model inheritance
- **WHEN** a built-in SubAgent definition is resolved
- **THEN** its model behavior SHALL inherit the parent/main agent model configuration

#### Scenario: Runtime does not route to a SubAgent-specific model
- **WHEN** a SubAgent run starts
- **THEN** the runtime SHALL NOT select a different provider or model for that run

### Requirement: Effective permissions SHALL never exceed parent permissions
The delegation manager SHALL compute an effective permission policy from the
parent context, SubAgent definition, runtime policy, and workspace policy. Deny
rules SHALL take precedence over allow rules.

#### Scenario: Parent denial remains denied
- **WHEN** the parent context denies a tool that the SubAgent definition allows
- **THEN** the effective policy SHALL deny that tool

#### Scenario: SubAgent denial remains denied
- **WHEN** the SubAgent definition denies a tool that the parent context allows
- **THEN** the effective policy SHALL deny that tool

#### Scenario: Approval cannot widen SubAgent policy
- **WHEN** a readonly SubAgent attempts a tool call denied by effective policy
- **THEN** the runtime SHALL deny the call before hook execution or approval replay and SHALL NOT create a user approval request

### Requirement: Readonly SubAgents SHALL be prevented from mutating workspace state
Readonly SubAgents SHALL NOT be able to use mutating file tools, mutating shell
commands, deployment commands, migration commands, or nested delegation.

#### Scenario: Write file tool is denied
- **WHEN** a readonly SubAgent attempts to call `write_file`
- **THEN** the tool call SHALL be denied by runtime policy

#### Scenario: Edit file tool is denied
- **WHEN** a readonly SubAgent attempts to call `edit_file`
- **THEN** the tool call SHALL be denied by runtime policy

#### Scenario: Mutating shell command is denied
- **WHEN** a readonly SubAgent attempts to run a shell command containing output redirection, destructive file operations, formatter write flags, migration commands, or deployment commands
- **THEN** the shell tool call SHALL be denied by runtime policy

#### Scenario: Readonly shell command is allowed
- **WHEN** a readonly SubAgent runs an allowed read-only command such as `pwd`, `ls`, `rg`, `grep`, `sed`, `git status`, `git diff`, `git grep`, `git log`, or `git show`
- **THEN** the shell tool call SHALL be allowed if no denied pattern matches

#### Scenario: Test execution is deferred
- **WHEN** a readonly MVP SubAgent attempts to run `pytest`, `npm test`, coverage, snapshot, or similar test commands that may write cache or result files
- **THEN** the shell tool call SHALL be denied or blocked and the SubAgent SHALL report the command as a recommended verification step instead

#### Scenario: Task progress mutation is denied
- **WHEN** a readonly SubAgent attempts to call `update_task_progress`, `set_user_timezone`, `copy_file_to_static`, or `get_token_usage`
- **THEN** the tool call SHALL be unavailable or denied because these tools are outside the MVP SubAgent allowlist

#### Scenario: SubAgent cannot delegate again
- **WHEN** a SubAgent attempts to call `delegate_to_subagent`
- **THEN** the tool call SHALL be denied by runtime policy

### Requirement: Main-agent-only delegation tool SHALL return compact results
The system SHALL expose `delegate_to_subagent` only to main-agent contexts and
SHALL return a compact structured result to the calling agent instead of
streaming SubAgent output directly to the user.

#### Scenario: Main agent can see delegation tool
- **WHEN** a normal main `SWEAgent` toolkit is created
- **THEN** `delegate_to_subagent` SHALL be available when delegation is enabled for that context

#### Scenario: SubAgent cannot see delegation tool
- **WHEN** a SubAgent `SWEAgent` toolkit is created
- **THEN** `delegate_to_subagent` SHALL NOT be registered in that toolkit

#### Scenario: SubAgent toolkit contains only MVP read tools
- **WHEN** a built-in readonly SubAgent `SWEAgent` toolkit is created
- **THEN** it SHALL include only the effective allowed built-ins such as `read_file`, `grep_search`, `glob_search`, `execute_shell_command`, and `get_current_time`
- **AND** it SHALL NOT include write, edit, task-progress, memory, skill, MCP, static-copy, timezone, or token-usage tools

#### Scenario: Raw SubAgent transcript is not returned
- **WHEN** a SubAgent completes a delegated task
- **THEN** `delegate_to_subagent` SHALL return the validated `AgentResult` and SHALL NOT return the full raw transcript by default

### Requirement: SubAgent results SHALL conform to AgentResult
The runtime SHALL validate SubAgent final output as `AgentResult` with task id,
run id, agent name, status, summary, findings, relevant files, risks,
recommendations, open questions, suggested next steps, metrics, optional
artifacts, and optional errors. The runtime SHALL prefer existing
`SWEAgent.reply(..., structured_model=AgentResult)` support when available and
SHALL still validate the returned content with the `AgentResult` model.

#### Scenario: Valid AgentResult is accepted
- **WHEN** the SubAgent final assistant output contains valid `AgentResult` JSON
- **THEN** the runtime SHALL return it with the current run id and runtime metrics

#### Scenario: Invalid JSON becomes structured failure or partial result
- **WHEN** the SubAgent final assistant output cannot be validated as `AgentResult`
- **THEN** the runtime SHALL either request one JSON repair attempt or return a runtime-generated structured `partial` or `failed` result

#### Scenario: Permission denial can produce blocked result
- **WHEN** the delegated task requires a forbidden action and no readonly alternative exists
- **THEN** the SubAgent result SHALL be `blocked` or `partial` with an error or open question explaining the denied capability

### Requirement: SubAgent runs SHALL be recorded
The system SHALL record SubAgent run identity, parent identity, agent name,
agent version, definition source, owner scope, delegation spec, effective
policy, status transitions, final result, and runtime errors through a run-store
interface.

#### Scenario: Run status transitions are recorded
- **WHEN** a SubAgent run is created, started, and completed
- **THEN** the run store SHALL record queued, running, and terminal status updates

#### Scenario: Runtime error is recorded
- **WHEN** SubAgent execution raises an unrecoverable runtime error
- **THEN** the run store SHALL record failed status and the structured error returned to the caller

#### Scenario: MVP run store is local app state
- **WHEN** the MVP run store persists a run
- **THEN** it SHALL write through a replaceable run-store interface to tenant/workspace-local app state and SHALL NOT write records into a delegated repository checkout

### Requirement: MVP SubAgents SHALL use shared workspace readonly isolation
The MVP runtime SHALL execute built-in SubAgents in the same workspace directory
as the parent agent with readonly effective permissions.

#### Scenario: Shared workspace is used for readonly research
- **WHEN** `plan-researcher`, `risk-reviewer`, or `test-surface-analyzer` starts
- **THEN** the runtime SHALL set the SubAgent workspace to the parent workspace directory

#### Scenario: Worktree workers are out of scope
- **WHEN** a delegation requests a mutating worker or git worktree isolation
- **THEN** the MVP runtime SHALL reject or fail the delegation as unsupported

#### Scenario: MCP tools are out of scope
- **WHEN** a delegation or SubAgent definition requests MCP tools
- **THEN** the MVP runtime SHALL reject or fail the delegation as unsupported
