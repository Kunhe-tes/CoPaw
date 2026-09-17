# Async Cron Broadcast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert scheduled-job broadcast into a source-job-level background task with durable per-target progress and one-shot current-status lookup from Console.

**Architecture:** Add a dedicated broadcast task store beside the existing broadcast-children snapshot store. The existing broadcast child creation/refresh helpers remain the source of truth for child job idempotence, while the new task layer records operation progress and drives an async HTTP contract.

**Tech Stack:** FastAPI, Pydantic, asyncio background tasks, existing DB wrapper, React/TypeScript Console, Vitest, pytest.

---

### Task 1: Backend Broadcast Task Store

**Files:**
- Create: `src/swe/app/crons/broadcast_task_store.py`
- Modify: `src/swe/app/_app.py`
- Test: `tests/unit/app/test_cron_broadcast_task_store.py`

- [ ] **Step 1: Write failing store tests**

Add tests for memory fallback and DB-backed SQL shape:

```python
def test_memory_store_tracks_target_progress():
    store = CronBroadcastTaskStore()
    task = asyncio.run(store.start_task(...))
    asyncio.run(store.mark_target_running(task.task_id, "tenant-a"))
    asyncio.run(store.record_target_result(task.task_id, result_payload))
    snapshot = asyncio.run(store.get_task(task.task_id))
    assert snapshot.completed_count == 1
```

Run: `& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_cron_broadcast_task_store.py -q`

Expected: FAIL because `CronBroadcastTaskStore` does not exist.

- [ ] **Step 2: Implement minimal store**

Create dataclasses/Pydantic-friendly objects:

```python
BroadcastTaskStatus = Literal["running", "completed", "failed"]

@dataclass(slots=True)
class CronBroadcastTaskSnapshot:
    task_id: str
    agent_id: str
    source_id: str
    tenant_id: str
    job_id: str
    status: BroadcastTaskStatus
    tenant_count: int
    completed_count: int
    failed_count: int
    results: list[dict[str, Any]]
```

Implement methods `initialize()`, `start_task()`, `get_task()`, `mark_target_running()`, `record_target_result()`, and `finish_task()`. Use DB tables `swe_cron_broadcast_tasks` and `swe_cron_broadcast_task_items` when connected; otherwise use in-memory dictionaries.

- [ ] **Step 3: Wire app startup**

Add `_initialize_cron_broadcast_task_store()` near `_initialize_cron_broadcast_children_store()` and set `app.state.cron_broadcast_task_store`.

- [ ] **Step 4: Run store tests green**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_cron_broadcast_task_store.py -q`

Expected: PASS.

### Task 2: Backend Async Broadcast Routes

**Files:**
- Modify: `src/swe/app/crons/api.py`
- Test: `tests/unit/app/test_tenant_cron_api.py`

- [ ] **Step 1: Write failing API tests**

Add tests that:
- `POST /cron/jobs/{job_id}/broadcast` returns `task_id`, `status=running`, `tenant_count`, and does not wait for delayed target processing.
- `GET /cron/jobs/{job_id}/broadcast/tasks/current` returns the currently running task for the source job, if any.
- `GET /cron/jobs/{job_id}/broadcast/tasks/{task_id}` returns a task snapshot by id for direct lookup.
- Repeated target processing refreshes existing child jobs rather than creating duplicates.

Run: `& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_tenant_cron_api.py -k "broadcast_task or broadcast_job_persists_target_identity_from_request" -q`

Expected: FAIL because the async response and task route do not exist.

- [ ] **Step 2: Add response models and helpers**

Add `CronBroadcastTaskResponse` with `task_id`, `status`, `tenant_count`, `completed_count`, `failed_count`, `results`, `updated_at`, and `reused`.

Add helpers:
- `_get_broadcast_task_store(request)`
- `_broadcast_task_key_parts(request, source_job)`
- `_schedule_broadcast_task(...)`
- `_run_broadcast_task(...)`

- [ ] **Step 3: Change broadcast submit route**

Make `broadcast_job()` create or reuse a task and return the task summary immediately. Background execution calls existing `_broadcast_to_tenant()` under the existing concurrency helper and records each result.

- [ ] **Step 4: Add task lookup routes**

Add `GET /jobs/{job_id}/broadcast/tasks/{task_id}`. It returns 404 if the source job or task does not exist.

- [ ] **Step 5: Run API tests green**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_tenant_cron_api.py tests/unit/app/test_cron_broadcast_task_store.py -q`

Expected: PASS.

### Task 3: Console Broadcast Polling

**Files:**
- Modify: `console/src/api/types/cronjob.ts`
- Modify: `console/src/api/modules/cronjob.ts`
- Modify: `console/src/pages/Control/CronJobs/index.tsx`
- Modify: `console/src/pages/Control/CronJobs/helpers.ts`
- Test: `console/src/pages/Control/CronJobs/helpers.test.ts`

- [ ] **Step 1: Write failing frontend tests**

Extend helper tests for task result messages:

```ts
expect(getBroadcastTaskProgressText({ status: "running", tenant_count: 3, completed_count: 1, failed_count: 0 })).toBe("Broadcasting 1/3 tenants");
```

Run: `.\node_modules\.bin\vitest.cmd run console/src/pages/Control/CronJobs/helpers.test.ts`

Expected: FAIL because helper/types do not exist.

- [ ] **Step 2: Update API types and client**

Change `broadcastCronJob()` to return `CronBroadcastTaskResponse`. Add `getCronBroadcastTask(jobId, taskId)`.

- [ ] **Step 3: Update modal state**

After submit, set `broadcastTask` from the response and show progress without continuous polling. When the modal opens, query the current running task once and disable starting another broadcast while it is running. Keep existing offset controls, target selector, and per-target result list.

- [ ] **Step 4: Run frontend tests green**

Run: `.\node_modules\.bin\vitest.cmd run console/src/pages/Control/CronJobs/helpers.test.ts`

Expected: PASS.

### Task 4: Final Verification

**Files:**
- Modify: `openspec/changes/add-async-cron-broadcast/tasks.md`

- [ ] **Step 1: Mark OpenSpec tasks complete as implementation slices pass**

Only check off tasks after corresponding tests pass.

- [ ] **Step 2: Run targeted verification**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_cron_broadcast_task_store.py tests/unit/app/test_tenant_cron_api.py -q
.\node_modules\.bin\vitest.cmd run console/src/pages/Control/CronJobs/helpers.test.ts
$env:POSTHOG_DISABLED='1'; openspec.cmd status --change "add-async-cron-broadcast"
```

- [ ] **Step 3: Run impact checks**

Run GitNexus `detect_changes` with the worktree path and inspect affected symbols.
