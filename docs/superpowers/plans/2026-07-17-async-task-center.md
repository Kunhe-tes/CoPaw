# Async Task Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first version of a unified async task center where `swe` and `market` write task records into shared tables and `monitor` exposes task list/detail queries for Console.

**Architecture:** Use layer 1 sharing: shared database schema and field contract, no shared Python package and no Monitor write API. `swe` and `market` each implement a thin local task writer against the same `swe_async_tasks` and `swe_async_task_items` tables; `monitor` reads the same tables through its existing MySQL connection.

**Tech Stack:** Python, FastAPI, aiomysql/MySQL, Pydantic, React, TypeScript, Ant Design/AgentScope Console patterns.

---

## File Structure

- Create `src/swe/app/async_tasks/store.py`: SWE local writer for task master/items.
- Create `src/swe/app/async_tasks/__init__.py`: exports SWE async task writer.
- Create `market/src/market/app/async_tasks/store.py`: Market local writer for the same task schema.
- Create `market/src/market/app/async_tasks/__init__.py`: exports Market async task writer.
- Modify `monitor/src/monitor/app/database/schema.py`: create `swe_async_tasks` and `swe_async_task_items`.
- Create `monitor/src/monitor/app/models/async_task.py`: response/query models.
- Create `monitor/src/monitor/app/services/async_task/query_service.py`: task list/detail SQL.
- Create `monitor/src/monitor/app/routers/async_tasks.py`: `GET /api/tasks` and `GET /api/tasks/{task_id}`.
- Modify `monitor/src/monitor/app/routers/__init__.py`: register async task router.
- Modify existing submit endpoints:
  - `src/swe/app/crons/api.py`
  - `src/swe/app/routers/providers.py`
  - `src/swe/app/workspace/tenant_pool.py` or user-visible tenant bootstrap call sites
  - `market/src/market/app/routers/skills_market.py`
  - `market/src/market/app/routers/mcp_market.py`
- Add Console task API and page:
  - `console/src/api/types/asyncTask.ts`
  - `console/src/api/modules/asyncTask.ts`
  - `console/src/pages/AsyncTasks/index.tsx`
  - `console/src/pages/AsyncTasks/index.module.less`
  - `console/src/layouts/MainLayout/index.tsx`

## Task 1: Shared Tables And Monitor Query API

**Files:**
- Modify: `monitor/src/monitor/app/database/schema.py`
- Create: `monitor/src/monitor/app/models/async_task.py`
- Create: `monitor/src/monitor/app/services/async_task/query_service.py`
- Create: `monitor/src/monitor/app/services/async_task/__init__.py`
- Create: `monitor/src/monitor/app/routers/async_tasks.py`
- Modify: `monitor/src/monitor/app/routers/__init__.py`
- Test: `monitor/tests/test_async_tasks_query_api.py`

- [ ] **Step 1: Write failing monitor tests**

Create tests that seed fake DB rows through a fake connection and verify:

```python
async def test_list_async_tasks_returns_paginated_rows():
    service = AsyncTaskQueryService(FakeDb([...]))
    result = await service.list_tasks(source_id="src1", page=1, page_size=20)
    assert result.total == 1
    assert result.items[0].task_id == "task-1"

async def test_get_async_task_returns_items():
    service = AsyncTaskQueryService(FakeDb([...], items=[...]))
    result = await service.get_task("task-1")
    assert result.task_id == "task-1"
    assert result.items[0].target_id == "tenant-a"
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
venv/bin/python -m pytest monitor/tests/test_async_tasks_query_api.py -q
```

Expected: import failure for missing `monitor.app.services.async_task`.

- [ ] **Step 3: Add schema and query implementation**

Add two tables:

