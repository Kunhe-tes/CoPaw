# Physical Cron Scheduler Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move batch dispatch scheduling out of Monitor into a real top-level Scheduler service.

**Architecture:** Add a new `scheduler` Python package and FastAPI app. Scheduler owns the dispatch loop, intent state transitions, SWE callback handoff, completion feedback handling, and immediate refill. Monitor remains the cron definition/execution/telemetry persistence surface; SWE remains the execution owner.

**Tech Stack:** Python, FastAPI, aiomysql-backed Monitor database tables, httpx SWE callback client, existing pytest/pytest-asyncio tests.

---

### Task 1: Introduce Scheduler Package And Test Import Path

**Files:**
- Create: `scheduler/pyproject.toml`
- Create: `scheduler/main.py`
- Create: `scheduler/src/scheduler/__init__.py`
- Create: `scheduler/src/scheduler/__version__.py`
- Create: `scheduler/src/scheduler/app/__init__.py`
- Create: `scheduler/src/scheduler/app/_app.py`
- Create: `scheduler/src/scheduler/app/routers/__init__.py`
- Modify: `conftest.py`

- [ ] **Step 1: Write failing import/app test**

Add a test that imports `scheduler.app._app:app` and asserts the app title is `Cron Scheduler`.

- [ ] **Step 2: Run the test and verify it fails**

Run: `& .\.venv\Scripts\python.exe -m pytest tests\unit\scheduler\test_scheduler_app.py -q`

Expected: FAIL because `scheduler` does not exist.

- [ ] **Step 3: Add the scheduler package and test import path**

Create the package under `scheduler/src`, add a minimal FastAPI app, and add `_ROOT / "scheduler" / "src"` to root `conftest.py`.

- [ ] **Step 4: Run the test and verify it passes**

Run: `& .\.venv\Scripts\python.exe -m pytest tests\unit\scheduler\test_scheduler_app.py -q`

Expected: PASS.

### Task 2: Move Dispatch Intent Store Into Scheduler

**Files:**
- Move: `monitor/src/monitor/app/services/cron/dispatch_intent_service.py` to `scheduler/src/scheduler/app/services/cron/dispatch_intent_service.py`
- Create: `scheduler/src/scheduler/app/services/__init__.py`
- Create: `scheduler/src/scheduler/app/services/cron/__init__.py`
- Modify: `tests/unit/monitor/test_cron_dispatch_intent_service.py` -> `tests/unit/scheduler/test_cron_dispatch_intent_service.py`
- Modify: `monitor/src/monitor/app/routers/sync.py`

- [ ] **Step 1: Write failing scheduler import test**

Update dispatch intent tests to import from `scheduler.app.services.cron.dispatch_intent_service`.

- [ ] **Step 2: Run the test and verify it fails**

Run: `& .\.venv\Scripts\python.exe -m pytest tests\unit\scheduler\test_cron_dispatch_intent_service.py -q`

Expected: FAIL until the service is moved.

- [ ] **Step 3: Move the service**

Move the dispatch intent queue code into `scheduler`. Its persistence can continue using the Monitor DB connection module during this rollout, because the physical service boundary is the required correction; schema extraction can be a later hardening step.

- [ ] **Step 4: Remove Monitor dispatch intent API ownership**

Remove Monitor sync-router dispatch intent endpoints and imports. Scheduler will expose dispatch-specific APIs.

- [ ] **Step 5: Run tests**

Run: `& .\.venv\Scripts\python.exe -m pytest tests\unit\scheduler\test_cron_dispatch_intent_service.py -q`

Expected: PASS.

### Task 3: Move Scheduling Loop Into Scheduler Service

**Files:**
- Move: `monitor/src/monitor/app/services/cron/scheduling_service.py` to `scheduler/src/scheduler/app/services/cron/scheduling_service.py`
- Create: `scheduler/src/scheduler/app/routers/cron.py`
- Modify: `monitor/src/monitor/app/_app.py`
- Modify: `monitor/src/monitor/app/services/cron/__init__.py`
- Modify: `tests/unit/monitor/test_cron_scheduling_service.py` -> `tests/unit/scheduler/test_cron_scheduling_service.py`

- [ ] **Step 1: Write failing tests**

Update scheduling tests to import from `scheduler.app.services.cron.scheduling_service`. Add a Monitor app test asserting Monitor lifespan no longer starts `monitor-cron-scheduling-service`.

- [ ] **Step 2: Run tests and verify failures**

Run: `& .\.venv\Scripts\python.exe -m pytest tests\unit\scheduler\test_cron_scheduling_service.py tests\unit\monitor\test_monitor_no_scheduler_runtime.py -q`

Expected: FAIL until moved and Monitor startup is removed.

