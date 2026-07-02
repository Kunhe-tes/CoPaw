## ADDED Requirements

### Requirement: Plan Mode SHALL be explicit and persisted per chat
The system SHALL expose Plan Mode as a user-visible state on a chat session and SHALL persist the state in `ChatSpec.meta.plan_mode_enabled`. The system SHALL NOT enter Plan Mode by silent Main Agent inference.

#### Scenario: Toggle enables Plan Mode
- **WHEN** the user turns on the Plan Mode toggle for a chat
- **THEN** the system SHALL persist `plan_mode_enabled=true` in that chat's metadata
- **AND** subsequent chat requests for that chat SHALL send `mode="plan"`

#### Scenario: Toggle disables Plan Mode
- **WHEN** the user turns off the Plan Mode toggle for a chat
- **THEN** the system SHALL persist `plan_mode_enabled=false` in that chat's metadata
- **AND** subsequent chat requests for that chat SHALL send `mode="normal"`

#### Scenario: Plan Mode initializes from chat metadata
- **WHEN** the frontend loads a chat whose metadata contains `plan_mode_enabled=true`
- **THEN** the Plan Mode toggle SHALL render enabled
- **AND** the next request from that chat SHALL run in Plan Mode unless the user disables it first

#### Scenario: Normal chat remains unchanged
- **WHEN** a chat has no `plan_mode_enabled` metadata and the request does not send `mode="plan"`
- **THEN** the request SHALL run with normal Main Agent permissions and existing chat behavior

### Requirement: `/plan` shortcut SHALL control Plan Mode
The frontend SHALL support `/plan` as a shortcut for explicit Plan Mode entry.

#### Scenario: Slash plan with text sends a planning turn
- **WHEN** the user submits `/plan investigate this bug`
- **THEN** the frontend SHALL persist Plan Mode enabled for the current chat
- **AND** it SHALL send `investigate this bug` as the user message with `mode="plan"`

#### Scenario: Slash plan without text only enters Plan Mode
- **WHEN** the user submits exactly `/plan` with no remaining text
- **THEN** the frontend SHALL persist Plan Mode enabled for the current chat
- **AND** it SHALL NOT start a model request

#### Scenario: Slash plan while already enabled strips prefix
- **WHEN** Plan Mode is already enabled and the user submits `/plan revise the scope`
- **THEN** the frontend SHALL send `revise the scope` with `mode="plan"`

### Requirement: Console requests SHALL preserve planning metadata
The Console chat pipeline SHALL preserve `mode`, `plan_interaction_response`, and related planning metadata from the frontend request into `AgentRequest.channel_meta` and Main Agent request context.

#### Scenario: Mode reaches Agent request context
- **WHEN** `/console/chat` receives a request with `mode="plan"`
- **THEN** the Console route and channel SHALL preserve the mode in request metadata
- **AND** `AgentRunner` SHALL inject the resolved planning mode into `SWEAgent` request context

#### Scenario: Plan interaction response reaches Agent request context
- **WHEN** `/console/chat` receives `plan_interaction_response`
- **THEN** the Console route and channel SHALL preserve the response metadata
- **AND** `AgentRunner` SHALL expose it to the Main Agent request context

#### Scenario: Unknown request metadata is not dropped
- **WHEN** a Console request includes metadata fields outside the base AgentRequest schema
- **THEN** the route SHALL preserve those fields unless they violate validation or security rules

### Requirement: Main Agent SHALL use Planning Readonly Policy in Plan Mode
The Main Agent SHALL run under a Planning Readonly Policy while a turn is resolved as Plan Mode. The policy SHALL allow repository reading, search, current-time lookup, readonly shell commands, planning interaction tools, and readonly SubAgent delegation when delegation is enabled. It SHALL forbid workspace mutation, tests, deployment, migration, task progress mutation, static copy, and mutating shell.

#### Scenario: Plan Mode toolkit excludes mutating tools
- **WHEN** a Main Agent toolkit is created for a Plan Mode turn
- **THEN** `write_file`, `edit_file`, `copy_file_to_static`, `update_task_progress`, `set_user_timezone`, and `get_token_usage` SHALL NOT be registered

