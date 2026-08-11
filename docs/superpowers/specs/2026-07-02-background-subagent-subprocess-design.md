# Background SubAgent Subprocess Design

## Context

Swe already has a synchronous readonly SubAgent MVP: the Main Agent can call `delegate_to_subagent`, the runtime creates a fresh-context `SWEAgent`, effective permissions are narrowed, and the SubAgent returns a compact `AgentResult`.

The next step is internal background execution. The goal is not to create user-defined SubAgent definitions or a public UI. The goal is to replace the synchronous SubAgent tool surface with background-only Main Agent tools that can start, observe, fetch, and cancel Background SubAgent Runs while keeping runtime isolation and avoiding a shared JSON write bottleneck.

## Decisions

- Use a local subprocess worker as the first Background SubAgent execution backend.
- Keep the scope internal to Main Agent tools; do not add public HTTP APIs or Console UI in this phase.
- Store each Background SubAgent Run in its own JSON file.
- Use the run JSON file as the only result protocol. `stderr` is diagnostic only; `stdout` is not a protocol.
- Enforce a fixed concurrency limit per `tenant_id + agent_id`. When the limit is reached, `start_subagent` returns blocked and does not create a run file.
- Use process-group cancellation: `SIGTERM`, short wait, then `SIGKILL`.
- Do not restore or resume running SubAgents after service restart.
- Remove the synchronous `delegate_to_subagent` tool from the Main Agent toolkit in this stage.

## Components

### BackgroundSubAgentSupervisor

Runs in the main process and owns active subprocess handles for one runtime process.

Responsibilities:

- Track active Background SubAgent Runs by `tenant_id + agent_id`.
- Enforce the fixed concurrency limit.
- Start worker subprocesses with `sys.executable`.
- Lazy-reap exited workers during `wait_subagent`, `get_subagent`, and `cancel_subagent`.
- Mark a run failed if a worker exits without writing a terminal result.
- Cancel a worker process group for active runs.

The supervisor state is in memory only. After process restart, active handles are gone and the first implementation does not scan run files to mark them expired.

### PerRunSubAgentRunStore

Stores one JSON file per run:

```text
<tenant_app_state>/workspaces/<agent_id>/subagent_runs/
  subagent-abc123.json
  subagent-abc123.launch.json
  subagent-abc123.stderr.log
```

The run JSON file contains the observable run record: identity, lifecycle status, parent identity, resolved definition identity, effective policy, worker metadata, final `AgentResult`, errors, and timestamps.

Writes use temporary files and atomic replace. Terminal states are first-writer-wins: once a run is terminal, later finish/fail/cancel attempts do not overwrite it.

### WorkerLaunchSpec

The launch spec is a minimal JSON contract from main process to worker process. It includes:

- `run_id`
- `run_store_dir`
- `workspace_dir`
- `parent_agent_config`
- `definition`
- `delegation_spec`
- `effective_policy`
- safe request context subset: `session_id`, `chat_id`, `turn_id`, `user_id`, `channel`, `source_id`, `trace_id`, `tenant_id`, `agent_id`
- `stderr_log_path`

It must not include API keys, secrets, full environment variables, full parent chat history, hook overlay objects, approval replay state, or raw SubAgent transcripts.

### Worker Module

The worker entrypoint is internal:

```text
<sys.executable> -m swe.app.subagents.worker --launch-spec <path>
```

The worker reads `WorkerLaunchSpec`, reconstructs the existing SubAgent runtime inputs, calls `SubAgentRuntime.run()`, and writes the terminal run record. Provider secrets are resolved through existing tenant/provider configuration and inherited process environment, not through the launch spec.

## Tools

The synchronous `delegate_to_subagent` tool is removed from the Main Agent toolkit in this stage. The SubAgent tool surface becomes background-only:

- `start_subagent`
- `wait_subagent`
- `get_subagent`
- `cancel_subagent`

### start_subagent

Inputs:

```python
start_subagent(
    agent_name: str,
    objective: str,
    background: str = "",
    scope: dict | None = None,
    budget: dict | None = None,
)
```

Behavior:

- Builds a full `DelegationSpec` internally.
- Resolves the named SubAgent definition.
- Computes effective policy from parent, definition, runtime, and workspace policy.
- Rejects unsupported or non-readonly MVP definitions.
- Checks the per-`tenant_id + agent_id` concurrency limit before creating a run.
- If the limit is reached, returns a blocked response with `reason=background_subagent_concurrency_limit`, `limit`, and `active_run_ids`.
- If accepted, creates a run file as `pending`, starts the worker subprocess, records worker pid, and returns run identity.

### wait_subagent

Performs a bounded wait and compact status snapshot for current in-memory active runs under `tenant_id + agent_id`.

Default behavior:

- Waits briefly, for example up to 3000 ms.
- Returns non-terminal active runs by default.
- Lazy-reaps exited workers.
- Includes runs that became terminal during this wait in `terminal_runs`.
- Does not scan historical run files.
- Does not restore or expire runs after service restart.

