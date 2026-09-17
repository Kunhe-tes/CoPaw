# AgentRunner Behavior-Preserving Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the query execution concerns in `AgentRunner` into private collaborators while preserving every externally observable request, stream, Hook, approval, retry, timeout, cancellation, trace, and cleanup behavior.

**Architecture:** `AgentRunner` remains the facade and continues to own workspace, session, chat manager, task tracker, and trace context. `_prepare_query_runtime` remains the runtime-assembly boundary. New private modules use dataclasses and narrow Protocols; they do not import `AgentRunner` at runtime.

**Tech Stack:** Python 3.12, asyncio, pytest, pytest-asyncio, AgentScope Runtime, GitNexus.

---

## File map

| File | Responsibility |
| --- | --- |
| `src/swe/app/runner/query_types.py` | Query attempt, runtime-start, retry, and turn dataclasses shared by private collaborators. |
| `src/swe/app/runner/query_attempt.py` | Retry loop, one-attempt flow, cancellation and final-error routing. |
| `src/swe/app/runner/session_lifecycle.py` | Session load/save and skill-snapshot persistence helpers. |
| `src/swe/app/runner/query_cleanup.py` | First-phase serial cleanup coordinator. |
| `src/swe/app/runner/runner.py` | Stable facade and dependency assembly only. |
| `tests/unit/app/test_runner_query_flow.py` | Characterization tests for output traces, trace statuses, and cleanup ordering. |
| `tests/unit/app/test_runner_hook_runtime.py` | Existing runtime-assembly regression tests, updated only for moved private imports. |

### Task 1: Lock the current query-flow behavior with characterization tests

**Files:**
- Create: `tests/unit/app/test_runner_query_flow.py`
- Modify: `tests/unit/app/test_runner_hook_runtime.py`

- [ ] **Step 1: Add a recording facade fixture.**

Create a fake runner exposing `_prepare_query_runtime`, `get_state_loaded`,
`_build_turn_plan`, `_stream_completion_lifecycle`, trace methods, and the
four cleanup actions. Record each call in `events`:

```python
class _RecordingRunner:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def _cleanup_query_resources(self, **_kwargs) -> None:
        self.events.extend(["save-session", "update-chat", "cleanup-mcp", "end-detector"])
```

Use a deterministic async generator yielding one assistant `Msg` and
`last=True`; do not call a real provider, MCP server, or filesystem.

- [ ] **Step 2: Write the failing normal-flow and cleanup-order tests.**

```python
@pytest.mark.asyncio
async def test_query_attempt_emits_existing_messages_and_keeps_cleanup_order():
    runner = _RecordingRunner()

    events = [event async for event in run_query_after_preflight(runner, _attempt_input())]

    assert [(message.content, last) for message, last in events] == [("done", True)]
    assert runner.events[-4:] == ["save-session", "update-chat", "cleanup-mcp", "end-detector"]
```

Add equivalent failing tests for Hook block, retryable error followed by
success, final error with `TraceStatus.ERROR`, and cancellation with
`TraceStatus.CANCELLED`.

- [ ] **Step 3: Run the characterization module before extraction.**

```bash
venv/bin/python -m pytest tests/unit/app/test_runner_query_flow.py -q
```

Expected: FAIL because `run_query_after_preflight` is not yet exported from a private collaborator.

### Task 2: Move shared private value types without changing their names

**Files:**
- Create: `src/swe/app/runner/query_types.py`
- Modify: `src/swe/app/runner/runner.py:201-296`
- Modify: `tests/unit/app/test_runner_hook_runtime.py:20-45`

- [ ] **Step 1: Create the shared type module.**

Move `_QueryPreflight`, `_QueryRuntimeInputs`, `_QueryRuntimeResources`,
`_QueryRuntime`, `_RuntimeStartResult`, `_TurnPlan`, `_QueryTurnOutcome`,
`_RetryState`, `_QueryAttemptState`, and `_QueryAttemptInput` unchanged into
`query_types.py`. Keep type-only imports under `TYPE_CHECKING` to avoid an
`AgentRunner` import cycle.

- [ ] **Step 2: Re-export the moved private names from `runner.py`.**

```python
from .query_types import (
    _QueryAttemptInput,
    _QueryAttemptState,
    _QueryPreflight,
    _QueryRuntime,
    _QueryRuntimeInputs,
    _QueryRuntimeResources,
    _QueryTurnOutcome,
    _RetryState,
    _RuntimeStartResult,
    _TurnPlan,
)
```

This preserves current test imports while callers migrate gradually.

