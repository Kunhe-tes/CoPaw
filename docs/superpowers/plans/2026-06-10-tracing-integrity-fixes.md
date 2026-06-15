# Tracing Integrity Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate cross-trace span attribution, restore missing `skill_invocation` spans, and add regression coverage so `swe_tracing_traces` and `swe_tracing_spans` stay internally consistent.

**Architecture:** Tighten trace ownership at request start by rejecting invalid `attach_existing` reuse before any existing `trace_id` is re-persisted, and clear attached trace context on cleanup. Collapse session-level and trace-level skill detection onto one detector instance so tool attribution, skill activation, and `skill_invocation` span emission share the same state, then harden cron request construction to avoid stale `trace_id` reuse. Add focused tracing and runner tests around attach, cron fallback, unified detector wiring, and post-cleanup isolation rather than changing span semantics or schema.

**Tech Stack:** Python, asyncio, FastAPI runner lifecycle, tracing manager/store, pytest, pytest-asyncio

---

### Task 1: Guard `attach_existing` Against Cross-Request Trace Reuse

**Files:**
- Modify: `src/swe/tracing/manager.py`
- Modify: `tests/unit/tracing/test_manager.py`

- [ ] **Step 1: Write failing attach validation tests**

Add tests that cover:

- attaching to an existing trace with matching `user_id`, `session_id`, `channel`, and `source_id` succeeds;
- attaching to an existing trace with mismatched `session_id` is rejected;
- mismatched `user_id`, `channel`, or `source_id` is rejected the same way;
- a rejected attach allocates a brand-new trace ID instead of reusing the incoming conflicting `trace_id`;
- a rejected attach does not overwrite the active trace context with the wrong trace.

Use the existing `TraceManager` fixtures and create a stored trace first via `start_trace(...)`, then call `start_trace(..., trace_id=existing_id, attach_existing=True)` with mismatched identity values.

- [ ] **Step 2: Run attach validation tests to verify RED**

Run:

```bash
venv/bin/python -m pytest tests/unit/tracing/test_manager.py -k attach_existing -v
```

Expected: new attach validation tests fail because `_handle_attach_existing()` currently accepts any existing `trace_id` without identity checks, and `start_trace()` reuses the incoming `trace_id` on the create path.

- [ ] **Step 3: Implement strict attach identity validation**

In `src/swe/tracing/manager.py`:

- add a small helper that compares the incoming request identity against the existing trace:

```python
def _can_attach_to_trace(
    existing_trace: Trace,
    *,
    user_id: str,
    session_id: str,
    channel: str,
    source_id: str,
) -> bool:
    return (
        (existing_trace.user_id or "") == user_id
        and (existing_trace.session_id or "") == session_id
        and (existing_trace.channel or "") == channel
        and (existing_trace.source_id or "") == source_id
    )
```

- call that helper from `_handle_attach_existing()`;
- when validation fails, log a warning with both the incoming identity and existing trace identity;
- change `start_trace()` so a failed `attach_existing` validation discards the incoming conflicting `trace_id` and generates a fresh UUID before creating a new trace row;
- keep successful attach behavior unchanged.

- [ ] **Step 4: Run attach validation tests to verify GREEN**

Run:

```bash
venv/bin/python -m pytest tests/unit/tracing/test_manager.py -k attach_existing -v
```

Expected: attach succeeds only for matching identity and mismatch cases now create a new trace path with a new trace ID instead of reusing the wrong one.

### Task 2: Clear Attached Trace Context During Runner Cleanup

**Files:**
- Modify: `src/swe/app/runner/runner.py`
- Modify: `tests/unit/app/test_runner_query_retry.py`

- [ ] **Step 1: Write failing cleanup tests for attached traces**

Add tests that:

- set up a fake attached trace context via `set_current_trace(...)` with `attached=True`;
- call `_end_trace_if_needed(...)`;
- verify the method does not call `TraceManager.end_trace(...)`;
- verify `get_current_trace()` becomes `None` after cleanup.

Also add one runner-level regression that performs two sequential traced requests in the same test process: the first request uses an attached context and cleanup, and the second request verifies it does not observe the stale trace context.

Keep the helper test focused on `_end_trace_if_needed()` and patch `has_trace_manager()` / `get_trace_manager()` as needed; keep the runner-level regression narrow and mock the model/tool layers.

- [ ] **Step 2: Run cleanup tests to verify RED**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_runner_query_retry.py -k attached_trace -v
```

Expected: the new test fails because the attached branch returns early without clearing `current_trace`.

- [ ] **Step 3: Fix the attached cleanup branch**

Update `src/swe/app/runner/runner.py` so the `ctx.attached` branch:

- logs the skip as it does today;
- calls `set_current_trace(None)` before returning;
- keeps ownership semantics unchanged by still skipping `trace_mgr.end_trace(...)`.

Use the tracing helpers directly in this branch rather than adding a second cleanup path elsewhere.

- [ ] **Step 4: Run cleanup tests to verify GREEN**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_runner_query_retry.py -k attached_trace -v
```

Expected: attached traces are skipped for ending but their leaked context is cleared.

### Task 3: Remove Stale `trace_id` From Cron Requests Before Trace Creation

**Files:**
- Modify: `src/swe/app/crons/executor.py`
- Modify: `tests/unit/app/test_tenant_cron_execution.py`

- [ ] **Step 1: Write failing cron request sanitization tests**

Add tests that verify:

- `_build_agent_request()` drops any existing `trace_id` from `job.request`;
- if `_create_trace_for_agent_job()` later returns a new trace ID, that new value is the only `trace_id` on the outgoing request;
- if trace creation fails, the request passed into `runner.stream_query(...)` has no `trace_id` field at all.