- [ ] **Step 3: Move service and wire Scheduler lifespan**

Scheduler app lifespan connects to the shared DB, starts `CronSchedulingService.run_loop()` when enabled, and shuts down cleanly.

- [ ] **Step 4: Remove Monitor scheduler startup**

Monitor no longer imports or starts the scheduling loop from its lifespan.

- [ ] **Step 5: Run tests**

Run: `& .\.venv\Scripts\python.exe -m pytest tests\unit\scheduler\test_cron_scheduling_service.py tests\unit\monitor\test_monitor_no_scheduler_runtime.py -q`

Expected: PASS.

### Task 4: Route Dispatch Completion Feedback To Scheduler

**Files:**
- Modify: `src/swe/app/crons/monitor_sync_client.py`
- Modify: `monitor/src/monitor/app/services/cron/sync_service.py`
- Create/Modify: `tests/unit/scheduler/test_scheduler_execution_feedback.py`
- Modify: `tests/unit/app/test_monitor_sync_client.py`

- [ ] **Step 1: Write failing tests**

Add tests showing dispatch-managed execution records are posted to Scheduler, not Monitor, and Scheduler persists the Monitor execution row before updating the intent and refilling.

- [ ] **Step 2: Run tests and verify failures**

Run: `& .\.venv\Scripts\python.exe -m pytest tests\unit\scheduler\test_scheduler_execution_feedback.py tests\unit\app\test_monitor_sync_client.py -q`

Expected: FAIL until endpoint/client routing is implemented.

- [ ] **Step 3: Add Scheduler execution feedback endpoint**

Scheduler endpoint accepts Monitor `ExecutionSyncRequest`, uses Monitor `SyncService.record_execution()` to persist execution, then calls `CronSchedulingService.handle_execution_recorded()`.

- [ ] **Step 4: Keep Monitor as storage only**

Monitor `SyncService.record_execution()` stays storage-only; Scheduler performs the dispatch intent update after the execution row is persisted. Monitor route does not import Scheduler or update intents in-process.

- [ ] **Step 5: Update SWE client**

Dispatch-managed execution meta posts to `SWE_SCHEDULER_API_URL` with bounded retry. Non-dispatch execution records still post to Monitor.

- [ ] **Step 6: Run tests**

Run: `& .\.venv\Scripts\python.exe -m pytest tests\unit\scheduler\test_scheduler_execution_feedback.py tests\unit\app\test_monitor_sync_client.py -q`

Expected: PASS.

### Task 5: Update Durable Documentation

**Files:**
- Modify: `CONTEXT.md`
- Modify: `docs/adr/0010-independent-cron-scheduling-service-owns-batch-dispatch.md`
- Modify: `docs/plans/2026-07-01-001-independent-cron-scheduling-service-design.md`
- Modify: `docs/plans/2026-07-01-002-independent-cron-scheduling-service-leadership-report.md`

- [ ] **Step 1: Update terminology**

Change `Dispatch Intent Queue` from Monitor-owned to Scheduler-owned durable queue. Keep Monitor described as the observability and persistence read/write surface.

- [ ] **Step 2: Update ADR**

Record that the physical service boundary is `scheduler`, not Monitor lifespan.

- [ ] **Step 3: Run doc/code grep**

Run: `rg -n "Monitor .*scheduling loop|Monitor-owned durable queue|monitor-cron-scheduling-service" CONTEXT.md docs monitor/src scheduler/src tests`

Expected: no stale claims that Monitor hosts the scheduler loop.

### Task 6: Final Verification

**Files:**
- All touched files.

- [ ] **Step 1: Run targeted backend tests**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\unit\scheduler tests\unit\routers\test_internal_tenant_scope.py tests\unit\app\test_external_cron_scope_refresh.py tests\unit\app\test_monitor_sync_client.py -q
```

- [ ] **Step 2: Run Python compile check**

Run:

```powershell
& .\.venv\Scripts\python.exe -m py_compile scheduler\src\scheduler\app\_app.py scheduler\src\scheduler\app\routers\cron.py scheduler\src\scheduler\app\services\cron\scheduling_service.py scheduler\src\scheduler\app\services\cron\dispatch_intent_service.py monitor\src\monitor\app\_app.py monitor\src\monitor\app\services\cron\sync_service.py src\swe\app\crons\monitor_sync_client.py src\swe\app\routers\internal.py
```

- [ ] **Step 3: Run frontend cron helper test**

Run: `.\node_modules\.bin\vitest.cmd run src/pages/Control/CronJobs/helpers.test.ts`

- [ ] **Step 4: Review final diff**

Confirm the scheduler service is physically separate and Monitor no longer starts dispatch scheduling.
