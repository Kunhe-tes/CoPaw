# -*- coding: utf-8 -*-
"""Source 级系统任务绑定存储测试。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from swe.app.crons.manager import TASK_SESSION_CLEANUP_TASK_TYPE

from swe.app.source_system_config.store import (
    SourceSystemConfigStoreUnavailable,
)
from swe.app.source_system_config.task_scheduler import (
    SOURCE_TASK_SESSION_CLEANUP_JOB_ID,
    SOURCE_TASK_SESSION_CLEANUP_NAME,
    SourceSchedulerIdentity,
    SourceSystemTaskScheduler,
)
from swe.app.source_system_config.task_binding_store import (
    SourceSystemTaskBinding,
    SourceSystemTaskBindingStore,
)


@pytest.fixture
def mock_db():
    """创建可读写的 mock 数据库连接。"""
    db = MagicMock()
    db.is_connected = True
    db.fetch_one = AsyncMock()
    db.execute = AsyncMock(return_value=1)
    return db


@pytest.fixture
def store(mock_db):
    """创建绑定存储。"""
    return SourceSystemTaskBindingStore(db=mock_db)


@pytest.mark.asyncio
async def test_upsert_binding_can_be_read_back(store, mock_db):
    """写入绑定后应可读回完整的 source 级任务绑定。"""
    updated_at = datetime(2026, 6, 15, 10, 30, 0)
    mock_db.fetch_one.return_value = {
        "source_id": "source-a",
        "task_type": "task_session_cleanup",
        "external_job_id": "job-123",
        "cron": "0 1 * * *",
        "enabled": 1,
        "scheduler_tenant_id": "tenant-a",
        "scheduler_scope_id": "scope-a",
        "scheduler_from_id": "system",
        "updated_by": "alice",
        "updated_at": updated_at,
    }

    result = await store.upsert_binding(
        source_id="source-a",
        task_type="task_session_cleanup",
        external_job_id="job-123",
        cron="0 1 * * *",
        enabled=True,
        scheduler_tenant_id="tenant-a",
        scheduler_scope_id="scope-a",
        scheduler_from_id="system",
        updated_by="alice",
    )
    read_back = await store.get_binding(
        source_id="source-a",
        task_type="task_session_cleanup",
    )

    expected = SourceSystemTaskBinding(
        source_id="source-a",
        task_type="task_session_cleanup",
        external_job_id="job-123",
        cron="0 1 * * *",
        enabled=True,
        scheduler_tenant_id="tenant-a",
        scheduler_scope_id="scope-a",
        scheduler_from_id="system",
        updated_by="alice",
        updated_at=updated_at,
    )

    assert result == expected
    assert read_back == expected
    assert mock_db.execute.await_count == 1
    assert mock_db.fetch_one.await_count == 2
    assert mock_db.execute.await_args.args[1] == (
        "source-a",
        "task_session_cleanup",
        "job-123",
        "0 1 * * *",
        1,
        "tenant-a",
        "scope-a",
        "system",
        "alice",
    )
    assert mock_db.fetch_one.await_args_list[0].args[1] == (
        "source-a",
        "task_session_cleanup",
    )
    assert mock_db.fetch_one.await_args_list[1].args[1] == (
        "source-a",
        "task_session_cleanup",
    )


@pytest.mark.asyncio
async def test_upsert_binding_raises_when_db_unavailable():
    """DB 不可用时写入绑定应抛出统一的存储不可用异常。"""
    store = SourceSystemTaskBindingStore(db=None)

    with pytest.raises(SourceSystemConfigStoreUnavailable):
        await store.upsert_binding(
            source_id="source-a",
            task_type="task_session_cleanup",
            external_job_id="job-123",
            cron="0 1 * * *",
            enabled=True,
            scheduler_tenant_id="tenant-a",
            scheduler_scope_id="scope-a",
            scheduler_from_id="system",
            updated_by="alice",
        )


@pytest.mark.asyncio
async def test_get_binding_raises_when_db_unavailable():
    """DB 不可用时应复用统一的存储不可用异常。"""
    store = SourceSystemTaskBindingStore(db=None)

    with pytest.raises(SourceSystemConfigStoreUnavailable):
        await store.get_binding("source-a", "task_session_cleanup")


@pytest.mark.asyncio
async def test_upsert_binding_wraps_execute_errors(store, mock_db):
    """底层 execute 异常应被包装为统一的存储不可用异常。"""
    mock_db.execute.side_effect = RuntimeError("db down")

    with pytest.raises(
        SourceSystemConfigStoreUnavailable,
        match="upsert binding failed: db down",
    ):
        await store.upsert_binding(
            source_id="source-a",
            task_type="task_session_cleanup",
            external_job_id="job-123",
            cron="0 1 * * *",
            enabled=True,
            scheduler_tenant_id="tenant-a",
            scheduler_scope_id="scope-a",
            scheduler_from_id="system",
            updated_by="alice",
        )


@pytest.mark.asyncio
async def test_get_binding_wraps_fetch_errors(store, mock_db):
    """底层 fetch_one 异常应被包装为统一的存储不可用异常。"""
    mock_db.fetch_one.side_effect = RuntimeError("db down")

    with pytest.raises(
        SourceSystemConfigStoreUnavailable,
        match="fetch binding failed: db down",
    ):
        await store.get_binding("source-a", "task_session_cleanup")


class InMemoryBindingStore:
    """用于测试 source 级系统任务调度器的内存绑定存储。"""

    def __init__(self) -> None:
        self._bindings: dict[tuple[str, str], SourceSystemTaskBinding] = {}

    async def get_binding(
        self,
        source_id: str,
        task_type: str,
    ) -> SourceSystemTaskBinding | None:
        return self._bindings.get((source_id, task_type))

    async def upsert_binding(
        self,
        *,
        source_id: str,
        task_type: str,
        external_job_id: str,
        cron: str,
        enabled: bool,
        scheduler_tenant_id: str | None = None,
        scheduler_scope_id: str | None = None,
        scheduler_from_id: str | None = None,
        updated_by: str | None = None,
    ) -> SourceSystemTaskBinding:
        binding = SourceSystemTaskBinding(
            source_id=source_id,
            task_type=task_type,
            external_job_id=external_job_id,
            cron=cron,
            enabled=enabled,
            scheduler_tenant_id=scheduler_tenant_id,
            scheduler_scope_id=scheduler_scope_id,
            scheduler_from_id=scheduler_from_id,
            updated_by=updated_by,
        )
        self._bindings[(source_id, task_type)] = binding
        return binding


class RecordingSchedulerAdapter:
    """记录外部调度调用，避免依赖真实平台。"""

    def __init__(self, external_id: str = "ext-1") -> None:
        self.external_id = external_id
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def register_job(self, **kwargs):
        self.calls.append(("register_job", dict(kwargs)))
        return self.external_id

    async def update_job(self, **kwargs):
        self.calls.append(("update_job", dict(kwargs)))

    async def pause_job(self, external_id: str):
        self.calls.append(("pause_job", {"external_id": external_id}))

    async def resume_job(self, external_id: str):
        self.calls.append(("resume_job", {"external_id": external_id}))


def _identity(
    *,
    tenant_id: str = "tenant-a",
    scope_id: str = "tenant-a-source-a",
    from_id: str = "alice",
    updated_by: str | None = "alice",
) -> SourceSchedulerIdentity:
    return SourceSchedulerIdentity(
        tenant_id=tenant_id,
        scope_id=scope_id,
        from_id=from_id,
        updated_by=updated_by,
    )


@pytest.mark.asyncio
async def test_refresh_task_session_cleanup_registers_source_level_job():
    """启用且没有外部任务时，应注册 source 级 cleanup 并写回绑定。"""
    store = InMemoryBindingStore()
    adapter = RecordingSchedulerAdapter(external_id="ext-1001")
    scheduler = SourceSystemTaskScheduler(
        binding_store=store,
        scheduler_adapter=adapter,
        callback_url="http://swe.local/api/internal/cron/callback",
    )

    result = await scheduler.refresh_task_session_cleanup(
        source_id="source-a",
        config={
            "cron_task_session_cleanup": {
                "enabled": True,
                "retention_days": 30,
                "cron": "30 2 * * *",
            },
        },
        identity=_identity(),
    )

    assert result["action"] == "registered"
    assert adapter.calls == [
        (
            "register_job",
            {
                "tenant_id": "tenant-a",
                "source_id": "source-a",
                "agent_id": "",
                "task_type": TASK_SESSION_CLEANUP_TASK_TYPE,
                "job_id": SOURCE_TASK_SESSION_CLEANUP_JOB_ID,
                "job_name": SOURCE_TASK_SESSION_CLEANUP_NAME,
                "cron": "30 2 * * *",
                "callback_url": "http://swe.local/api/internal/cron/callback",
                "source_level": True,
                "scope_id": "tenant-a-source-a",
                "from_id": "alice",
            },
        ),
    ]
    binding = await store.get_binding(
        "source-a",
        SOURCE_TASK_SESSION_CLEANUP_NAME,
    )
    assert binding is not None
    assert binding.external_job_id == "ext-1001"
    assert binding.enabled is True
    assert binding.cron == "30 2 * * *"
    assert binding.scheduler_tenant_id == "tenant-a"
    assert binding.scheduler_scope_id == "tenant-a-source-a"
    assert binding.scheduler_from_id == "alice"
    assert binding.updated_by == "alice"


@pytest.mark.asyncio
async def test_refresh_task_session_cleanup_updates_and_resumes_existing_job():
    """启用且已有外部任务时，应更新、恢复并刷新最后修改身份。"""
    store = InMemoryBindingStore()
    await store.upsert_binding(
        source_id="source-a",
        task_type=SOURCE_TASK_SESSION_CLEANUP_NAME,
        external_job_id="ext-1001",
        cron="30 2 * * *",
        enabled=True,
        scheduler_tenant_id="tenant-a",
        scheduler_scope_id="old-scope",
        scheduler_from_id="old-user",
        updated_by="old-user",
    )
    adapter = RecordingSchedulerAdapter()
    scheduler = SourceSystemTaskScheduler(
        binding_store=store,
        scheduler_adapter=adapter,
        callback_url="http://swe.local/api/internal/cron/callback",
    )

    result = await scheduler.refresh_task_session_cleanup(
        source_id="source-a",
        config={
            "cron_task_session_cleanup": {
                "enabled": True,
                "retention_days": 45,
                "cron": "15 4 * * *",
            },
        },
        identity=_identity(
            tenant_id="tenant-b",
            scope_id="scope-b",
            from_id="bob",
            updated_by="bob",
        ),
    )

    assert result["action"] == "updated"
    assert adapter.calls == [
        (
            "update_job",
            {
                "external_id": "ext-1001",
                "tenant_id": "tenant-b",
                "source_id": "source-a",
                "agent_id": "",
                "task_type": TASK_SESSION_CLEANUP_TASK_TYPE,
                "job_id": SOURCE_TASK_SESSION_CLEANUP_JOB_ID,
                "job_name": SOURCE_TASK_SESSION_CLEANUP_NAME,
                "cron": "15 4 * * *",
                "callback_url": "http://swe.local/api/internal/cron/callback",
                "source_level": True,
                "scope_id": "scope-b",
                "from_id": "bob",
            },
        ),
        ("resume_job", {"external_id": "ext-1001"}),
    ]
    binding = await store.get_binding(
        "source-a",
        SOURCE_TASK_SESSION_CLEANUP_NAME,
    )
    assert binding is not None
    assert binding.external_job_id == "ext-1001"
    assert binding.enabled is True
    assert binding.cron == "15 4 * * *"
    assert binding.scheduler_tenant_id == "tenant-b"
    assert binding.scheduler_scope_id == "scope-b"
    assert binding.scheduler_from_id == "bob"
    assert binding.updated_by == "bob"


@pytest.mark.asyncio
async def test_refresh_task_session_cleanup_pauses_existing_job_when_disabled():
    """禁用 cleanup 时，应暂停已有外部任务并写回停用绑定。"""
    store = InMemoryBindingStore()
    await store.upsert_binding(
        source_id="source-a",
        task_type=SOURCE_TASK_SESSION_CLEANUP_NAME,
        external_job_id="ext-1001",
        cron="30 2 * * *",
        enabled=True,
        scheduler_tenant_id="tenant-a",
        scheduler_scope_id="scope-a",
        scheduler_from_id="alice",
        updated_by="alice",
    )
    adapter = RecordingSchedulerAdapter()
    scheduler = SourceSystemTaskScheduler(
        binding_store=store,
        scheduler_adapter=adapter,
        callback_url="http://swe.local/api/internal/cron/callback",
    )

    result = await scheduler.refresh_task_session_cleanup(
        source_id="source-a",
        config={
            "cron_task_session_cleanup": {
                "enabled": False,
                "retention_days": 30,
                "cron": "0 1 * * *",
            },
        },
        identity=_identity(
            scope_id="scope-disabled",
            from_id="charlie",
            updated_by="charlie",
        ),
    )

    assert result["action"] == "paused"
    assert adapter.calls == [
        ("pause_job", {"external_id": "ext-1001"}),
    ]
    binding = await store.get_binding(
        "source-a",
        SOURCE_TASK_SESSION_CLEANUP_NAME,
    )
    assert binding is not None
    assert binding.external_job_id == "ext-1001"
    assert binding.enabled is False
    assert binding.cron == "0 1 * * *"
    assert binding.scheduler_tenant_id == "tenant-a"
    assert binding.scheduler_scope_id == "scope-disabled"
    assert binding.scheduler_from_id == "charlie"
    assert binding.updated_by == "charlie"