Model the request using `CronJobRequest.model_validate(...)` with an extra `trace_id` value to reproduce the stale-field case.

- [ ] **Step 2: Run cron sanitization tests to verify RED**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_tenant_cron_execution.py -k trace_id -v
```

Expected: the stale `trace_id` remains in the built cron request because `_build_agent_request()` currently preserves all extra fields from `job.request`.

- [ ] **Step 3: Sanitize cron request payloads**

In `src/swe/app/crons/executor.py`:

- remove any pre-existing `trace_id` immediately after `job.request.model_dump(mode="json")`;
- keep injecting the new trace ID only after `_create_trace_for_agent_job()` succeeds;
- add a debug or warning log when a stale `trace_id` is removed so future incidents are visible in logs.

Use a direct payload cleanup rather than changing `CronJobRequest` schema so existing extra-field behavior stays intact.

- [ ] **Step 4: Run cron sanitization tests to verify GREEN**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_tenant_cron_execution.py -k trace_id -v
```

Expected: cron execution never forwards a stale trace ID into `runner.stream_query(...)`.

### Task 4: Wire Session Skill Detector Into Tracing

**Files:**
- Modify: `src/swe/app/runner/runner.py`
- Modify: `src/swe/agents/skill_invocation_detector.py`
- Modify: `tests/unit/app/test_runner_hook_runtime.py`
- Modify: `tests/unit/agents/test_skill_invocation_detector.py`

- [ ] **Step 1: Write failing detector wiring tests**

Add tests that verify:

- the session skill detector created in `_attach_session_skill_detector()` receives tracing context when `request.trace_id` is present;
- the detector used by `agent._request_context["_skill_invocation_detector"]` is the same instance as the detector used by tracing-driven tool attribution, or the trace-context detector reference is explicitly updated to that same object;
- `start_skill(...)` on that shared detector emits `skill_invocation` through the trace manager instead of only updating hook state;
- requests without a trace ID still keep the previous no-tracing behavior.

Patch `TraceManager.emit_skill_invocation()` or use a detector spy so the test proves the shared detector is now trace-aware.

- [ ] **Step 2: Run detector wiring tests to verify RED**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/app/test_runner_hook_runtime.py \
  tests/unit/agents/test_skill_invocation_detector.py \
  -k "trace or skill_invocation" -v
```

Expected: the detector wiring tests fail because the request-context detector and the trace-context detector are currently separate instances, and the request-context detector never receives tracing context.

- [ ] **Step 3: Inject tracing context into the session detector**

Implement one shared detector path instead of two partially-overlapping ones:

- extend `_create_session_skill_detector(...)` to optionally accept `trace_manager` and `trace_id`, or call `detector.set_tracing_context(...)` immediately after construction;
- when `request.trace_id` is available in `_attach_session_skill_detector()`, pass the current trace manager, trace ID, user ID, session ID, and channel into the detector;
- register that same detector instance both in `agent._request_context["_skill_invocation_detector"]` and in the current trace context so `emit_tool_call_start()` and tool-guard notifications consult the same object;
- keep the no-trace branch unchanged so non-traced flows still work.

Do not add a third detector path; reuse the existing `SkillInvocationDetector` API and remove divergence between the current two call sites.

- [ ] **Step 4: Run detector wiring tests to verify GREEN**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/app/test_runner_hook_runtime.py \
  tests/unit/agents/test_skill_invocation_detector.py \
  -k "trace or skill_invocation" -v
```

Expected: the single shared detector now drives both tool attribution and `skill_invocation` span emission when a trace is active.

### Task 5: Add Trace Integrity Regression Coverage

**Files:**
- Modify: `tests/unit/tracing/test_manager.py`
- Modify: `tests/unit/app/test_tenant_cron_execution.py`
- Modify: `tests/unit/app/test_runner_hook_runtime.py`
- Modify: `analysis/playbook/common-errors.md`
- Modify: `analysis/playbook/troubleshooting-order.md`

- [ ] **Step 1: Add regression tests for known failure patterns**

Add focused tests for:

- same `trace_id` with mismatched identity now creates a fresh trace;
- attached traces do not leak `current_trace` after cleanup;
- cron requests with stale `trace_id` cannot trigger attach reuse;
- the shared skill detector writes `skill_invocation` once a traced request starts a skill;
- a post-cleanup request does not inherit the previous attached trace context.

Keep each failure pattern isolated in its existing test module so future regressions point directly at the broken subsystem.

- [ ] **Step 2: Run the focused regression suite**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/tracing/test_manager.py \
  tests/unit/app/test_runner_hook_runtime.py \
  tests/unit/app/test_runner_query_retry.py \
  tests/unit/app/test_tenant_cron_execution.py \
  tests/unit/agents/test_skill_invocation_detector.py -v
```

Expected: all focused tracing integrity tests pass.

- [ ] **Step 3: Document the new failure signatures and checks**

Update:

- `analysis/playbook/common-errors.md` with the symptom “same trace contains multiple model names / cross-request spans” and the likely causes `attach_existing` mismatch or stale cron `trace_id`;
- `analysis/playbook/troubleshooting-order.md` with a check sequence:
  1. confirm `trace_id` appears under multiple `session_id/user_id/source_id/channel`;
  2. inspect attach logs;
  3. inspect cron request payload for stale `trace_id`;
  4. verify session detector tracing is wired.

- [ ] **Step 4: Run the final verification commands**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/tracing/test_manager.py \
  tests/unit/app/test_runner_hook_runtime.py \
  tests/unit/app/test_runner_query_retry.py \
  tests/unit/app/test_tenant_cron_execution.py \
  tests/unit/agents/test_skill_invocation_detector.py -v
```

Expected: the tracing integrity regression suite stays green after docs updates.