```sql
CREATE TABLE IF NOT EXISTS swe_async_tasks (
  task_id VARCHAR(64) PRIMARY KEY,
  service VARCHAR(32) NOT NULL,
  task_type VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  title VARCHAR(255) NOT NULL,
  summary VARCHAR(1024) DEFAULT NULL,
  source_id VARCHAR(128) DEFAULT NULL,
  tenant_id VARCHAR(255) DEFAULT NULL,
  actor_user_id VARCHAR(255) DEFAULT NULL,
  actor_user_name VARCHAR(255) DEFAULT NULL,
  target_count INT NOT NULL DEFAULT 0,
  done_count INT NOT NULL DEFAULT 0,
  failed_count INT NOT NULL DEFAULT 0,
  error_message TEXT DEFAULT NULL,
  result_json JSON DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  finished_at DATETIME DEFAULT NULL,
  INDEX idx_async_tasks_status (status),
  INDEX idx_async_tasks_type (task_type),
  INDEX idx_async_tasks_source (source_id),
  INDEX idx_async_tasks_created (created_at)
);
```

```sql
CREATE TABLE IF NOT EXISTS swe_async_task_items (
  task_id VARCHAR(64) NOT NULL,
  target_id VARCHAR(255) NOT NULL,
  target_name VARCHAR(255) DEFAULT NULL,
  status VARCHAR(32) NOT NULL,
  error_message TEXT DEFAULT NULL,
  result_json JSON DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (task_id, target_id),
  INDEX idx_async_task_items_status (status)
);
```

- [ ] **Step 4: Verify monitor tests pass**

Run:

```bash
venv/bin/python -m pytest monitor/tests/test_async_tasks_query_api.py -q
```

Expected: pass.

## Task 2: SWE Thin Writer And Provider Distribution Async Acceptance

**Files:**
- Create: `src/swe/app/async_tasks/store.py`
- Create: `src/swe/app/async_tasks/__init__.py`
- Modify: `src/swe/app/routers/providers.py`
- Test: `tests/unit/app/test_async_task_store.py`
- Test: `tests/unit/routers/test_provider_active_model_distribution.py`
- Test: `tests/unit/routers/test_providers_distribution.py`

- [ ] **Step 1: Write failing SWE store tests**

Test local writer behavior:

```python
async def test_start_task_inserts_master_and_items(fake_db):
    store = AsyncTaskStore(fake_db)
    await store.start_task(task_id="task-1", service="swe", task_type="provider.providers.distribute", title="分发供应商配置", target_ids=["a", "b"])
    assert fake_db.executed_many_count == 2
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_async_task_store.py -q
```

Expected: import failure for missing `swe.app.async_tasks`.

- [ ] **Step 3: Implement SWE writer**

Implement methods:

- `start_task(...)`
- `mark_running(task_id)`
- `record_item_result(task_id, target_id, success, result, error_message)`
- `finish_task(task_id)`
- `fail_task(task_id, error_message)`

- [ ] **Step 4: Convert provider distribution endpoints**

Change:

- `POST /models/distribution/active-llm`
- `POST /models/distribution/providers`

to return accepted task payload:

```json
{"task_id":"...","status":"queued","reused":false}
```

and run old per-tenant logic in an `asyncio.create_task` background coroutine.

- [ ] **Step 5: Verify provider tests**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_async_task_store.py tests/unit/routers/test_provider_active_model_distribution.py tests/unit/routers/test_providers_distribution.py -q
```

Expected: pass after updating expected response contracts.

## Task 3: SWE Cron Broadcast And Tenant Bootstrap Async Recording

**Files:**
- Modify: `src/swe/app/crons/api.py`
- Modify: user-visible tenant bootstrap call sites that call `TenantInitializer.ensure_seeded_bootstrap()`
- Test: `tests/unit/app/test_cron_broadcast_task_store.py`
- Test: `tests/unit/workspace/test_tenant_initializer.py`

- [ ] **Step 1: Add failing cron async task integration tests**

Assert cron broadcast returns accepted task payload and writes async task records using the SWE local writer.

- [ ] **Step 2: Verify tests fail**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_cron_broadcast_task_store.py -q
```

- [ ] **Step 3: Wire cron broadcast to unified task tables**

Keep existing cron broadcast task behavior where needed, but mirror task summary/item state into `swe_async_tasks` and `swe_async_task_items`.

- [ ] **Step 4: Add tenant bootstrap task records**