- [ ] **Step 3: Run type and runtime-assembly regressions.**

```bash
venv/bin/python -m pytest tests/unit/app/test_runner_hook_runtime.py -q
venv/bin/ruff check src/swe/app/runner/query_types.py src/swe/app/runner/runner.py
```

Expected: PASS with no import cycle.

- [ ] **Step 4: Commit the value-type extraction.**

```bash
git add src/swe/app/runner/query_types.py src/swe/app/runner/runner.py tests/unit/app/test_runner_hook_runtime.py
git diff --cached --check
git commit -m "refactor(runner): extract query value types"
```

### Task 3: Extract serial cleanup as a tested private collaborator

**Files:**
- Create: `src/swe/app/runner/query_cleanup.py`
- Modify: `src/swe/app/runner/runner.py:3900-4080`
- Modify: `tests/unit/app/test_runner_query_flow.py`

- [ ] **Step 1: Define the cleanup port and coordinator.**

```python
class QueryCleanupPort(Protocol):
    async def _save_state_during_cleanup(self, *, runtime: _QueryRuntime | None, session_state_loaded: bool) -> None: ...
    async def _update_chat_during_cleanup(self, runtime: _QueryRuntime | None) -> None: ...
    async def _cleanup_mcp_during_cleanup(self, runtime: _QueryRuntime | None) -> None: ...
    async def _end_skill_detector_during_cleanup(self, runtime: _QueryRuntime | None) -> None: ...

async def cleanup_query_resources(port: QueryCleanupPort, *, runtime: _QueryRuntime | None, session_state_loaded: bool) -> None:
    await port._save_state_during_cleanup(runtime=runtime, session_state_loaded=session_state_loaded)
    await port._update_chat_during_cleanup(runtime)
    await port._cleanup_mcp_during_cleanup(runtime)
    await port._end_skill_detector_during_cleanup(runtime)
```

- [ ] **Step 2: Delegate from the existing facade method.**

```python
async def _cleanup_query_resources(self, *, runtime, session_state_loaded, session_id):
    logger.info("Runner finally block executing for session %s", session_id)
    await cleanup_query_resources(self, runtime=runtime, session_state_loaded=session_state_loaded)
```

Do not change `session_id` logging or blocked-start cleanup.

- [ ] **Step 3: Run cleanup characterization and hook-runtime tests.**

```bash
venv/bin/python -m pytest tests/unit/app/test_runner_query_flow.py tests/unit/app/test_runner_hook_runtime.py -q
```

Expected: PASS; the recorded cleanup order remains exactly serial.

- [ ] **Step 4: Commit the cleanup extraction.**

```bash
git add src/swe/app/runner/query_cleanup.py src/swe/app/runner/runner.py tests/unit/app/test_runner_query_flow.py
git diff --cached --check
git commit -m "refactor(runner): isolate serial query cleanup"
```

### Task 4: Extract session lifecycle helpers behind an explicit port

**Files:**
- Create: `src/swe/app/runner/session_lifecycle.py`
- Modify: `src/swe/app/runner/runner.py:505-1110`
- Modify: `tests/unit/app/test_runner_query_flow.py`

- [ ] **Step 1: Characterize regular and cron persistence.**

Add failing tests that use a fake session with `load_session_state` and
`mutate_session_state` recorders:

```python
@pytest.mark.asyncio
async def test_cron_session_persistence_uses_mutation_not_history_replacement():
    session = _RecordingSession()
    await save_session_state(session, agent=_agent(), session_id="s", user_id="u", skip_history=True, hook_overlay=None)

    assert session.calls == ["mutate-session-state"]
```

Add a regular-request test asserting that state is loaded before turn
execution and that the hook overlay is retained in the saved state.

- [ ] **Step 2: Move pure session operations.**

Move `_build_cron_merged_state`, cron/regular/legacy save branches, session
state loading, and skill-snapshot persistence into `session_lifecycle.py`.
The module receives `session`, `agent`, IDs, and `hook_overlay` explicitly;
it does not read `AgentRunner` attributes.

- [ ] **Step 3: Preserve facade delegates.**

Keep `get_state_loaded` and `save_job_session_state` on `AgentRunner`, but
make each a one-line delegate into `session_lifecycle`. Existing callers and
tests therefore retain their boundary.

- [ ] **Step 4: Run persistence and critical-path regressions.**

```bash
venv/bin/python -m pytest tests/unit/app/test_runner_query_flow.py tests/unit/app/test_runner_hook_runtime.py tests/unit/app/test_tenant_cron_execution.py -q
venv/bin/python scripts/run_critical_path_tests.py
```

