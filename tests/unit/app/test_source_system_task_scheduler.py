# -*- coding: utf-8 -*-
"""Source 级系统任务绑定存储测试。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from swe.app.source_system_config.store import (
    SourceSystemConfigStoreUnavailable,
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
