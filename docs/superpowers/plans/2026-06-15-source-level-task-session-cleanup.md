# Source-Level Task Session Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register and execute the task-session-history cleanup as one source-level system task per `source_id`, not one task per tenant workspace.

**Architecture:** Keep cleanup configuration in `swe_source_system_config`, add a source-level task binding store keyed by `(source_id, task_type)`, and add a source-level scheduler service that creates/updates/pauses one external scheduler job per source. Tenant identity values remain in scheduler payload for audit/compatibility, but they no longer define task uniqueness or cleanup scope.

**Tech Stack:** Python 3.12, FastAPI, existing async DB wrapper, existing `RealSchedulerAdapter`, pytest, MySQL migration SQL under `scripts/sql/`.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `scripts/sql/source_system_task_binding.sql` | Creates the source-level binding table for external system task IDs. |
| `src/swe/app/source_system_config/task_binding_store.py` | Async DB store for `(source_id, task_type)` bindings. |
| `src/swe/app/source_system_config/task_scheduler.py` | Source-level scheduler and cleanup runner orchestration. |
| `src/swe/app/source_system_config/router.py` | Calls source-level scheduler after current source config changes. |
| `src/swe/app/_app.py` | Wires the binding store and source scheduler into `app.state`. |
| `src/swe/app/crons/scheduler_adapter.py` | Supports source-level cleanup job names and explicit `scopeId/fromId` payload values. |
| `src/swe/app/crons/manager.py` | Removes cleanup system-task registration from tenant `CronManager.initialize()`. |
| `src/swe/app/routers/internal.py` | Routes cleanup callback through source-level cleanup using `source_id`. |
| `tests/unit/app/test_source_system_task_scheduler.py` | Unit tests for source-level scheduler behavior and concurrency. |
| `tests/unit/app/test_external_cron_scope_refresh.py` | Adjusts old cleanup registration tests to assert it no longer happens via `CronManager`. |
| `tests/unit/app/test_source_system_config.py` | Verifies config upsert/delete refreshes source-level scheduler with last updater identity. |

## Existing Behavior To Preserve

- Ordinary business cron jobs still include tenant/source/agent/task/job in scheduler payload.
- Heartbeat and dream still register from tenant `CronManager`.
- Cleanup execution still prunes task session state using the existing pruning helpers and retention-day semantics.
- `tenant_id`, `scopeId`, and `fromId` remain in scheduler `jobParam` for cleanup jobs, using the last config modifier's request identity.

---

### Task 1: Add Source System Task Binding Store

**Files:**
- Create: `scripts/sql/source_system_task_binding.sql`
- Create: `src/swe/app/source_system_config/task_binding_store.py`
- Test: `tests/unit/app/test_source_system_task_scheduler.py`

- [ ] **Step 1: Write binding store tests**

Create `tests/unit/app/test_source_system_task_scheduler.py` with these initial tests:

```python
# -*- coding: utf-8 -*-
"""Source 级系统任务调度回归测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from swe.app.source_system_config.task_binding_store import (
    SourceSystemTaskBinding,
    SourceSystemTaskBindingStore,
)


class _FakeDb:
    def __init__(self) -> None:
        self.is_connected = True
        self.rows: dict[tuple[str, str], dict] = {}
        self.executed: list[tuple[str, tuple]] = []

    async def fetch_one(self, query: str, params: tuple):
        if "SELECT source_id" in query:
            key = (params[0], params[1])
            return self.rows.get(key)
        return None

    async def execute(self, query: str, params: tuple):
        self.executed.append((query, params))
        source_id, task_type = params[0], params[1]
        key = (source_id, task_type)
        if "INSERT INTO swe_source_system_task_binding" in query:
            row = self.rows.get(key, {})
            self.rows[key] = {
                "source_id": source_id,
                "task_type": task_type,
                "external_job_id": params[2],
                "cron": params[3],
                "enabled": params[4],
                "scheduler_tenant_id": params[5],
                "scheduler_scope_id": params[6],
                "scheduler_from_id": params[7],
                "updated_by": params[8],
                "updated_at": row.get("updated_at"),
            }
        return 1


@pytest.mark.asyncio
async def test_binding_store_upserts_and_reads_source_task_binding() -> None:
    db = _FakeDb()
    store = SourceSystemTaskBindingStore(db)

    binding = await store.upsert_binding(
        source_id="source-a",
        task_type="task_session_cleanup",
        external_job_id="1001",
        cron="30 2 * * *",
        enabled=True,
        scheduler_tenant_id="tenant-a",
        scheduler_scope_id="tenant-a-source-a",
        scheduler_from_id="tenant-a",
        updated_by="alice",
    )

    assert binding == SourceSystemTaskBinding(
        source_id="source-a",
        task_type="task_session_cleanup",
        external_job_id="1001",
        cron="30 2 * * *",
        enabled=True,
        scheduler_tenant_id="tenant-a",
        scheduler_scope_id="tenant-a-source-a",
        scheduler_from_id="tenant-a",
        updated_by="alice",
        updated_at=None,
    )
    assert await store.get_binding("source-a", "task_session_cleanup") == binding
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/app/test_source_system_task_scheduler.py::test_binding_store_upserts_and_reads_source_task_binding -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'swe.app.source_system_config.task_binding_store'`.

- [ ] **Step 3: Create the migration SQL**

Create `scripts/sql/source_system_task_binding.sql`:

