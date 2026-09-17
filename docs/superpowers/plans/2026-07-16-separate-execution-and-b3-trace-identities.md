# Separate Execution and B3 Trace Identities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep every Swe execution uniquely addressable while retaining an unchanged, potentially shared B3 trace identifier for distributed correlation.

**Architecture:** `swe_tracing_traces.trace_id` remains the unique internal execution key and gains a nullable, non-unique `b3_trace_id`. Cron resolves whether an incoming B3 value can also be the execution ID: valid `dispatch_service` batch callbacks generate a UUID per attempt; all non-batch requests preserve the current B3-as-trace behavior. Spans, Subtasks, feedback, Elasticsearch, and runtime invocation claims continue to use only the internal execution ID.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, async MySQL, pytest, manual idempotent MySQL migrations.

---

### Task 1: Persist both trace identities

**Files:**
- Modify: `src/swe/tracing/models.py`
- Modify: `src/swe/tracing/manager.py`
- Modify: `src/swe/tracing/store.py`
- Modify: `scripts/sql/tracing_tables.sql`
- Modify: `scripts/init_tracing_tables.py`
- Create: `scripts/sql/tracing_b3_trace_id_migration.sql`
- Test: `tests/unit/tracing/test_manager.py`
- Test: `tests/unit/tracing/test_store.py`

- [ ] **Step 1: Write failing manager and store tests**

Add a manager test that calls `start_trace(..., trace_id="internal-trace", b3_trace_id="shared-b3")` and asserts the active `Trace` contains both values. Add store tests that assert `create_trace()` writes `b3_trace_id` immediately after `trace_id`, and `_row_to_trace()` accepts both populated and missing `b3_trace_id` rows.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/unit/tracing/test_manager.py -k b3_trace_id tests/unit/tracing/test_store.py -k b3_trace_id -q`

Expected: failures because `Trace` and `TraceManager.start_trace()` do not yet accept `b3_trace_id`, and the insert does not contain the new column.

- [ ] **Step 3: Add the minimal persistence implementation**

Add `b3_trace_id: Optional[str] = None` to `Trace`; append the same optional keyword to `TraceManager.start_trace()` and pass it into the newly created `Trace`. Insert it through `TraceStore.create_trace()` and deserialize with `row.get("b3_trace_id")`. Keep `trace_id` unique and do not change Span storage.

- [ ] **Step 4: Add install and upgrade SQL**

Add nullable `VARCHAR(64)` `b3_trace_id` plus non-unique `(source_id, b3_trace_id)` index to fresh-table SQL and the Python initializer. Add an idempotent MySQL/TDSQL-compatible migration that checks `INFORMATION_SCHEMA.COLUMNS` and `INFORMATION_SCHEMA.STATISTICS` before conditionally executing prepared `ALTER TABLE` statements; explicitly do not backfill historical rows.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Step 2 command and expect all selected tests to pass.

### Task 2: Resolve batch and non-batch IDs at runtime entry points

**Files:**
- Modify: `src/swe/app/crons/executor.py`
- Modify: `src/swe/app/runner/runner.py`
- Test: `tests/unit/app/test_tenant_cron_execution.py`
- Test: `tests/unit/app/test_runner_query_retry.py`

- [ ] **Step 1: Write failing Cron and Runner tests**

Cover agent and text Cron execution. A valid batch meta object must contain `source="dispatch_service"`, a positive integer `intent_id`, non-empty `batch_id`, and positive integer `dispatch_attempt`; with B3 present Cron must pre-generate a UUID, call trace creation with that UUID plus `b3_trace_id=<B3>`, and propagate the UUID as request `trace_id`, while preserving the original `b3_trace_id` and `X-B3-*` passthrough headers. Two attempts with the same B3 must get different UUIDs even when trace pre-creation fails. Non-batch Cron and ordinary Runner requests must pass B3 as both `trace_id` and `b3_trace_id`.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_tenant_cron_execution.py -k "trace or b3" tests/unit/app/test_runner_query_retry.py -k start_query_trace -q`