### get_subagent

Reads a per-run JSON file by run id within the current `tenant_id + agent_id` scope.

Default response is compact:

- `run_id`
- lifecycle `status`
- `agent_name`
- `objective`
- key timestamps
- `result` when terminal
- `errors`
- worker exit summary
- `manageable`
- stderr tail up to 4 KB for failed or cancelled runs

`include_details=true` may include the full `delegation_spec` and `effective_policy`.

### cancel_subagent

Cancels only an active run owned by the current `tenant_id + agent_id` scope.

Behavior:

- If the run is already terminal, return the existing terminal state.
- If the run exists but has no active supervisor handle, return `not_manageable`.
- If active, terminate the worker process group with `SIGTERM`, wait briefly, then `SIGKILL`.
- Write `cancelled` only if no terminal state has already been written.

## Lifecycle Status

Background SubAgent Run lifecycle statuses:

```python
pending
running
paused
completed
failed
cancelled
expired
```

The first implementation actively emits:

- `pending`
- `running`
- `completed`
- `failed`
- `cancelled`

`paused` is reserved for future pause/resume or approval-driven behavior. `expired` is reserved for future supervisor cleanup semantics and is not emitted by the first implementation.

This lifecycle status is separate from `AgentResult.status`. For example, a run lifecycle may be `completed` while the `AgentResult.status` is `partial` or `blocked`.

## Visibility And Permissions

SubAgent tools are main-agent-only.

Tool registration rules:

- If `agent_role == "subagent"`, register no SubAgent tools.
- If `enable_subagents != true`, register no SubAgent tools.
- `start_subagent` requires the current user turn or explicit metadata to mention SubAgent intent.
- `wait_subagent` is visible when the current scope has active Background SubAgent Runs, or when the current turn mentions SubAgent intent.
- `get_subagent` and `cancel_subagent` are visible when the current scope has active runs, the current turn mentions SubAgent intent, or the request explicitly includes a run id.

Conservative SubAgent intent triggers:

```text
subagent
SubAgent
subAgent
子代理
子 agent
子Agent
后台子代理
```

Plan Mode may use background readonly SubAgents. Plan Mode does not widen permissions.

Hard restrictions:

- Background execution does not bypass `ToolGuardMixin`.
- Effective policy remains parent ∩ definition ∩ runtime ∩ workspace.
- SubAgent workers cannot use MCP, skills, memory, worktree isolation, mutating tools, test commands, or nested delegation in this phase.
- `get_subagent` and `cancel_subagent` cannot cross the current `tenant_id + agent_id` run directory.

## Error Handling

`start_subagent`:

- Unknown agent: return failed; do not create a run.
- Unsupported definition: return failed; do not create a run.
- Concurrency limit reached: return blocked; do not create a run.
- Worker start failure after run creation: mark run `failed(worker_start_failed)`.

Worker:

- Provider/config unavailable: mark `failed(provider_config_unavailable)`.
- Runtime exception: use existing structured failed result.
- Invalid output: use existing repair path and fallback.
- Crash without terminal result: supervisor lazy reap marks `failed(worker_exited_without_result)`.

`wait_subagent`:

- Timeout returns `timed_out=true`; it does not mutate run status.

`get_subagent`:

- Missing or out-of-scope run returns `not_found` to avoid leaking cross-scope existence.

`cancel_subagent`:

- Already-terminal run returns existing terminal state.
- Existing run without active supervisor handle returns `not_manageable`.
- Active run terminates the worker process group and writes `cancelled` if first terminal writer wins.

## Testing

Unit tests:

- Per-run store create/update/get.
- Terminal first-writer-wins.
- Atomic replace behavior.
- Supervisor concurrency limit.
- Limit reached returns blocked and creates no run file.
- Lazy reap writes failed when worker exits without result.
- Cancel terminates process group.
- Launch spec excludes secrets, hook overlay objects, and full request context.
- Tool visibility for trigger words, main-agent-only behavior, SubAgent invisibility, and Plan Mode readonly availability.
- Tool response shapes for start/wait/get/cancel.

Worker tests:

- Worker reads launch spec and invokes a monkeypatched `SubAgentRuntime`.
- Worker writes terminal result.
- Worker writes failed state on exception.

Integration tests:

- Start a fast fake worker and observe it through `wait_subagent`.
- Cancel a long-running fake worker.
- `get_subagent` reads terminal per-run result.
- `delegate_to_subagent` is no longer registered as a Main Agent tool.
- Without current-turn SubAgent intent, create/delegate tools are not visible.

## Out Of Scope

- Public HTTP APIs.
- Console UI.
- Distributed queue or cross-pod worker scheduling.
- Service restart recovery.
- Automatic `expired` emission.
- Pause/resume.
- User-defined SubAgent CRUD/UI.
- Worktree or sandbox write workers.
- Full transcript persistence.
- Full stdout protocol.