```sql
CREATE TABLE IF NOT EXISTS `swe_source_system_task_binding` (
  `source_id` varchar(128) NOT NULL COMMENT '来源系统 ID',
  `task_type` varchar(64) NOT NULL COMMENT 'source 级系统任务类型',
  `external_job_id` varchar(128) DEFAULT NULL COMMENT '外部调度平台任务 ID',
  `cron` varchar(128) DEFAULT NULL COMMENT '最后一次注册使用的 cron',
  `enabled` tinyint(1) NOT NULL DEFAULT 0 COMMENT '最后一次注册时的启用状态',
  `scheduler_tenant_id` varchar(256) DEFAULT NULL COMMENT '最后修改配置的 tenant_id',
  `scheduler_scope_id` varchar(512) DEFAULT NULL COMMENT '最后修改配置的 scopeId',
  `scheduler_from_id` varchar(256) DEFAULT NULL COMMENT '最后修改配置的 fromId',
  `updated_by` varchar(256) DEFAULT NULL COMMENT '最后修改配置的用户',
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`source_id`, `task_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Source 级系统任务外部调度绑定';
```

- [ ] **Step 4: Implement the binding store**

Create `src/swe/app/source_system_config/task_binding_store.py`:

```python
# -*- coding: utf-8 -*-
"""Source 级系统任务外部调度绑定存储。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .store import SourceSystemConfigStoreUnavailable


@dataclass(frozen=True)
class SourceSystemTaskBinding:
    """Source 级系统任务与外部调度平台任务 ID 的绑定。"""

    source_id: str
    task_type: str
    external_job_id: str
    cron: str
    enabled: bool
    scheduler_tenant_id: str
    scheduler_scope_id: str
    scheduler_from_id: str
    updated_by: str | None
    updated_at: Any | None = None


class SourceSystemTaskBindingStore:
    """按 source_id 和 task_type 读写系统任务绑定。"""

    def __init__(self, db: Any | None = None):
        self.db = db

    @property
    def is_available(self) -> bool:
        """返回绑定存储是否可用。"""
        return self.db is not None and bool(
            getattr(self.db, "is_connected", False),
        )

    def _require_db(self) -> Any:
        if not self.is_available:
            raise SourceSystemConfigStoreUnavailable(
                "source system task binding storage unavailable: "
                "db is not connected",
            )
        return self.db

    async def get_binding(
        self,
        source_id: str,
        task_type: str,
    ) -> SourceSystemTaskBinding | None:
        """读取 source 级系统任务绑定。"""
        db = self._require_db()
        row = await db.fetch_one(
            """
            SELECT source_id, task_type, external_job_id, cron, enabled,
                   scheduler_tenant_id, scheduler_scope_id,
                   scheduler_from_id, updated_by, updated_at
            FROM swe_source_system_task_binding
            WHERE source_id = %s AND task_type = %s
            """,
            (source_id, task_type),
        )
        if row is None:
            return None
        return self._row_to_binding(row)

    async def upsert_binding(
        self,
        *,
        source_id: str,
        task_type: str,
        external_job_id: str,
        cron: str,
        enabled: bool,
        scheduler_tenant_id: str,
        scheduler_scope_id: str,
        scheduler_from_id: str,
        updated_by: str | None,
    ) -> SourceSystemTaskBinding:
        """写入 source 级系统任务绑定。"""
        db = self._require_db()
        await db.execute(
            """
            INSERT INTO swe_source_system_task_binding
                (source_id, task_type, external_job_id, cron, enabled,
                 scheduler_tenant_id, scheduler_scope_id, scheduler_from_id,
                 updated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                external_job_id = VALUES(external_job_id),
                cron = VALUES(cron),
                enabled = VALUES(enabled),
                scheduler_tenant_id = VALUES(scheduler_tenant_id),
                scheduler_scope_id = VALUES(scheduler_scope_id),
                scheduler_from_id = VALUES(scheduler_from_id),
                updated_by = VALUES(updated_by),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                source_id,
                task_type,
                external_job_id,
                cron,
                1 if enabled else 0,
                scheduler_tenant_id,
                scheduler_scope_id,
                scheduler_from_id,
                updated_by,
            ),
        )
        binding = await self.get_binding(source_id, task_type)
        if binding is None:
            raise ValueError(
                "source system task binding upsert did not return row: "
                f"{source_id}/{task_type}",
            )
        return binding

    @staticmethod
    def _row_to_binding(row: dict[str, Any]) -> SourceSystemTaskBinding:
        return SourceSystemTaskBinding(
            source_id=str(row["source_id"]),
            task_type=str(row["task_type"]),
            external_job_id=str(row.get("external_job_id") or ""),
            cron=str(row.get("cron") or ""),
            enabled=bool(row.get("enabled")),
            scheduler_tenant_id=str(row.get("scheduler_tenant_id") or ""),
            scheduler_scope_id=str(row.get("scheduler_scope_id") or ""),
            scheduler_from_id=str(row.get("scheduler_from_id") or ""),
            updated_by=row.get("updated_by"),
            updated_at=row.get("updated_at"),
        )
```

- [ ] **Step 5: Verify Task 1**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/app/test_source_system_task_scheduler.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```powershell
git add scripts/sql/source_system_task_binding.sql src/swe/app/source_system_config/task_binding_store.py tests/unit/app/test_source_system_task_scheduler.py
git commit -m "feat(source-config): add source task binding store"
```

---

### Task 2: Add Source-Level Cleanup Scheduler

**Files:**
- Create: `src/swe/app/source_system_config/task_scheduler.py`
- Modify: `tests/unit/app/test_source_system_task_scheduler.py`

- [ ] **Step 1: Add scheduler tests for create/update/pause**

Append these tests to `tests/unit/app/test_source_system_task_scheduler.py`:

```python
from swe.app.source_system_config.models import (
    EffectiveSourceSystemConfig,
    SourceSystemConfig,
)
from swe.app.source_system_config.task_scheduler import (
    SourceSchedulerIdentity,
    SourceSystemTaskScheduler,
)


class _CapturingAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def register_job(self, **kwargs):
        self.calls.append(("register", kwargs))
        return "1001"

    async def update_job(self, **kwargs):
        self.calls.append(("update", kwargs))

    async def pause_job(self, external_id: str):
        self.calls.append(("pause", {"external_id": external_id}))

    async def resume_job(self, external_id: str):
        self.calls.append(("resume", {"external_id": external_id}))


def _effective_source_config(source_id: str, raw: dict) -> EffectiveSourceSystemConfig:
    config = SourceSystemConfig.model_validate(raw)
    return EffectiveSourceSystemConfig(
        source_id=source_id,
        config=config.merged_with_defaults(),
        raw_config=config,
        version=1,
    )


def _identity(tenant_id: str = "tenant-a") -> SourceSchedulerIdentity:
    return SourceSchedulerIdentity(
        tenant_id=tenant_id,
        scope_id=f"{tenant_id}-source-a",
        from_id=tenant_id,
        updated_by="alice",
    )


