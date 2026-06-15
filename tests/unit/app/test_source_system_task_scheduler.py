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
    binding = SourceSystemTaskBinding(
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

    result = await store.upsert_binding(binding)
    read_back = await store.get_binding(
        source_id="source-a",
        task_type="task_session_cleanup",
    )

    assert result == binding.replace(updated_at=updated_at)
    assert read_back == binding.replace(updated_at=updated_at)
    assert mock_db.execute.await_count == 1
    assert mock_db.fetch_one.await_count == 2


@pytest.mark.asyncio
async def test_get_binding_raises_when_db_unavailable():
    """DB 不可用时应复用统一的存储不可用异常。"""
    store = SourceSystemTaskBindingStore(db=None)

    with pytest.raises(SourceSystemConfigStoreUnavailable):
        await store.get_binding("source-a", "task_session_cleanup")
