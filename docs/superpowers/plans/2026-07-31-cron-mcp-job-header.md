# Scheduled MCP `cron_job_id` Header Plan

**Goal:** Whenever a Scheduled Job runs, pass the authoritative job id to every
HTTP/SSE MCP connection as the `cron_job_id` request header. This applies to
both schedule-triggered and manually triggered Scheduled Runs.

**Architecture:** `CronManager.run_job()` is the shared execution boundary for
schedule-triggered and manually triggered Scheduled Runs. It will enrich a
per-execution copy of `dispatch_meta.passthrough_headers` before creating the
background task. The existing `CronExecutor` and Runner header pipeline will
carry the value to `build_mcp_http_headers()` without MCP client changes.

**Contract:**

- Header name is exactly `cron_job_id`.
- Header value is the persisted `CronJobSpec.id`, not an incoming caller value.
- Both `is_manual=False` and `is_manual=True` executions receive the header.
- Persisted `job.dispatch.meta` headers and per-execution passthrough/B3 headers
  are preserved, with per-execution values taking precedence
  case-insensitively.
- Existing case variants of `cron_job_id` are removed before the authoritative
  lowercase header is written.
- Caller-owned dictionaries are not mutated.
- HTTP/SSE MCP transports receive the header; stdio MCP is out of scope.

**Docs:** No `CONTEXT.md` or ADR update. This is a reversible transport detail,
not a new domain term or architectural ownership decision.

## Task 1: Add failing manager-level tests

**Files:**

- Modify: `tests/unit/app/test_cron_manager_completed_cancellation.py` or the
  narrowest existing Cron manager test module.

**Steps:**

1. Add a test that invokes `run_job(..., is_manual=False)` and captures the
   metadata passed to `_execute_once`.
2. Assert that existing passthrough headers remain present and
   `cron_job_id == job.id`.
3. Assert that an incoming `cron_job_id` is overwritten by the persisted job
   id and that the caller-owned metadata is unchanged.
4. Add a manual-run test asserting the authoritative `cron_job_id` is
   injected while existing headers are preserved.
5. Add regression cases for persisted `job.dispatch.meta` headers and a
   mixed-case external `Cron_Job_Id`.
6. Run the focused tests and confirm the new assertions fail before
   implementation.

## Task 2: Implement the smallest boundary change

**Files:**

- Modify: `src/swe/app/crons/manager.py`

**Steps:**

1. Copy persisted job headers, then overlay copied per-execution headers.
2. Remove all case-insensitive variants of `cron_job_id`.
3. Write the authoritative lowercase `cron_job_id` for every run.
4. Pass the enriched metadata to `_execute_once` for both scheduled and manual
   executions.
5. Re-run the focused tests and confirm they pass.

## Task 3: Regression verification

**Commands:**

```powershell
& .\.venv\Scripts\python.exe -m pytest <focused-test-node-ids> -q
& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_tenant_cron_execution.py tests/unit/routers/test_internal_tenant_scope.py -q
```

Run independent spec and quality review passes, fix all Important findings,
then run GitNexus `detect_changes` and inspect the final diff.
