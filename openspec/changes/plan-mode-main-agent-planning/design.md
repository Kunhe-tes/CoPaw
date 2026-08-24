## Context

The runtime already has tenant-scoped Agent workspaces, `ChatSpec.meta` for extensible chat metadata, Console channel metadata forwarding, a Main Agent `request_context`, SubAgent readonly permission models, and ToolGuard hard-denial hooks. Plan Mode should reuse these seams instead of creating a parallel runtime.

Current gaps:

- `/console/chat` request parsing drops extra fields such as `mode` and `plan_interaction_response`.
- Plan Mode state is not persisted per chat.
- Main Agent tool registration and ToolGuard enforcement do not have a planning readonly policy.
- Existing approval cards represent ToolGuard approvals, not Proposed Plan review.
- Proposed Plans are not durable, so execution cannot safely reference a backend-owned plan artifact.

## Goals / Non-Goals

**Goals:**

- Make Plan Mode an explicit per-chat state entered by a toggle or `/plan`.
- Persist Plan Mode state in `ChatSpec.meta.plan_mode_enabled`.
- Send each Console chat turn with explicit `mode="plan"` or `mode="normal"`.
- Apply a Planning Readonly Policy to the Main Agent only while a turn is in Plan Mode.
- Register only available planning tools in Plan Mode and hard-deny forbidden calls as a fallback.
- Add structured Plan Interaction Cards through tool metadata, not assistant text parsing.
- Persist Proposed Plans under the current tenant Agent workspace `plans/` directory.
- Support `revise`, `execute`, and `exit_plan` review decisions.

**Non-Goals:**

- No automatic default `plan-researcher` or silent Main Agent mode switching.
- No custom SubAgent Definition CRUD or UI.
- No async SubAgentRun create, observe, or collect tools.
- No MySQL-backed Proposed Plan store in this change.
- No changes to the existing ToolGuard approval contract beyond avoiding UI/card conflation.

## Decisions

### Decision: Plan Mode state lives in `ChatSpec.meta`

Use `ChatSpec.meta.plan_mode_enabled` instead of adding a first-class `ChatSpec` field.

Rationale:

- `meta` is already persisted by the chat repository and returned to the frontend.
- It avoids broad schema churn for chat APIs and preserves backward compatibility.
- The state is per chat, which matches the domain language in `CONTEXT.md`.

Alternative considered: add `ChatSpec.plan_mode_enabled`. Rejected because the existing extensibility point is sufficient and a first-class field has broader API impact.

### Decision: Console chat metadata is preserved end to end

`/console/chat` SHALL preserve extra request metadata into `native_payload["meta"]`, and `ConsoleChannel.build_agent_request_from_native` SHALL pass it through `request.channel_meta`.

Rationale:

- `AgentRunner._create_agent_for_query` can derive request context from one place.
- It keeps planning card responses as normal chat turns with structured metadata.

The route may short-circuit `exit_plan` review submissions after persisting the decision and disabling Plan Mode, because that action intentionally exits planning without executing or asking the model to acknowledge.

### Decision: Proposed Plans are backend-owned workspace JSON records

Persist Proposed Plans under:

```text
<workspace_dir>/plans/<chat_id>/<plan_id>.json
```

Each record stores the plan payload, `chat_id`, `session_id`, `turn_id`, creator metadata, timestamps, status, and review decisions.

Rationale:

- This matches the existing workspace-local storage style for `chats.json`, `jobs.json`, sessions, memory, and SubAgent local state.
- It satisfies tenant/source isolation because `workspace_dir` is already resolved from the runtime tenant scope.
- Backend-generated `plan_id` prevents frontend-supplied plan snapshots from becoming the execution source of truth.

Trade-off:

- Kubernetes deployments must ensure the tenant workspace directory is shared or sticky in the same way as current chat/session workspace files. If a later deployment needs cross-pod non-shared storage, the store interface can grow a Redis or MySQL implementation without changing the tool contract.

### Decision: Plan review uses backend plan lookup

