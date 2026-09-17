## Why

The current runtime can run a user-facing `SWEAgent`, but it has no first-class
way for the main agent to delegate bounded read-only research to an isolated
worker and receive structured evidence without polluting the main conversation
context. This is needed before Plan Mode, parallel review, and evidence-driven
Goal Mode can be implemented safely.

## What Changes

- Add a SubAgent runtime capability for single, fresh-context delegation from a
  main agent to a named read-only SubAgent.
- Introduce structured SubAgent definitions, delegation specs, run records, and
  `AgentResult` output validation.
- Add built-in readonly SubAgents for repository research, risk review, and
  test-surface analysis.
- Make the registry and definition model extension-ready for future
  tenant/workspace-scoped user-defined SubAgents without enabling broad custom
  execution capabilities in the MVP.
- Enforce SubAgent permissions through runtime policy, including tool
  allowlists, readonly mutation denial, shell command allowlists, and nested
  delegation denial.
- Add a main-agent-only `delegate_to_subagent` built-in tool that returns a
  compact structured result to the caller instead of streaming directly to the
  user.
- Keep SubAgents on the same model configuration as the parent/main agent for
  this MVP.
- Disable workspace skills, persistent memory, task-progress tools, and MCP
  clients for MVP SubAgent runs unless a later design explicitly allows them.
- Keep the MVP scoped to shared-workspace readonly execution; Plan Mode,
  parallel fan-out, Goal Mode, worktree workers, external APIs, and database
  persistence, and public custom-SubAgent CRUD/UI are deferred.

## Capabilities

### New Capabilities

- `subagent-runtime`: Defines single-run SubAgent delegation, definitions,
  permission enforcement, structured result validation, and run recording.

### Modified Capabilities

- None.

## Impact

- Backend runtime:
  - `src/swe/app/subagents/` for models, registry, permissions, run store,
    definition store interfaces, runtime, and delegation manager
  - `src/swe/agents/tools/` for the `delegate_to_subagent` tool
  - `src/swe/agents/react_agent.py` for controlled built-in tool registration
    plus SubAgent system-prompt override and skill disabling
  - `src/swe/agents/tool_guard_mixin.py` for hard SubAgent policy enforcement
    before hooks, approvals, and normal guard decisions
- Existing user-facing chat behavior should remain unchanged.
- Tests:
  - SubAgent model, registry, permission, runtime, and run-store unit tests
  - Definition-store tests for built-in/user-defined namespace separation and
    validation
  - Tool guard tests proving readonly SubAgents cannot write files or run
    mutating shell commands
  - Integration-style tests proving a main agent can invoke a readonly SubAgent
    and receive a valid `AgentResult`
