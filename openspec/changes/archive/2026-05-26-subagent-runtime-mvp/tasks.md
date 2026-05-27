## 1. Models and Built-in Definitions

- [x] 1.1 Create `src/swe/app/subagents/` module structure with module docstrings and exports.
- [x] 1.2 Add Pydantic models for `SubAgentDefinition`, `DelegationSpec`, `AgentResult`, `EvidenceRef`, budgets, isolation, lifecycle, registration metadata, and run status.
- [x] 1.3 Add registration metadata fields for schema version, definition source (`builtin` or future `user`), owner scope, enabled state, timestamps, and optional creator identity.
- [x] 1.4 Add validation that rejects nested delegation, unsupported MVP isolation modes, missing prompts, invalid built-in tool names, MCP requests, mutable/test-execution capabilities, duplicate definitions, and attempts to override built-ins.
- [x] 1.5 Define a `SubAgentDefinitionStore`/provider interface for future tenant/workspace user-defined definitions while keeping public CRUD/API/UI out of this MVP.
- [x] 1.6 Define built-in `plan-researcher`, `risk-reviewer`, and `test-surface-analyzer` definitions with inherited model behavior, fresh context, shared workspace, no memory, no skills, no MCP, builtin source metadata, and readonly permissions.
- [x] 1.7 Add unit tests for model defaults, registration metadata, validation errors, built-in definition validity, and MVP rejection of unsupported user-defined definitions.

## 2. Registry and Run Store

- [x] 2.1 Implement `AgentRegistry` with ordered built-in and user-definition providers, register, resolve latest, get by version, list, source/owner filtering, duplicate detection, and no silent shadowing.
- [x] 2.2 Implement an injectable `SubAgentRunStore` interface with create, mark running, finish, fail, cancel, and get operations.
- [x] 2.3 Add an MVP tenant/workspace-local app-state run-store implementation that records spec, resolved definition name/version/source/owner, effective policy, status, result, timestamps, and errors without writing records into delegated repository checkouts.
- [x] 2.4 Add unit tests for registry lookup, user-provider injection, duplicate handling, validation, status transitions, and runtime error recording.

## 3. Permission Engine and Tool Policy

- [x] 3.1 Implement effective permission policy composition with deny precedence and parent/sub/runtime/workspace intersection.
- [x] 3.2 Implement builtin tool allowlist filtering for SubAgent-created `SWEAgent` instances by copying `AgentProfileConfig.tools.builtin_tools` and enabling only effective allowed tools.
- [x] 3.3 Implement a SubAgent-safe `SWEAgent` construction path that supports a definition-driven system prompt override and disables workspace skills, persistent memory, task tracker/progress tools, static copy, timezone mutation, token usage, and MCP clients while preserving normal-chat defaults.
- [x] 3.4 Implement readonly policy checks for file tools, nested delegation, MCP default denial, test-execution denial, and shell allowlist/denied-pattern authorization.
- [x] 3.5 Wire SubAgent effective policy into `SWEAgent` request context so `ToolGuardMixin` can enforce it before hooks, approvals, normal guard checks, and tool execution.
- [x] 3.6 Add tests proving readonly SubAgents deny `write_file`, `edit_file`, nested delegation, mutating shell commands, test commands, task-progress/state tools, skill tools, and MCP tools while allowing read-only file/search/shell commands.

## 4. SubAgent Runtime

- [x] 4.1 Implement `SubAgentRuntime` that directly creates a fresh `SWEAgent` without loading parent session history or persistent memory manager.
- [x] 4.2 Build the SubAgent controlling system prompt from the definition prompt, runtime safety contract, environment summary, effective policy summary, and output contract; pass the `DelegationSpec` as the single delegated user task.
- [x] 4.3 Execute the SubAgent with timeout and budget handling, using existing `SWEAgent.reply(..., structured_model=AgentResult)` support where possible, then extract final assistant output.
- [x] 4.4 Implement `AgentResult` JSON extraction, validation, one repair attempt, and structured partial/failed fallback.
- [x] 4.5 Add runtime tests for fresh context, inherited model behavior, no skills/MCP/memory, valid result acceptance, invalid output fallback, and failure recording.

## 5. Delegation Manager and Tool Integration

- [x] 5.1 Implement `DelegationManager` that validates caller context, resolves definitions from registry providers, computes effective policy, records resolved definition identity/source/owner in the run lifecycle, and invokes runtime.
- [x] 5.2 Add `delegate_to_subagent` built-in tool with main-agent-only availability and compact `AgentResult` return.
- [x] 5.3 Ensure SubAgent-created toolkits do not register `delegate_to_subagent`.
- [x] 5.4 Add tests for successful main-agent delegation, unknown SubAgent failure, and SubAgent nested delegation denial.

## 6. Integration Verification

- [x] 6.1 Add an integration-style test where a main agent delegates readonly repository research and receives a valid `AgentResult`.
- [x] 6.2 Add a regression test proving SubAgent execution does not append raw SubAgent transcript content to the parent session history.
- [x] 6.3 Add a regression test proving user-facing normal chat behavior is unchanged when no delegation tool is used.
- [x] 6.4 Run focused test suites with `venv/bin/python -m pytest` for subagents, tool guard, and runner integration coverage.