Expected: batch assertions fail because current Cron execution reuses B3 as the unique trace ID, and Runner does not pass `b3_trace_id` to the manager.

- [ ] **Step 3: Implement strict batch recognition and ID resolution**

Add a small executor helper that recognizes only the normalized, fully valid dispatch-service identity. Resolve `(requested_trace_id, b3_trace_id)` as `(new UUID, B3)` for valid batches and `(B3, B3)` otherwise. Thread both values through text and agent trace creation. If pre-creation fails, retain the generated UUID in the execution result/request so Runner can recreate or attach by the internal ID rather than falling back to B3. Keep `_apply_dispatch_passthrough_headers()` unchanged so all original B3 headers remain byte-for-byte equivalent at the request metadata boundary.

- [ ] **Step 4: Preserve ordinary Runner compatibility**

In `_start_query_trace()`, continue choosing B3 as a new ordinary trace ID, and also pass it separately as `b3_trace_id`. When attaching an already-created Cron trace, keep the request's internal `trace_id` and pass the B3 value only as metadata.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Step 2 command and expect all selected tests to pass.

### Task 3: Expose the stored B3 correlation in Monitor trace detail

**Files:**
- Modify: `monitor/src/monitor/app/models/tracing.py`
- Modify: `monitor/src/monitor/app/services/tracing/query_service.py`
- Test: `tests/unit/monitor/test_tracing_b3_trace_id.py`

- [ ] **Step 1: Write a failing row-mapping test**

Construct a database trace row with `trace_id="internal-trace"` and `b3_trace_id="shared-b3"`, invoke `_row_to_trace()`, and assert both fields are present on the returned model. Include a legacy row without the new column and assert `b3_trace_id is None`.

- [ ] **Step 2: Run the test and verify RED**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/unit/monitor/test_tracing_b3_trace_id.py -q`

Expected: failure because Monitor's `Trace` model and row mapper do not expose `b3_trace_id`.

- [ ] **Step 3: Implement the optional Monitor field**

Add the nullable field to Monitor's `Trace` model and map it with `row.get("b3_trace_id")`. Do not alter Span, feedback, Elasticsearch document IDs, or Subtask keys.

- [ ] **Step 4: Run the test and verify GREEN**

Run the Step 2 command and expect both new mapping cases to pass.

### Task 4: Regression and scope verification

**Files:**
- Verify all files above plus `src/swe/runtime_invocation_claims.py` and Monitor Subtask storage without modifying their internal-ID contract.

- [ ] **Step 1: Run focused regression suites**

Run the complete tracing manager/store suites, Cron execution tests, Runner trace tests, Monitor B3 mapping tests, internal callback tests, runtime invocation claim tests, and Subtask tests.

- [ ] **Step 2: Verify source quality**

Run `git diff --check`, targeted Ruff/Pylint commands used by the repository where available, and Python compile checks for modified modules.

- [ ] **Step 3: Run GitNexus change detection**

Run `detect_changes()` and confirm the changed execution flows are limited to tracing persistence, Cron trace creation, ordinary query trace creation, and Monitor trace deserialization.

- [ ] **Step 4: Inspect final diff and document every modification**

Map each changed file to its purpose, state the exact batch/non-batch matrix, explain why Subtasks continue storing only internal `trace_id`, and list the migration command/artifact without executing it against an external database.

- [ ] **Step 5: Enforce the release Go/No-Go order**

Release order is mandatory: run `scripts/sql/tracing_b3_trace_id_migration.sql`; query `INFORMATION_SCHEMA.COLUMNS` to verify nullable `b3_trace_id VARCHAR(64)`; query `INFORMATION_SCHEMA.STATISTICS` to verify `idx_source_b3_trace` contains `source_id` then `b3_trace_id`; only then deploy SWE writers, followed by Monitor readers. Do not deploy the new INSERT path while the column is absent.

No git commit is included because the user requested implementation and explanation, not repository history mutation.