#### Scenario: Plan Mode toolkit includes readonly tools
- **WHEN** a Main Agent toolkit is created for a Plan Mode turn
- **THEN** `read_file`, `grep_search`, `glob_search`, `get_current_time`, and readonly `execute_shell_command` SHALL be available when enabled by the agent config

#### Scenario: Readonly delegation is available when enabled
- **WHEN** Plan Mode is active and the request context enables SubAgent delegation
- **THEN** `delegate_to_subagent` SHALL be available as readonly delegation
- **AND** delegated SubAgent runs SHALL remain bounded by existing SubAgent readonly policy

#### Scenario: Mutating shell is denied
- **WHEN** a Main Agent in Plan Mode calls `execute_shell_command` with redirection, destructive file operations, formatter writes, migration commands, deployment commands, or test commands
- **THEN** the call SHALL be denied before execution

#### Scenario: Tests are deferred in Plan Mode
- **WHEN** a Main Agent in Plan Mode attempts to run `pytest`, `npm test`, coverage, snapshot, or similar test commands
- **THEN** the shell call SHALL be denied
- **AND** the Main Agent SHALL report the command as a verification step instead

#### Scenario: Hard policy runs before approvals
- **WHEN** a Main Agent in Plan Mode attempts a forbidden tool call
- **THEN** ToolGuard SHALL return a policy denial before hook execution, ToolGuard approval creation, or approval replay

### Requirement: Plan Mode prompt SHALL match available tools
The Main Agent system prompt for Plan Mode SHALL describe planning constraints and SHALL NOT instruct the model to use unavailable mutating tools.

#### Scenario: Task progress prompt is suppressed
- **WHEN** source-level task progress is enabled and the Main Agent turn is in Plan Mode
- **THEN** the system prompt SHALL NOT require `update_task_progress`

#### Scenario: Normal prompt remains unchanged
- **WHEN** the Main Agent turn is not in Plan Mode
- **THEN** existing source-level task progress prompt behavior SHALL remain unchanged

### Requirement: Planning interaction tools SHALL emit structured cards
The Main Agent SHALL have `ask_plan_clarification` and `submit_proposed_plan` tools that emit structured Plan Interaction Card metadata. The frontend SHALL render planning cards only from validated tool metadata and SHALL NOT parse free-form assistant text JSON as planning cards.

#### Scenario: Clarification card supports single choice
- **WHEN** the Main Agent calls `ask_plan_clarification` with `kind="single_choice"`
- **THEN** the frontend SHALL render a Planning Clarification Card with mutually exclusive options

#### Scenario: Clarification card supports multiple choice
- **WHEN** the Main Agent calls `ask_plan_clarification` with `kind="multi_choice"`
- **THEN** the frontend SHALL render a Planning Clarification Card that accepts multiple selected options

#### Scenario: Clarification card supports text input
- **WHEN** the Main Agent calls `ask_plan_clarification` with `kind="text"`
- **THEN** the frontend SHALL render a Planning Clarification Card that accepts free-form text

#### Scenario: Clarification response is next chat turn
- **WHEN** the user submits a Planning Clarification Card response
- **THEN** the frontend SHALL submit it as the next user turn with `plan_interaction_response` metadata

#### Scenario: Planning tools work outside Plan Mode
- **WHEN** the Main Agent calls a planning interaction tool during normal mode
- **THEN** the frontend SHALL render the card
- **AND** the card itself SHALL NOT enable or disable Plan Mode unless the user action explicitly does so

### Requirement: Proposed Plans SHALL be persisted by the backend
The backend SHALL generate `plan_id` values and persist Proposed Plans under the current tenant Agent workspace `plans/` directory. The frontend SHALL NOT provide the authoritative `plan_id` or return plan snapshots for execution.

#### Scenario: Proposed Plan is saved on tool call
- **WHEN** the Main Agent calls `submit_proposed_plan`
- **THEN** the backend SHALL generate a `plan_id`
- **AND** it SHALL persist the Proposed Plan before returning the Plan Review Card metadata

#### Scenario: Proposed Plan includes required fields
- **WHEN** a Proposed Plan is persisted
- **THEN** it SHALL include `plan_id`, `title`, `summary`, `steps`, `risks`, `verification`, `open_questions`, and `confidence`