Expected: PASS with the same history and cron merge behavior.

- [ ] **Step 5: Commit the session extraction.**

```bash
git add src/swe/app/runner/session_lifecycle.py src/swe/app/runner/runner.py tests/unit/app/test_runner_query_flow.py
git diff --cached --check
git commit -m "refactor(runner): isolate session lifecycle"
```

### Task 5: Extract retry and attempt orchestration

**Files:**
- Create: `src/swe/app/runner/query_attempt.py`
- Modify: `src/swe/app/runner/runner.py:4484-4820`
- Modify: `tests/unit/app/test_runner_query_flow.py`

- [ ] **Step 1: Define a narrow execution port.**

```python
class QueryAttemptPort(Protocol):
    async def _prepare_query_runtime(self, *, request, msgs, query, preflight) -> _RuntimeStartResult: ...
    async def _handle_query_cancelled(self, *, trace_id, session_id, agent, exc) -> None: ...
    async def _handle_query_error(self, *, request, exc, trace_id, locals_snapshot) -> None: ...
    async def _cleanup_query_resources(self, *, runtime, session_state_loaded, session_id) -> None: ...
```

`query_attempt.py` may call only this port and explicitly passed helper
callbacks. It must not import `AgentRunner`.

- [ ] **Step 2: Move `_stream_single_query_attempt` and `_stream_query_after_preflight`.**

Expose module functions `stream_single_query_attempt(port, ...)` and
`run_query_after_preflight(port, ...)`. Preserve the existing retry loop,
`try/finally` scope, runtime-invocation claim reset, file-network reset, and
blocked-runtime cleanup in the same order.

- [ ] **Step 3: Reduce facade methods to delegating generators.**

```python
async def _stream_query_after_preflight(self, msgs, *, request, query, session_id, preflight):
    async for item in run_query_after_preflight(self, msgs=msgs, request=request, query=query, session_id=session_id, preflight=preflight):
        yield item
```

Keep `_stream_query_entry`, `query_handler`, and `stream_query` in
`AgentRunner`; they are the public-boundary adapters.

- [ ] **Step 4: Run all behavior characterizations and focused failures.**

```bash
venv/bin/python -m pytest tests/unit/app/test_runner_query_flow.py tests/unit/app/test_runner_hook_runtime.py tests/unit/app/test_model_call_error_runner.py -q
venv/bin/python -m pytest tests/integrated/critical_paths/test_scheduled_run_boundary.py -q
```

Expected: PASS; normal, blocked, retried, failed, and cancelled traces match
the pre-extraction characterization assertions.

- [ ] **Step 5: Commit the attempt extraction.**

```bash
git add src/swe/app/runner/query_attempt.py src/swe/app/runner/runner.py tests/unit/app/test_runner_query_flow.py
git diff --cached --check
git commit -m "refactor(runner): extract query attempt flow"
```

### Task 6: Verify the refactor boundary and record deferred cleanup work

**Files:**
- Modify: `docs/superpowers/specs/2026-08-16-test-topology-and-runner-refactor-design.md`

- [ ] **Step 1: Run impact analysis before final review.**

```text
impact({repo: "CoPaw", target: "AgentRunner", file_path: "src/swe/app/runner/runner.py", direction: "upstream", includeTests: true, summaryOnly: true})
```

Expected: inspect every direct caller before accepting the refactor.

- [ ] **Step 2: Run the required suites and static checks.**

```bash
venv/bin/python -m pytest tests/unit/app/test_runner_query_flow.py tests/unit/app/test_runner_hook_runtime.py tests/unit/app/test_model_call_error_runner.py tests/unit/app/test_tenant_cron_execution.py -q
venv/bin/python scripts/run_critical_path_tests.py
venv/bin/ruff check src/swe/app/runner tests/unit/app
```

Expected: all commands exit 0.

- [ ] **Step 3: Confirm the diff has only expected symbols and flows.**

```text
detect_changes({repo: "CoPaw", scope: "all"})
```

Expected: only runner query-flow symbols, their tests, and design documentation are affected.

- [ ] **Step 4: Record the deferred second phase without implementing it.**

Retain the design document's cleanup second-phase section: persist session
first, then use a shared-deadline `TaskGroup` for chat, MCP, and detector
cleanup. Do not make that behavior change in this refactor.

- [ ] **Step 5: Commit the final verification/documentation update.**

```bash
git add docs/superpowers/specs/2026-08-16-test-topology-and-runner-refactor-design.md
git diff --cached --check
git commit -m "docs: record runner refactor verification"
```