@pytest.mark.asyncio
async def test_scheduler_registers_one_source_cleanup_job() -> None:
    db = _FakeDb()
    store = SourceSystemTaskBindingStore(db)
    adapter = _CapturingAdapter()
    scheduler = SourceSystemTaskScheduler(
        binding_store=store,
        scheduler_adapter=adapter,
        callback_url="http://swe.local/api/internal/cron/callback",
    )

    result = await scheduler.refresh_task_session_cleanup(
        source_id="source-a",
        config=_effective_source_config(
            "source-a",
            {
                "cron_task_session_cleanup": {
                    "enabled": True,
                    "retention_days": 30,
                    "cron": "30 2 * * *",
                },
            },
        ),
        identity=_identity(),
    )

    assert result == {
        "source_id": "source-a",
        "task_type": "task_session_cleanup",
        "action": "registered",
        "external_job_id": "1001",
    }
    assert adapter.calls[0][0] == "register"
    kwargs = adapter.calls[0][1]
    assert kwargs["tenant_id"] == "tenant-a"
    assert kwargs["source_id"] == "source-a"
    assert kwargs["agent_id"] == ""
    assert kwargs["task_type"] == "cleanup"
    assert kwargs["job_id"] == "_source_task_session_cleanup"
    assert kwargs["job_name"] == "task_session_cleanup"
    assert kwargs["cron"] == "30 2 * * *"
    assert kwargs["scope_id"] == "tenant-a-source-a"
    assert kwargs["from_id"] == "tenant-a"


@pytest.mark.asyncio
async def test_scheduler_updates_existing_source_cleanup_identity() -> None:
    db = _FakeDb()
    store = SourceSystemTaskBindingStore(db)
    await store.upsert_binding(
        source_id="source-a",
        task_type="task_session_cleanup",
        external_job_id="1001",
        cron="30 2 * * *",
        enabled=True,
        scheduler_tenant_id="tenant-a",
        scheduler_scope_id="tenant-a-source-a",
        scheduler_from_id="tenant-a",
        updated_by="alice",
    )
    adapter = _CapturingAdapter()
    scheduler = SourceSystemTaskScheduler(
        binding_store=store,
        scheduler_adapter=adapter,
        callback_url="http://swe.local/api/internal/cron/callback",
    )

    await scheduler.refresh_task_session_cleanup(
        source_id="source-a",
        config=_effective_source_config(
            "source-a",
            {
                "cron_task_session_cleanup": {
                    "enabled": True,
                    "retention_days": 45,
                    "cron": "0 3 * * *",
                },
            },
        ),
        identity=_identity("tenant-b"),
    )

    assert adapter.calls[0][0] == "update"
    assert adapter.calls[0][1]["external_id"] == "1001"
    assert adapter.calls[0][1]["tenant_id"] == "tenant-b"
    assert adapter.calls[0][1]["scope_id"] == "tenant-b-source-a"
    assert adapter.calls[1] == ("resume", {"external_id": "1001"})
    binding = await store.get_binding("source-a", "task_session_cleanup")
    assert binding is not None
    assert binding.scheduler_tenant_id == "tenant-b"
    assert binding.scheduler_scope_id == "tenant-b-source-a"
    assert binding.scheduler_from_id == "tenant-b"


@pytest.mark.asyncio
async def test_scheduler_pauses_disabled_source_cleanup_job() -> None:
    db = _FakeDb()
    store = SourceSystemTaskBindingStore(db)
    await store.upsert_binding(
        source_id="source-a",
        task_type="task_session_cleanup",
        external_job_id="1001",
        cron="30 2 * * *",
        enabled=True,
        scheduler_tenant_id="tenant-a",
        scheduler_scope_id="tenant-a-source-a",
        scheduler_from_id="tenant-a",
        updated_by="alice",
    )
    adapter = _CapturingAdapter()
    scheduler = SourceSystemTaskScheduler(
        binding_store=store,
        scheduler_adapter=adapter,
        callback_url="http://swe.local/api/internal/cron/callback",
    )

    result = await scheduler.refresh_task_session_cleanup(
        source_id="source-a",
        config=_effective_source_config(
            "source-a",
            {"cron_task_session_cleanup": {"enabled": False}},
        ),
        identity=_identity("tenant-b"),
    )

    assert result["action"] == "paused"
    assert adapter.calls == [("pause", {"external_id": "1001"})]
```

- [ ] **Step 2: Run the failing scheduler tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/app/test_source_system_task_scheduler.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'swe.app.source_system_config.task_scheduler'`.

- [ ] **Step 3: Implement source-level scheduler**

Create `src/swe/app/source_system_config/task_scheduler.py`:

```python
# -*- coding: utf-8 -*-
"""Source 级系统任务注册与执行编排。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..crons.manager import TASK_SESSION_CLEANUP_TASK_TYPE
from ..source_system_config.registry import (
    resolve_cron_task_session_cleanup_config,
)
from .models import EffectiveSourceSystemConfig
from .task_binding_store import SourceSystemTaskBindingStore

logger = logging.getLogger(__name__)

SOURCE_TASK_SESSION_CLEANUP_JOB_ID = "_source_task_session_cleanup"
SOURCE_TASK_SESSION_CLEANUP_NAME = "task_session_cleanup"


@dataclass(frozen=True)
class SourceSchedulerIdentity:
    """最后修改 source 配置的调度平台身份。"""

    tenant_id: str
    scope_id: str
    from_id: str
    updated_by: str | None


class SourceSystemTaskScheduler:
    """按 source_id 注册和执行 source 级系统任务。"""

    def __init__(
        self,
        *,
        binding_store: SourceSystemTaskBindingStore,
        scheduler_adapter: Any,
        callback_url: str,
    ) -> None:
        self._binding_store = binding_store
        self._scheduler_adapter = scheduler_adapter
        self._callback_url = callback_url

    async def refresh_task_session_cleanup(
        self,
        *,
        source_id: str,
        config: EffectiveSourceSystemConfig,
        identity: SourceSchedulerIdentity,
    ) -> dict[str, Any]:
        """按 source 配置注册、更新或暂停清理系统任务。"""
        cleanup_config = resolve_cron_task_session_cleanup_config(config)
        binding = await self._binding_store.get_binding(
            source_id,
            SOURCE_TASK_SESSION_CLEANUP_NAME,
        )
        external_job_id = binding.external_job_id if binding else ""

        if not cleanup_config.enabled:
            if external_job_id:
                await self._scheduler_adapter.pause_job(external_job_id)
            await self._binding_store.upsert_binding(
                source_id=source_id,
                task_type=SOURCE_TASK_SESSION_CLEANUP_NAME,
                external_job_id=external_job_id,
                cron=cleanup_config.cron,
                enabled=False,
                scheduler_tenant_id=identity.tenant_id,
                scheduler_scope_id=identity.scope_id,
                scheduler_from_id=identity.from_id,
                updated_by=identity.updated_by,
            )
            return self._result(source_id, "paused", external_job_id)

        kwargs = self._scheduler_kwargs(
            source_id=source_id,
            cron=cleanup_config.cron,
            identity=identity,
        )
        if external_job_id:
            await self._scheduler_adapter.update_job(
                external_id=external_job_id,
                **kwargs,
            )
            await self._scheduler_adapter.resume_job(external_job_id)
            action = "updated"
        else:
            external_job_id = await self._scheduler_adapter.register_job(
                **kwargs,
            )
            action = "registered"

        await self._binding_store.upsert_binding(
            source_id=source_id,
            task_type=SOURCE_TASK_SESSION_CLEANUP_NAME,
            external_job_id=external_job_id,
            cron=cleanup_config.cron,
            enabled=True,
            scheduler_tenant_id=identity.tenant_id,
            scheduler_scope_id=identity.scope_id,
            scheduler_from_id=identity.from_id,
            updated_by=identity.updated_by,
        )
        return self._result(source_id, action, external_job_id)

    def _scheduler_kwargs(
        self,
        *,
        source_id: str,
        cron: str,
        identity: SourceSchedulerIdentity,
    ) -> dict[str, Any]:
        return {
            "tenant_id": identity.tenant_id,
            "source_id": source_id,
            "agent_id": "",
            "task_type": TASK_SESSION_CLEANUP_TASK_TYPE,
            "job_id": SOURCE_TASK_SESSION_CLEANUP_JOB_ID,
            "job_name": SOURCE_TASK_SESSION_CLEANUP_NAME,
            "cron": cron,
            "callback_url": self._callback_url,
            "scope_id": identity.scope_id,
            "from_id": identity.from_id,
            "source_level": True,
        }

    @staticmethod
    def _result(
        source_id: str,
        action: str,
        external_job_id: str,
    ) -> dict[str, Any]:
        return {
            "source_id": source_id,
            "task_type": SOURCE_TASK_SESSION_CLEANUP_NAME,
            "action": action,
            "external_job_id": external_job_id,
        }
```

- [ ] **Step 4: Verify Task 2**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/app/test_source_system_task_scheduler.py -q
```

Expected: FAIL only because `SchedulerAdapter.register_job()` and `update_job()` do not yet accept `scope_id`, `from_id`, or `source_level`. This failure is expected until Task 3. Do not commit until Task 3 passes.

---

### Task 3: Extend Scheduler Adapter Payload For Source-Level Cleanup

**Files:**
- Modify: `src/swe/app/crons/scheduler_adapter.py`
- Modify: `tests/unit/app/test_external_cron_scope_refresh.py`
- Test: `tests/unit/app/test_source_system_task_scheduler.py`

- [ ] **Step 1: Add adapter payload test**

Append this test to `tests/unit/app/test_external_cron_scope_refresh.py`:

```python
@pytest.mark.asyncio
async def test_source_cleanup_scheduler_payload_uses_source_only_job_name() -> None:
    """source 级清理任务名不拼 agentId 和 tenant_id。"""
    adapter = CapturingSchedulerAdapter()

    await adapter.register_job(
        tenant_id="tenant-a",
        source_id="source-a",
        agent_id="",
        task_type="cleanup",
        job_id="_source_task_session_cleanup",
        job_name="task_session_cleanup",
        cron="30 2 * * *",
        callback_url="http://swe.local/api/internal/cron/callback",
        scope_id="tenant-a-source-a",
        from_id="tenant-a",
        source_level=True,
    )

    _, payload = adapter.requests[0]
    assert payload["jobDesc"] == "[SWE] source-a/task_session_cleanup"
    job_param = _decode_job_param(payload["jobParam"])
    assert job_param["tenant_id"] == "tenant-a"
    assert job_param["source_id"] == "source-a"
    assert job_param["scopeId"] == "tenant-a-source-a"
    assert job_param["fromId"] == "tenant-a"
    assert job_param["agent_id"] == ""
    assert job_param["task_type"] == "cleanup"
    assert job_param["job_id"] == "_source_task_session_cleanup"
```

- [ ] **Step 2: Run adapter test to verify it fails**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/app/test_external_cron_scope_refresh.py::test_source_cleanup_scheduler_payload_uses_source_only_job_name -q
```

Expected: FAIL with `TypeError: RealSchedulerAdapter.register_job() got an unexpected keyword argument 'scope_id'`.

- [ ] **Step 3: Update adapter method signatures**

Modify `src/swe/app/crons/scheduler_adapter.py` by replacing the two method
definitions with these signatures and payload calls while keeping their
existing logging and `_post` behavior unchanged:

```python
async def register_job(
    self,
    tenant_id: str,
    agent_id: str,
    task_type: str,
    job_id: str,
    job_name: str,
    cron: str,
    callback_url: str,
    source_id: str = "",
    scope_id: str = "",
    from_id: str = "",
    source_level: bool = False,
) -> str:
    payload = self._build_add_payload(
        tenant_id,
        agent_id,
        task_type,
        job_id,
        job_name,
        cron,
        callback_url,
        source_id=source_id,
        scope_id=scope_id,
        from_id=from_id,
        source_level=source_level,
    )
    resp_data = await self._post("/job-admin/v2/add-job", payload)
    ext_id = str(resp_data.get("content", ""))
    logger.info(
        "RealAdapter registered job: ext_id=%s tenant=%s source=%s agent=%s type=%s job=%s",
        ext_id,
        tenant_id,
        source_id,
        agent_id,
        task_type,
        job_id,
    )
    await self._set_run_state(ext_id, run_flag=1)
    return ext_id


async def update_job(
    self,
    external_id: str,
    tenant_id: str,
    agent_id: str,
    task_type: str,
    job_id: str,
    job_name: str,
    cron: str,
    callback_url: str,
    source_id: str = "",
    scope_id: str = "",
    from_id: str = "",
    source_level: bool = False,
) -> None:
    payload = self._build_add_payload(
        tenant_id,
        agent_id,
        task_type,
        job_id,
        job_name,
        cron,
        callback_url,
        source_id=source_id,
        scope_id=scope_id,
        from_id=from_id,
        source_level=source_level,
    )
    payload["id"] = int(external_id)
    await self._post("/job-admin/v2/update-job", payload)
    logger.info(
        "RealAdapter updated job: ext_id=%s tenant=%s source=%s agent=%s type=%s job=%s",
        external_id,
        tenant_id,
        source_id,
        agent_id,
        task_type,
        job_id,
    )
```

Make the same optional keyword additions on `SchedulerAdapter.register_job`,
`SchedulerAdapter.update_job`, `NoopSchedulerAdapter.register_job`, and
`NoopSchedulerAdapter.update_job`. The noop methods only log, so their bodies
stay unchanged.

- [ ] **Step 4: Update `_build_job_param` and `_build_add_payload`**

Replace `_build_job_param` and update `_build_add_payload` in `src/swe/app/crons/scheduler_adapter.py`:

```python
@staticmethod
def _build_job_param(
    tenant_id: str,
    source_id: str,
    agent_id: str,
    task_type: str,
    job_id: str,
    *,
    scope_id: str = "",
    from_id: str = "",
) -> str:
    """将回调上下文参数编码为 base64 JSON，放入 jobParam。"""
    payload = json.dumps(
        {
            "tenant_id": tenant_id,
            "source_id": source_id,
            "scopeId": scope_id or f"{tenant_id}-{source_id}",
            "agent_id": agent_id,
            "task_type": task_type,
            "job_id": job_id,
            "fromId": from_id or tenant_id,
        },
    )
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _build_add_payload(
    self,
    tenant_id: str,
    agent_id: str,
    task_type: str,
    job_id: str,
    job_name: str,
    cron: str,
    callback_url: str,
    source_id: str = "",
    *,
    scope_id: str = "",
    from_id: str = "",
    source_level: bool = False,
) -> dict:
    """构建 add-job / update-job 的请求体。"""
    if source_level:
        job_desc = _truncate(
            f"[SWE] {source_id}/{job_name}",
            _MAX_JOBDESC_CHARS,
        )
    else:
        identity = tenant_id
        if source_id:
            identity = f"{tenant_id}/{source_id}"
        job_desc = _truncate(
            f"[SWE] {identity}/{agent_id}/{task_type} - {job_name}",
            _MAX_JOBDESC_CHARS,
        )
    "jobParam": self._build_job_param(
        tenant_id,
        source_id,
        agent_id,
        task_type,
        job_id,
        scope_id=scope_id,
        from_id=from_id,
    ),
```

- [ ] **Step 5: Verify adapter and scheduler tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/app/test_source_system_task_scheduler.py tests/unit/app/test_external_cron_scope_refresh.py::test_source_cleanup_scheduler_payload_uses_source_only_job_name -q
```

Expected: PASS.

- [ ] **Step 6: Commit Tasks 2 and 3**

```powershell
git add src/swe/app/source_system_config/task_scheduler.py src/swe/app/crons/scheduler_adapter.py tests/unit/app/test_source_system_task_scheduler.py tests/unit/app/test_external_cron_scope_refresh.py
git commit -m "feat(cron): register cleanup as source system task"
```

---

### Task 4: Wire Source Scheduler Into App And Config Router

**Files:**
- Modify: `src/swe/app/_app.py`
- Modify: `src/swe/app/source_system_config/router.py`
- Modify: `tests/unit/app/test_source_system_config.py`

- [ ] **Step 1: Add router tests for identity handoff**

In `tests/unit/app/test_source_system_config.py`, add a test near the current config upsert tests:

```python
@pytest.mark.asyncio
async def test_upsert_current_config_refreshes_source_cleanup_scheduler(
    monkeypatch,
) -> None:
    """保存 source 配置后使用最后修改人身份刷新 source 清理任务。"""
    from swe.app.source_system_config.router import (
        upsert_current_source_system_config,
    )
    from swe.app.source_system_config.models import (
        CurrentSourceSystemConfigUpdateRequest,
        SourceSystemConfig,
    )

    refreshed: dict = {}

    class FakeService:
        async def upsert_current_source_config(
            self,
            source_id,
            config,
            *,
            updated_by,
        ):
            return SimpleNamespace(
                source_id=source_id,
                config=config,
                version=2,
                is_default=False,
            )

        async def resolve_config(self, source_id, *, force_refresh=False):
            return SimpleNamespace(
                source_id=source_id,
                config=config,
                version=2,
            )

    class FakeScheduler:
        async def refresh_task_session_cleanup(
            self,
            *,
            source_id,
            config,
            identity,
        ):
            refreshed["source_id"] = source_id
            refreshed["tenant_id"] = identity.tenant_id
            refreshed["scope_id"] = identity.scope_id
            refreshed["from_id"] = identity.from_id
            refreshed["updated_by"] = identity.updated_by

    config = SourceSystemConfig.model_validate(
        {
            "cron_task_session_cleanup": {
                "enabled": True,
                "retention_days": 30,
                "cron": "30 2 * * *",
            },
        },
    )
    request = SimpleNamespace(
        state=SimpleNamespace(
            user_id="alice",
            source_id="source-a",
            tenant_id="tenant-a",
            scope_id="tenant-a-source-a",
        ),
        app=SimpleNamespace(
            state=SimpleNamespace(
                source_system_config_service=FakeService(),
                source_system_task_scheduler=FakeScheduler(),
            ),
        ),
    )

    await upsert_current_source_system_config(
        CurrentSourceSystemConfigUpdateRequest(config=config),
        request,
    )

    assert refreshed == {
        "source_id": "source-a",
        "tenant_id": "tenant-a",
        "scope_id": "tenant-a-source-a",
        "from_id": "tenant-a",
        "updated_by": "alice",
    }