#### Scenario: Proposed Plan is scoped to chat and workspace
- **WHEN** a Proposed Plan is saved
- **THEN** it SHALL be stored under `<workspace_dir>/plans/<chat_id>/<plan_id>.json`
- **AND** later review submissions SHALL only resolve plans belonging to the same chat and tenant workspace

#### Scenario: Frontend snapshot is ignored for execution
- **WHEN** the frontend submits a Plan Review Decision
- **THEN** the backend SHALL use `plan_id` to load the persisted Proposed Plan
- **AND** it SHALL ignore any frontend-supplied plan snapshot for execution

### Requirement: Plan Review Card SHALL support revise, execute, and exit actions
The frontend SHALL render Proposed Plan review through a distinct Plan Review Card with actions for continuing modification, executing the plan, and exiting Plan Mode without execution.

#### Scenario: Revise keeps Plan Mode
- **WHEN** the user chooses `revise` on a Plan Review Card
- **THEN** the frontend SHALL submit the user's feedback with `plan_interaction_response`
- **AND** the chat SHALL remain in Plan Mode

#### Scenario: Execute exits Plan Mode and runs normal turn
- **WHEN** the user chooses `execute` on a Plan Review Card
- **THEN** the backend SHALL record the Plan Review Decision
- **AND** the chat SHALL persist `plan_mode_enabled=false`
- **AND** the next Agent turn SHALL run in normal mode with the persisted Proposed Plan available as accepted plan context

#### Scenario: Exit plan mode does not execute
- **WHEN** the user chooses `exit_plan` on a Plan Review Card
- **THEN** the backend SHALL record the Plan Review Decision when a valid `plan_id` is provided
- **AND** the chat SHALL persist `plan_mode_enabled=false`
- **AND** the system SHALL NOT start a Main Agent execution request by default

#### Scenario: Review card is not ToolGuard approval
- **WHEN** a Proposed Plan review card is rendered
- **THEN** it SHALL use a distinct card code and metadata namespace from ToolGuard approval cards

#### Scenario: Submitted review card is disabled
- **WHEN** the user submits a Plan Review Decision
- **THEN** the frontend SHALL render the card as submitted or disabled to prevent duplicate decisions

### Requirement: Plan Mode transitions SHALL be consistent across requests
The backend SHALL resolve request mode from explicit request metadata and persisted chat metadata, and SHALL persist state transitions caused by planning actions.

#### Scenario: Explicit plan request enables planning
- **WHEN** a request sends `mode="plan"`
- **THEN** the backend SHALL treat the turn as Plan Mode
- **AND** it SHALL persist `plan_mode_enabled=true` for the chat

#### Scenario: Execute closes planning before normal execution
- **WHEN** a valid `execute` Plan Review Decision is submitted
- **THEN** the backend SHALL close Plan Mode before constructing the Main Agent for the next turn

#### Scenario: Revise preserves planning
- **WHEN** a valid `revise` Plan Review Decision is submitted
- **THEN** the backend SHALL keep `plan_mode_enabled=true`
- **AND** the Main Agent SHALL continue under Planning Readonly Policy

#### Scenario: Manual toggle can exit planning
- **WHEN** the user manually disables the Plan Mode toggle
- **THEN** the next request SHALL run with `mode="normal"` and normal Main Agent permissions

### Requirement: Existing SubAgent runtime behavior SHALL remain unchanged
Plan Mode SHALL preserve the existing synchronous `delegate_to_subagent` runtime and readonly SubAgent policy. It SHALL NOT introduce automatic default planning delegation or async SubAgent run lifecycle tools.

#### Scenario: No automatic plan researcher
- **WHEN** a chat enters Plan Mode
- **THEN** the system SHALL NOT automatically create or invoke a `plan-researcher` SubAgent run

#### Scenario: Existing synchronous delegation still works
- **WHEN** the Main Agent explicitly calls `delegate_to_subagent` in Plan Mode and delegation is enabled
- **THEN** the existing synchronous SubAgent runtime SHALL execute according to its readonly policy and return compact results

#### Scenario: Async SubAgent APIs are not introduced
- **WHEN** this change is implemented
- **THEN** no async SubAgentRun creation, observation, or collection tools SHALL be added