The frontend submits `plan_id`, `decision`, and optional `feedback`. It SHALL NOT send a plan snapshot back for execution. For `execute`, the backend reads the persisted plan and injects a compact accepted-plan context into the next normal turn. For `revise`, the feedback remains a Plan Interaction Response in Plan Mode. For `exit_plan`, the backend records the decision and disables Plan Mode without starting an Agent run by default.

Rationale:

- Prevents stale or tampered frontend plan payloads from driving execution.
- Cleanly separates "execute this accepted plan" from "approve a dangerous tool call".

### Decision: Planning tools are normal Main Agent built-ins

Add `ask_plan_clarification` and `submit_proposed_plan` as built-in tools available in all modes. Plan Mode controls permissions, not tool existence. In normal mode these tools may render cards, but they do not automatically enable or disable Plan Mode.

Rationale:

- The Main Agent can ask structured planning questions without requiring Plan Mode.
- The same tool output shape can be reused for normal-mode planning UX.

### Decision: Planning Readonly Policy filters toolkit and hard-denies calls

In Plan Mode, `SWEAgent._create_toolkit` registers only allowed tools:

- `read_file`
- `grep_search`
- `glob_search`
- `get_current_time`
- readonly `execute_shell_command`
- readonly `delegate_to_subagent` when delegation is enabled
- planning interaction tools

It excludes `write_file`, `edit_file`, `copy_file_to_static`, `update_task_progress`, mutating shell commands, tests, deployment, and migration commands. `ToolGuardMixin` also checks the Planning Readonly Policy before hook execution or approval replay.

Rationale:

- The system prompt and toolkit reflect actual available capabilities.
- ToolGuard remains the defense-in-depth layer if a tool appears through config drift, MCP, or future registration changes.

### Decision: Plan Mode prompt suppresses task-progress requirements

When a turn is in Plan Mode, the system prompt SHALL NOT instruct the model to call `update_task_progress`, even if source-level task progress is enabled.

Rationale:

- The tool is intentionally unavailable in Plan Mode.
- Prompt/tool mismatch causes predictable tool-call failures.

### Decision: `/plan` is a frontend shortcut with persistence

- `/plan <text>` persists Plan Mode on the current chat, strips the prefix, then sends `<text>` with `mode="plan"`.
- `/plan` alone persists Plan Mode and does not start an Agent request.
- If the current UI state has no persisted ChatSpec, the frontend creates or resolves one before persisting Plan Mode state.

Rationale:

- Plan Mode is explicit and durable.
- Empty `/plan` should change state, not create an empty model turn.

## Risks / Trade-offs

- Local JSON plan storage on non-shared Kubernetes volumes can lose cross-pod visibility -> rely on the same workspace persistence assumptions as existing chat/session files and keep a store interface for future backend replacement.
- Plan cards could be confused with ToolGuard approval cards -> use a distinct `PlanReviewCard` code and `plan_interaction_card` metadata namespace.
- A stale frontend may submit an old `plan_id` -> backend validates chat ownership and plan status before accepting decisions.
- Toolkit filtering alone can miss future tool paths -> ToolGuard hard policy rechecks every call, including hook-updated input and approval replay.
- `/plan` on a brand-new empty chat requires a persisted chat identity -> frontend must create or resolve the chat before saving Plan Mode state.
- `exit_plan` without an Agent run may feel silent -> frontend should update UI state immediately and may append a local/system-visible audit marker if product design wants one later.

## Migration Plan

1. Add backend models, store, and service with JSON persistence under `workspace_dir/plans`.
2. Add metadata passthrough and Plan Mode state updates while preserving normal chat behavior.
3. Add planning tools and card metadata.
4. Add Planning Readonly Policy toolkit filtering and ToolGuard hard denial.
5. Add frontend Plan Mode toggle, `/plan`, and Plan Interaction Card rendering.
6. Add tests before implementation for backend state/policy/store behavior and frontend state/card flows.

Rollback is straightforward: disable frontend entry points and planning tool registration. Existing chat metadata with `plan_mode_enabled` and `plans/` JSON files can remain inert.

## Open Questions

- Whether `exit_plan` should append an audit message to persisted chat history or remain a pure state transition plus plan decision record.
- Whether Proposed Plan records need retention cleanup in the first implementation or can follow existing workspace file retention policy.