When a user-visible initialization call triggers bootstrap, record `tenant.bootstrap`.

- [ ] **Step 5: Verify targeted tests**

Run:

```bash
venv/bin/python -m pytest tests/unit/app/test_cron_broadcast_task_store.py tests/unit/workspace/test_tenant_initializer.py -q
```

## Task 4: Market Thin Writer And Skill/MCP Distribution Async Acceptance

**Files:**
- Create: `market/src/market/app/async_tasks/store.py`
- Create: `market/src/market/app/async_tasks/__init__.py`
- Modify: `market/src/market/app/routers/skills_market.py`
- Modify: `market/src/market/app/routers/mcp_market.py`
- Test: `market/tests/unit/marketplace/test_async_task_store.py`
- Test: `market/tests/unit/marketplace/test_skills_market.py`
- Test: `market/tests/unit/marketplace/test_mcp_models.py`

- [ ] **Step 1: Write failing market store tests**

Mirror SWE writer tests against Market's local `DatabaseConnection` shape.

- [ ] **Step 2: Verify tests fail**

Run:

```bash
venv/bin/python -m pytest market/tests/unit/marketplace/test_async_task_store.py -q
```

- [ ] **Step 3: Implement Market writer**

Use the same table names, columns, statuses, and item result semantics as SWE.

- [ ] **Step 4: Convert skill and MCP distribution routes**

Change:

- `POST /market/skills/{item_id}/distribute`
- `POST /market/mcp/{item_id}/distribute`

to accepted task responses and background execution.

- [ ] **Step 5: Verify market tests**

Run:

```bash
venv/bin/python -m pytest market/tests/unit/marketplace/test_async_task_store.py market/tests/unit/marketplace/test_skills_market.py market/tests/unit/marketplace/test_mcp_models.py -q
```

## Task 5: Console Async Task Center

**Files:**
- Create: `console/src/api/types/asyncTask.ts`
- Create: `console/src/api/modules/asyncTask.ts`
- Create: `console/src/pages/AsyncTasks/index.tsx`
- Create: `console/src/pages/AsyncTasks/index.module.less`
- Modify: `console/src/layouts/MainLayout/index.tsx`
- Modify: submit flows in Cron, Market, and Models pages.
- Test: `console/src/api/modules/asyncTask.test.ts`
- Test: `console/src/pages/AsyncTasks/index.test.tsx`

- [ ] **Step 1: Write failing API/page tests**

Assert API calls `/monitor/tasks` or the repo's monitor proxy path and page renders task rows with status/progress.

- [ ] **Step 2: Verify tests fail**

Run:

```bash
cd console && npm run test:run -- asyncTask
```

- [ ] **Step 3: Add API types and page**

Build a white-first management table page with filters, status badges, progress counts, and detail drawer.

- [ ] **Step 4: Update submit flows**

Replace “分发完成” copy with “任务已受理”， link to `/async-tasks?task_id=...` where useful.

- [ ] **Step 5: Verify frontend tests**

Run:

```bash
cd console && npm run test:run -- asyncTask
```

## Task 6: Final Verification

**Files:**
- All changed files

- [ ] **Step 1: Run targeted backend tests**

```bash
venv/bin/python -m pytest tests/unit/app/test_async_task_store.py tests/unit/routers/test_provider_active_model_distribution.py tests/unit/routers/test_providers_distribution.py monitor/tests/test_async_tasks_query_api.py -q
```

- [ ] **Step 2: Run targeted market tests**

```bash
venv/bin/python -m pytest market/tests/unit/marketplace/test_async_task_store.py market/tests/unit/marketplace/test_skills_market.py -q
```

- [ ] **Step 3: Run targeted frontend tests**

```bash
cd console && npm run test:run -- asyncTask
```

- [ ] **Step 4: Review git diff**

```bash
git diff --stat
git diff -- docs/superpowers/specs/2026-07-17-async-task-center-design.md
```

Expected: implementation matches Monitor-query / SWE-Market-write spec and leaves unrelated `.gitignore` / `analysis/README.md` edits untouched.