```

Use the existing fake request helper in this test file only if it already
sets `state.user_id`, `state.source_id`, `state.tenant_id`, `state.scope_id`,
and `app.state.source_system_task_scheduler`; keep the assertions exactly as
shown above.

- [ ] **Step 2: Run the failing router test**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/app/test_source_system_config.py::test_upsert_current_config_refreshes_source_cleanup_scheduler -q
```

Expected: FAIL because router still calls `_refresh_cleanup_system_job()` on tenant `CronManager`.

- [ ] **Step 3: Replace router refresh helper**

In `src/swe/app/source_system_config/router.py`, replace `_refresh_cleanup_system_job()` with source scheduler logic:

```python
def _get_scheduler_identity(request: Request, updated_by: str | None):
    from .task_scheduler import SourceSchedulerIdentity

    tenant_id = str(getattr(request.state, "tenant_id", "") or "")
    source_id = _get_request_source_id(request)
    scope_id = str(getattr(request.state, "scope_id", "") or "")
    if not scope_id and tenant_id and source_id:
        scope_id = f"{tenant_id}-{source_id}"
    return SourceSchedulerIdentity(
        tenant_id=tenant_id,
        scope_id=scope_id,
        from_id=tenant_id,
        updated_by=updated_by,
    )


async def _refresh_cleanup_source_task(
    request: Request,
    *,
    source_id: str,
    updated_by: str | None,
) -> None:
    """配置变更后刷新当前 source 的清理系统任务。"""
    scheduler = getattr(
        request.app.state,
        "source_system_task_scheduler",
        None,
    )
    if scheduler is None:
        logger.warning("Source system task scheduler is not initialized")
        return

    service = _get_service(request)
    config = await service.resolve_config(source_id, force_refresh=True)
    await scheduler.refresh_task_session_cleanup(
        source_id=source_id,
        config=config,
        identity=_get_scheduler_identity(request, updated_by),
    )
```

Update the PUT route:

```python
await _refresh_cleanup_source_task(
    request,
    source_id=source_id,
    updated_by=updated_by,
)
```

Update the DELETE route:

```python
await _refresh_cleanup_source_task(
    request,
    source_id=source_id,
    updated_by=_require_manager(request),
)
```

Ensure DELETE stores the manager id once so `_require_manager(request)` is not called twice with surprising side effects.

- [ ] **Step 4: Wire scheduler in app startup**

In `src/swe/app/_app.py`, extend the source config module initialization:

```python
from .crons.scheduler_adapter import _build_scheduler_adapter
from .source_system_config.task_binding_store import (
    SourceSystemTaskBindingStore,
)
from .source_system_config.task_scheduler import SourceSystemTaskScheduler

source_config_service = SourceSystemConfigService(
    SourceSystemConfigStore(db_connection),
)
app.state.source_system_config_service = source_config_service
app.state.source_system_task_scheduler = SourceSystemTaskScheduler(
    binding_store=SourceSystemTaskBindingStore(db_connection),
    scheduler_adapter=_build_scheduler_adapter(),
    callback_url=_build_internal_cron_callback_url(),
)
```

Add this helper in `src/swe/app/_app.py` near the app initialization helpers:

```python
def _build_internal_cron_callback_url() -> str:
    base = (
        os.environ.get("SWE_SERVER_DOMAIN", "").strip()
        or "http://localhost:8000"
    )
    return f"{base}/api/internal/cron/callback"
```

- [ ] **Step 5: Verify router tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/app/test_source_system_config.py::test_upsert_current_config_refreshes_source_cleanup_scheduler -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```powershell
git add src/swe/app/_app.py src/swe/app/source_system_config/router.py tests/unit/app/test_source_system_config.py
git commit -m "feat(source-config): refresh source cleanup task on config changes"
```

---

### Task 5: Remove Tenant-Level Cleanup Registration

**Files:**
- Modify: `src/swe/app/crons/manager.py`
- Modify: `tests/unit/app/test_external_cron_scope_refresh.py`

- [ ] **Step 1: Add regression test that tenant CronManager no longer registers cleanup**

In `tests/unit/app/test_external_cron_scope_refresh.py`, replace old cleanup registration expectations with:

```python
@pytest.mark.asyncio
async def test_cron_manager_system_jobs_do_not_register_cleanup(
    tmp_path,
) -> None:
    """tenant CronManager 初始化时不再注册 source 级清理任务。"""
    adapter = CapturingSchedulerAdapter()

    class FakeRepo:
        _path = tmp_path / "jobs.json"

        async def list_jobs(self):
            return []

    manager = CronManager(
        repo=FakeRepo(),
        runner=SimpleNamespace(workspace_dir=None, _workspace=None),
        channel_manager=object(),
        agent_id="default",
        tenant_id=encode_scope_id("tenant-a", "source-a"),
        scheduler_adapter=adapter,
        source_system_config_service=_StaticSourceSystemConfigService(
            {
                "cron_task_session_cleanup": {
                    "enabled": True,
                    "retention_days": 30,
                    "cron": "30 2 * * *",
                },
            },
        ),
    )

    await manager._register_system_jobs()

    paths = [path for path, _ in adapter.requests]
    assert "/job-admin/v2/add-job" not in paths
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/app/test_external_cron_scope_refresh.py::test_cron_manager_system_jobs_do_not_register_cleanup -q
```

Expected: FAIL because `_register_system_jobs()` still calls `register_task_session_cleanup()`.

- [ ] **Step 3: Stop tenant CronManager from registering cleanup**

In `src/swe/app/crons/manager.py`, update `_register_system_jobs()`:

```python
async def _register_system_jobs(self) -> None:
    """注册 tenant 级 heartbeat 和 dream 到外部调度平台。"""
    await self.register_heartbeat()
    await self.register_dream()
```

Remove or leave unused-only methods only after checking references:

```powershell
rg -n "register_task_session_cleanup|_get_task_session_cleanup_external_id|_save_task_session_cleanup_external_id" src tests
```

If only tests and old router references remain, delete:

