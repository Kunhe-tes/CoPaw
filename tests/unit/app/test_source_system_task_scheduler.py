# -*- coding: utf-8 -*-
"""Source 级系统任务绑定存储测试。"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from swe.app.crons.manager import TASK_SESSION_CLEANUP_TASK_TYPE
from swe.config.context import encode_scope_id

from swe.app.source_system_config.store import (
    SourceSystemConfigStoreUnavailable,
)
from swe.app.source_system_config.task_scheduler import (
    SOURCE_ARCHIVE_MAINTENANCE_JOB_ID,
    SOURCE_ARCHIVE_MAINTENANCE_NAME,
    SOURCE_ARCHIVE_MAINTENANCE_TASK_TYPE,
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
        self.upsert_calls = 0

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
        scheduler_from_id: str | None = None,
        updated_by: str | None = None,
    ) -> SourceSystemTaskBinding:
        self.upsert_calls += 1
        binding = SourceSystemTaskBinding(
            source_id=source_id,
            task_type=task_type,
            external_job_id=external_job_id,
            cron=cron,
            enabled=enabled,
            scheduler_tenant_id=scheduler_tenant_id,
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
    from_id: str = "alice",
    updated_by: str | None = "alice",
) -> SourceSchedulerIdentity:
    return SourceSchedulerIdentity(
        tenant_id=tenant_id,
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

    assert result.action == "registered"
    assert result.binding is not None
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
            from_id="bob",
            updated_by="bob",
        ),
    )

    assert result.action == "updated"
    assert result.binding is not None
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
            from_id="charlie",
            updated_by="charlie",
        ),
    )

    assert result.action == "paused"
    assert result.binding is not None
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
    assert binding.scheduler_from_id == "charlie"
    assert binding.updated_by == "charlie"


@pytest.mark.asyncio
async def test_refresh_task_session_cleanup_skips_empty_disabled_binding():
    """禁用且没有现有绑定时，不应写入空绑定或调用外部调度。"""
    store = InMemoryBindingStore()
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
        identity=_identity(),
    )

    assert result.action == "disabled"
    assert result.binding is None
    assert adapter.calls == []
    assert store.upsert_calls == 0
    assert await store.get_binding("source-a", SOURCE_TASK_SESSION_CLEANUP_NAME) is None


@pytest.mark.asyncio
async def test_refresh_task_session_cleanup_raises_when_register_returns_empty_id():
    """外部调度没有返回 job id 时，不应写入启用绑定。"""
    store = InMemoryBindingStore()
    adapter = RecordingSchedulerAdapter(external_id="")
    scheduler = SourceSystemTaskScheduler(
        binding_store=store,
        scheduler_adapter=adapter,
        callback_url="http://swe.local/api/internal/cron/callback",
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "external scheduler did not return job id "
            "for source cleanup task: source-a"
        ),
    ):
        await scheduler.refresh_task_session_cleanup(
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
                "from_id": "alice",
            },
        ),
    ]
    assert store.upsert_calls == 0
    assert await store.get_binding("source-a", SOURCE_TASK_SESSION_CLEANUP_NAME) is None


@pytest.mark.asyncio
async def test_refresh_archive_maintenance_registers_source_level_job():
    store = InMemoryBindingStore()
    adapter = RecordingSchedulerAdapter(external_id="ext-archive-1")
    scheduler = SourceSystemTaskScheduler(
        binding_store=store,
        scheduler_adapter=adapter,
        callback_url="http://swe.local/api/internal/cron/callback",
    )

    result = await scheduler.refresh_archive_maintenance(
        source_id="source-a",
        config={
            "archive_maintenance": {
                "enabled": True,
                "cron": "30 3 * * *",
            },
        },
        identity=_identity(),
    )

    assert result.action == "registered"
    assert result.binding is not None
    assert adapter.calls == [
        (
            "register_job",
            {
                "tenant_id": "tenant-a",
                "source_id": "source-a",
                "agent_id": "",
                "task_type": SOURCE_ARCHIVE_MAINTENANCE_TASK_TYPE,
                "job_id": SOURCE_ARCHIVE_MAINTENANCE_JOB_ID,
                "job_name": SOURCE_ARCHIVE_MAINTENANCE_NAME,
                "cron": "30 3 * * *",
                "callback_url": "http://swe.local/api/internal/cron/callback",
                "source_level": True,
                "from_id": "alice",
            },
        ),
    ]
    binding = await store.get_binding(
        "source-a",
        SOURCE_ARCHIVE_MAINTENANCE_NAME,
    )
    assert binding is not None
    assert binding.external_job_id == "ext-archive-1"
    assert binding.enabled is True
    assert binding.cron == "30 3 * * *"


@pytest.mark.asyncio
async def test_refresh_archive_maintenance_pauses_existing_job_when_disabled():
    store = InMemoryBindingStore()
    await store.upsert_binding(
        source_id="source-a",
        task_type=SOURCE_ARCHIVE_MAINTENANCE_NAME,
        external_job_id="ext-archive-1",
        cron="0 3 * * *",
        enabled=True,
        scheduler_tenant_id="tenant-a",
        scheduler_from_id="alice",
        updated_by="alice",
    )
    adapter = RecordingSchedulerAdapter()
    scheduler = SourceSystemTaskScheduler(
        binding_store=store,
        scheduler_adapter=adapter,
        callback_url="http://swe.local/api/internal/cron/callback",
    )

    result = await scheduler.refresh_archive_maintenance(
        source_id="source-a",
        config={
            "archive_maintenance": {
                "enabled": False,
                "cron": "0 3 * * *",
            },
        },
        identity=_identity(updated_by="bob"),
    )

    assert result.action == "paused"
    assert adapter.calls == [("pause_job", {"external_id": "ext-archive-1"})]
    binding = await store.get_binding(
        "source-a",
        SOURCE_ARCHIVE_MAINTENANCE_NAME,
    )
    assert binding is not None
    assert binding.enabled is False
    assert binding.updated_by == "bob"


@pytest.mark.asyncio
async def test_source_cleanup_runs_all_scope_managers_for_source() -> None:
    """source 清理会覆盖该 source 下所有 runtime scope。"""
    cleaned: list[str] = []

    class FakeTenantScopeStore:
        async def get_by_source(
            self,
            source_id: str,
            *,
            include_templates: bool = False,
        ) -> list[dict[str, str]]:
            assert source_id == "source-a"
            assert include_templates is False
            return [
                {"tenant_id": "tenant-a", "source_id": "source-a"},
                {"tenant_id": "tenant-b", "source_id": "source-a"},
            ]

    class FakeCronManager:
        def __init__(self, name: str) -> None:
            self.name = name

        async def run_task_session_cleanup(self) -> dict[str, int | bool]:
            cleaned.append(self.name)
            return {
                "enabled": True,
                "sessions_seen": 1,
                "sessions_cleaned": 1,
                "sessions_skipped_locked": 0,
                "runs_removed": 2,
                "messages_removed": 3,
            }

    class FakeManager:
        async def get_agent(self, agent_id: str, tenant_id: str | None = None):
            return SimpleNamespace(
                cron_manager=FakeCronManager(f"{tenant_id}:{agent_id}"),
            )

    scheduler = SourceSystemTaskScheduler(
        binding_store=InMemoryBindingStore(),
        scheduler_adapter=RecordingSchedulerAdapter(),
        callback_url="http://swe.local/api/internal/cron/callback",
        tenant_scope_store_factory=lambda: FakeTenantScopeStore(),
        multi_agent_manager=FakeManager(),
        agent_id="default",
    )

    result = await scheduler.run_task_session_cleanup(source_id="source-a")

    assert cleaned == [
        f"{encode_scope_id('tenant-a', 'source-a')}:default",
        f"{encode_scope_id('tenant-b', 'source-a')}:default",
    ]
    assert result["source_id"] == "source-a"
    assert result["scopes_seen"] == 2
    assert result["scopes_failed"] == 0
    assert result["sessions_seen"] == 2
    assert result["sessions_cleaned"] == 2
    assert result["runs_removed"] == 4
    assert result["messages_removed"] == 6


@pytest.mark.asyncio
async def test_source_archive_maintenance_scans_source_workspaces_without_agent_runtime(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_calls: list[dict[str, object]] = []

    class FakeTenantScopeStore:
        async def get_by_source(
            self,
            source_id: str,
            *,
            include_templates: bool = False,
        ) -> list[dict[str, str]]:
            assert source_id == "source-a"
            assert include_templates is False
            return [
                {"tenant_id": "tenant-a", "source_id": "source-a"},
                {"tenant_id": "tenant-b", "source_id": "source-a"},
            ]

    class ExplodingManager:
        async def get_agent(self, agent_id: str, tenant_id: str | None = None):
            raise AssertionError("archive maintenance must not load agents")

    class FakeGovernanceService:
        def __init__(self) -> None:
            self.upsert_calls: list[dict[str, object]] = []

        async def upsert_archive_items(self, **kwargs):
            self.upsert_calls.append(kwargs)

    def fake_archive_old_orphans_for_workspace(
        workspace_dir,
        *,
        old_orphan_days: int,
        max_files: int,
        remaining_files: int,
        actor: str,
    ):
        archive_calls.append(
            {
                "workspace_dir": workspace_dir,
                "old_orphan_days": old_orphan_days,
                "max_files": max_files,
                "remaining_files": remaining_files,
                "actor": actor,
            },
        )
        item = {
            "id": f"{workspace_dir.name}-archive",
            "original_path": f"{workspace_dir.name}.txt",
            "archive_path": f"governance/archive/files/{workspace_dir.name}",
            "size_bytes": 7,
            "mtime": "2026-07-01T00:00:00Z",
            "archived_at": "2026-07-02T00:00:00Z",
            "archived_by": actor,
            "archive_reason": "source_archive_maintenance_mtime_5_days",
        }
        return SimpleNamespace(
            archived_items=[item],
            archived_paths=[item["original_path"]],
            archived_size_bytes=7,
            candidates_count=1,
            skipped_files=0,
            errors=[],
        )

    monkeypatch.setattr(
        "swe.app.source_system_config.task_scheduler."
        "archive_old_orphans_for_workspace",
        fake_archive_old_orphans_for_workspace,
    )

    for tenant_id, agent_ids in {
        "tenant-a": ["default", "writer"],
        "tenant-b": ["default"],
    }.items():
        runtime_tenant_id = encode_scope_id(tenant_id, "source-a")
        for agent_id in agent_ids:
            (tmp_path / runtime_tenant_id / "workspaces" / agent_id).mkdir(
                parents=True,
            )
    (tmp_path / encode_scope_id("tenant-b", "source-a") / "workspaces" / ".bad").mkdir(
        parents=True,
    )

    governance_service = FakeGovernanceService()
    scheduler = SourceSystemTaskScheduler(
        binding_store=InMemoryBindingStore(),
        scheduler_adapter=RecordingSchedulerAdapter(),
        callback_url="http://swe.local/api/internal/cron/callback",
        tenant_scope_store_factory=lambda: FakeTenantScopeStore(),
        tenant_dir_resolver=lambda runtime_tenant_id: tmp_path
        / runtime_tenant_id,
        continuous_governance_service_factory=lambda: governance_service,
        multi_agent_manager=ExplodingManager(),
    )

    result = await scheduler.run_archive_maintenance(
        source_id="source-a",
        config={
            "archive_maintenance": {
                "enabled": True,
                "cron": "0 3 * * *",
                "old_orphan_days": 5,
                "max_workspaces_per_run": 10,
                "max_files_per_workspace": 3,
                "max_files_per_run": 10,
                "timeout_seconds": 120,
            },
        },
    )

    assert [call["workspace_dir"].name for call in archive_calls] == [
        "default",
        "writer",
        "default",
    ]
    assert {call["old_orphan_days"] for call in archive_calls} == {5}
    assert {call["max_files"] for call in archive_calls} == {3}
    assert [call["remaining_files"] for call in archive_calls] == [10, 9, 8]
    assert {call["actor"] for call in archive_calls} == {
        "source_archive_maintenance",
    }
    assert result["source_id"] == "source-a"
    assert result["tenants_seen"] == 2
    assert result["workspaces_seen"] == 3
    assert result["workspaces_processed"] == 3
    assert result["workspaces_failed"] == 0
    assert result["files_archived"] == 3
    assert result["archived_size_bytes"] == 21
    assert [
        (
            call["target_user_id"],
            call["target_agent_id"],
            call["items"][0]["original_path"],
        )
        for call in governance_service.upsert_calls
    ] == [
        ("tenant-a", "default", "default.txt"),
        ("tenant-a", "writer", "writer.txt"),
        ("tenant-b", "default", "default.txt"),
    ]