```python
register_task_session_cleanup
_get_task_session_cleanup_external_id
_save_task_session_cleanup_external_id
```

Keep `_resolve_task_session_cleanup_config()` and `run_task_session_cleanup()` because callback execution still uses retention-day config.

- [ ] **Step 4: Verify CronManager cleanup registration tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/app/test_external_cron_scope_refresh.py::test_cron_manager_system_jobs_do_not_register_cleanup -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

```powershell
git add src/swe/app/crons/manager.py tests/unit/app/test_external_cron_scope_refresh.py
git commit -m "refactor(cron): remove tenant cleanup registration"
```

---

### Task 6: Route Cleanup Callback Through Source Scope

**Files:**
- Modify: `src/swe/app/routers/internal.py`
- Test: `tests/unit/app/test_external_cron_scope_refresh.py`

- [ ] **Step 1: Add callback test for source-only cleanup**

In `tests/unit/app/test_external_cron_scope_refresh.py`, add:

```python
@pytest.mark.asyncio
async def test_callback_runs_source_cleanup_without_using_tenant_scope(
    monkeypatch,
) -> None:
    """清理回调只按 source_id 定位清理范围。"""
    observed: dict = {}

    class FakeSourceScheduler:
        async def run_task_session_cleanup(self, *, source_id):
            observed["source_id"] = source_id
            return {"enabled": True, "source_id": source_id}

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                source_system_task_scheduler=FakeSourceScheduler(),
                multi_agent_manager=object(),
            ),
        ),
    )
    body = {
        "tenant_id": "tenant-a",
        "source_id": "source-a",
        "agent_id": "",
        "task_type": "cleanup",
        "job_id": "_source_task_session_cleanup",
        "scopeId": "tenant-a-source-a",
        "fromId": "tenant-a",
    }

    monkeypatch.setattr(
        internal_router,
        "_verify_internal_token",
        lambda _token: None,
    )

    response = await internal_router.internal_cron_callback(
        request,
        x_internal_token="token",
        body=body,
    )

    assert response == {"status": "ok", "task_type": "cleanup"}
    assert observed == {"source_id": "source-a"}
```

- [ ] **Step 2: Run the failing callback test**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/app/test_external_cron_scope_refresh.py::test_callback_runs_source_cleanup_without_using_tenant_scope -q
```

Expected: FAIL because callback currently calls
`_run_source_task_session_cleanup()` with `tenant_id`, `source_id`, and
`agent_id` instead of dispatching to `app.state.source_system_task_scheduler`.

- [ ] **Step 3: Update callback cleanup branch**

In `src/swe/app/routers/internal.py`, change `task_type == "cleanup"` branch:

```python
if task_type == "cleanup":
    if not source_id:
        raise HTTPException(
            status_code=400,
            detail="source_id required for task_type=cleanup",
        )
    source_scheduler = getattr(
        request.app.state,
        "source_system_task_scheduler",
        None,
    )
    if source_scheduler is None:
        raise HTTPException(
            status_code=503,
            detail="Source system task scheduler not available",
        )
    cleanup_result = await source_scheduler.run_task_session_cleanup(
        source_id=source_id,
    )
    logger.info("Source task session cleanup result: %s", cleanup_result)
```

- [ ] **Step 4: Verify callback routing**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/app/test_external_cron_scope_refresh.py::test_callback_runs_source_cleanup_without_using_tenant_scope -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

```powershell
git add src/swe/app/routers/internal.py tests/unit/app/test_external_cron_scope_refresh.py
git commit -m "refactor(cron): route cleanup callback by source"
```

---

### Task 7: Implement Source-Wide Cleanup Execution

**Files:**
- Modify: `src/swe/app/source_system_config/task_scheduler.py`
- Modify: `src/swe/app/_app.py`
- Test: `tests/unit/app/test_source_system_task_scheduler.py`

- [ ] **Step 1: Add source-wide cleanup execution test**

Append this test to `tests/unit/app/test_source_system_task_scheduler.py`:

```python
@pytest.mark.asyncio
async def test_source_cleanup_runs_all_scope_managers_for_source() -> None:
    """source 清理会覆盖该 source 下所有 runtime scope。"""
    cleaned: list[str] = []

    class FakeTenantScopeStore:
        async def list_runtime_tenant_ids_for_source(self, source_id):
            assert source_id == "source-a"
            return ["tenant-a-source-a", "tenant-b-source-a"]

    class FakeCronManager:
        def __init__(self, name):
            self.name = name

        async def run_task_session_cleanup(self):
            cleaned.append(self.name)
            return {
                "enabled": True,
                "sessions_seen": 1,
                "sessions_cleaned": 1,
                "runs_removed": 2,
                "messages_removed": 3,
            }

    class FakeManager:
        async def get_agent(self, tenant_id, agent_id):
            return SimpleNamespace(
                cron_manager=FakeCronManager(f"{tenant_id}:{agent_id}"),
            )

    scheduler = SourceSystemTaskScheduler(
        binding_store=SourceSystemTaskBindingStore(_FakeDb()),
        scheduler_adapter=_CapturingAdapter(),
        callback_url="http://swe.local/api/internal/cron/callback",
        tenant_scope_store=FakeTenantScopeStore(),
        multi_agent_manager=FakeManager(),
        agent_id="default",
    )

    result = await scheduler.run_task_session_cleanup(source_id="source-a")

    assert cleaned == [
        "tenant-a-source-a:default",
        "tenant-b-source-a:default",
    ]
    assert result["source_id"] == "source-a"
    assert result["scopes_seen"] == 2
    assert result["scopes_failed"] == 0
    assert result["sessions_seen"] == 2
    assert result["sessions_cleaned"] == 2
    assert result["runs_removed"] == 4
    assert result["messages_removed"] == 6
```

- [ ] **Step 2: Run source cleanup execution test**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/app/test_source_system_task_scheduler.py::test_source_cleanup_runs_all_scope_managers_for_source -q
```

Expected: FAIL because `SourceSystemTaskScheduler.__init__` does not accept `tenant_scope_store`, `multi_agent_manager`, or `agent_id`.

- [ ] **Step 3: Implement source-wide cleanup aggregation**

Update `SourceSystemTaskScheduler.__init__`:

```python
def __init__(
    self,
    *,
    binding_store: SourceSystemTaskBindingStore,
    scheduler_adapter: Any,
    callback_url: str,
    tenant_scope_store: Any | None = None,
    multi_agent_manager: Any | None = None,
    agent_id: str = "default",
) -> None:
    self._binding_store = binding_store
    self._scheduler_adapter = scheduler_adapter
    self._callback_url = callback_url
    self._tenant_scope_store = tenant_scope_store
    self._multi_agent_manager = multi_agent_manager
    self._agent_id = agent_id
```

Replace `run_task_session_cleanup`:

```python
async def run_task_session_cleanup(
    self,
    *,
    source_id: str,
) -> dict[str, Any]:
    """清理指定 source 下所有 tenant/scope 的定时任务会话历史。"""
    result: dict[str, Any] = {
        "source_id": source_id,
        "scopes_seen": 0,
        "scopes_failed": 0,
        "sessions_seen": 0,
        "sessions_cleaned": 0,
        "sessions_skipped_locked": 0,
        "runs_removed": 0,
        "messages_removed": 0,
        "errors": [],
    }
    if self._tenant_scope_store is None or self._multi_agent_manager is None:
        result["errors"].append("source cleanup dependencies unavailable")
        return result

    runtime_tenant_ids = (
        await self._tenant_scope_store.list_runtime_tenant_ids_for_source(
            source_id,
        )
    )
    result["scopes_seen"] = len(runtime_tenant_ids)
    for runtime_tenant_id in runtime_tenant_ids:
        try:
            workspace = await self._multi_agent_manager.get_agent(
                runtime_tenant_id,
                self._agent_id,
            )
            cron_manager = getattr(workspace, "cron_manager", None)
            if cron_manager is None:
                raise RuntimeError("CronManager not found")
            scope_result = await cron_manager.run_task_session_cleanup()
            for key in (
                "sessions_seen",
                "sessions_cleaned",
                "sessions_skipped_locked",
                "runs_removed",
                "messages_removed",
            ):
                result[key] += int(scope_result.get(key, 0))
        except Exception as exc:  # noqa: BLE001
            result["scopes_failed"] += 1
            result["errors"].append(
                {
                    "runtime_tenant_id": runtime_tenant_id,
                    "error": str(exc),
                },
            )
    return result
```

Use the existing `TenantInitSourceStore.get_by_source(source_id)` method. Map
each returned row's `tenant_id` and `source_id` to a runtime scope with
`encode_scope_id(row["tenant_id"], row["source_id"])`.

- [ ] **Step 4: Wire dependencies in `_app.py`**

When constructing `SourceSystemTaskScheduler`, pass:

```python
tenant_scope_store=tenant_workspace_pool.init_source_store,
multi_agent_manager=multi_agent_manager,
agent_id="default",
```

Add this read-only property to `TenantWorkspacePool`:

```python
@property
def init_source_store(self):
    """返回 tenant/source 初始化来源存储。"""
    from .tenant_init_source_store import get_tenant_init_source_store

    return get_tenant_init_source_store()
```

- [ ] **Step 5: Verify source-wide cleanup tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/app/test_source_system_task_scheduler.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 7**

```powershell
git add src/swe/app/source_system_config/task_scheduler.py src/swe/app/_app.py src/swe/app/workspace/tenant_pool.py tests/unit/app/test_source_system_task_scheduler.py
git commit -m "feat(cron): run session cleanup across source scopes"
```

---

### Task 8: Final Verification And Cleanup

**Files:**
- Review all files changed in Tasks 1-7.

- [ ] **Step 1: Run focused backend tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/app/test_source_system_task_scheduler.py tests/unit/app/test_external_cron_scope_refresh.py tests/unit/app/test_source_system_config.py tests/unit/app/test_cron_task_session_cleanup.py -q
```

Expected: PASS.

- [ ] **Step 2: Run syntax check**

Run:

```powershell
.venv\Scripts\python.exe -m py_compile src\swe\app\source_system_config\task_binding_store.py src\swe\app\source_system_config\task_scheduler.py src\swe\app\source_system_config\router.py src\swe\app\crons\scheduler_adapter.py src\swe\app\crons\manager.py src\swe\app\routers\internal.py
```

Expected: no output and exit code 0.

- [ ] **Step 3: Run GitNexus change detection**

Run GitNexus `detect_changes(scope="all", repo="CoPaw", worktree="C:\\Users\\lenovo\\Desktop\\CoPaw")`.

Expected: changed symbols are limited to source config scheduling, scheduler adapter, internal callback, and CronManager cleanup registration removal.

- [ ] **Step 4: Run whitespace check**

Run:

```powershell
git diff --check
```

Expected: no whitespace errors. CRLF warnings are acceptable in this repo.

- [ ] **Step 5: Commit final fixes if any**

If Step 1-4 required small fixes, stage the exact files changed by those fixes:

```powershell
git add src/swe/app/source_system_config/task_scheduler.py src/swe/app/source_system_config/router.py src/swe/app/crons/scheduler_adapter.py src/swe/app/crons/manager.py src/swe/app/routers/internal.py tests/unit/app/test_source_system_task_scheduler.py tests/unit/app/test_external_cron_scope_refresh.py tests/unit/app/test_source_system_config.py
git commit -m "fix(cron): stabilize source cleanup registration"
```

If no fixes were needed, do not create an empty commit.

## Self-Review

- Spec coverage: source-level uniqueness is covered by Tasks 1-2; last-updater identity and source-only job name are covered by Task 3; config-save refresh is covered by Task 4; removal of tenant registration is covered by Task 5; source-only callback and source-wide cleanup execution are covered by Tasks 6-7.
- Placeholder scan: no `TBD`, `TODO`, or open-ended "add tests" steps are present. Each task names files, concrete tests, commands, expected outcomes, and commit boundaries.
- Type consistency: `SourceSchedulerIdentity`, `SourceSystemTaskBindingStore`, `SourceSystemTaskScheduler`, `SOURCE_TASK_SESSION_CLEANUP_JOB_ID`, and `SOURCE_TASK_SESSION_CLEANUP_NAME` are introduced before later tasks refer to them.
