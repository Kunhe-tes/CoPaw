# -*- coding: utf-8 -*-
"""异步任务查询接口的服务层测试。"""

from datetime import datetime

import pytest

from monitor.app.services.async_task import AsyncTaskQueryService


class FakeDb:
    """记录 SQL 调用并返回预设结果的轻量数据库替身。"""

    def __init__(self) -> None:
        self.task_rows = [
            {
                "task_id": "task-1",
                "service": "swe",
                "task_type": "provider.providers.distribute",
                "status": "succeeded",
                "title": "分发供应商配置",
                "summary": "已完成",
                "source_id": "src1",
                "tenant_id": "tenant-root",
                "actor_user_id": "u1",
                "actor_user_name": "Alice",
                "target_count": 2,
                "done_count": 2,
                "failed_count": 0,
                "error_message": None,
                "result_json": '{"ok": true}',
                "created_at": datetime(2026, 7, 17, 9, 0, 0),
                "updated_at": datetime(2026, 7, 17, 9, 1, 0),
                "finished_at": datetime(2026, 7, 17, 9, 1, 0),
            },
        ]
        self.item_rows = [
            {
                "task_id": "task-1",
                "target_id": "tenant-a",
                "target_name": "租户A",
                "status": "succeeded",
                "error_message": None,
                "result_json": '{"tenant": "tenant-a"}',
                "created_at": datetime(2026, 7, 17, 9, 0, 0),
                "updated_at": datetime(2026, 7, 17, 9, 1, 0),
            },
        ]
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        """按 SQL 类型返回计数或单条任务。"""
        self.fetch_one_calls.append((sql, params))
        if "COUNT" in sql:
            return {"total": len(self.task_rows)}
        if "task_id = %s" in sql:
            task_id = params[0]
            source_id = params[1] if len(params) > 1 else None
            return next(
                (
                    row
                    for row in self.task_rows
                    if row["task_id"] == task_id
                    and (source_id is None or row["source_id"] == source_id)
                ),
                None,
            )
        return None

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """按 SQL 类型返回任务列表或明细列表。"""
        self.fetch_all_calls.append((sql, params))
        if "FROM swe_async_task_items" in sql:
            task_id = params[0]
            return [row for row in self.item_rows if row["task_id"] == task_id]
        return self.task_rows


@pytest.mark.asyncio
async def test_list_async_tasks_returns_paginated_rows() -> None:
    """列表查询应返回分页信息和任务主表字段。"""
    service = AsyncTaskQueryService(FakeDb())

    result = await service.list_tasks(
        source_id="src1",
        page=1,
        page_size=20,
    )

    assert result.total == 1
    assert result.page == 1
    assert result.page_size == 20
    assert result.items[0].task_id == "task-1"
    assert result.items[0].result_json == {"ok": True}


@pytest.mark.asyncio
async def test_list_async_tasks_applies_keyword_filter() -> None:
    """关键词查询应下推到数据库，保证分页总数与搜索条件一致。"""
    db = FakeDb()
    service = AsyncTaskQueryService(db)

    await service.list_tasks(
        source_id="src1",
        keyword="task-1",
        page=1,
        page_size=20,
    )

    count_sql, count_params = db.fetch_one_calls[0]
    list_sql, list_params = db.fetch_all_calls[0]
    assert "LIKE %s" in count_sql
    assert "LIKE %s" in list_sql
    assert "%task-1%" in count_params
    assert "%task-1%" in list_params


@pytest.mark.asyncio
async def test_get_async_task_returns_items() -> None:
    """详情查询应返回主任务和目标明细。"""
    service = AsyncTaskQueryService(FakeDb())

    result = await service.get_task("task-1", source_id="src1")

    assert result is not None
    assert result.task_id == "task-1"
    assert result.items[0].target_id == "tenant-a"
    assert result.items[0].result_json == {"tenant": "tenant-a"}


@pytest.mark.asyncio
async def test_get_async_task_returns_none_when_missing() -> None:
    """任务不存在时返回 None，路由层据此转换为 404。"""
    service = AsyncTaskQueryService(FakeDb())

    result = await service.get_task("missing-task", source_id="src1")

    assert result is None


@pytest.mark.asyncio
async def test_get_async_task_filters_by_source_id() -> None:
    """详情查询必须限制在当前来源，避免跨来源读取任务明细。"""
    service = AsyncTaskQueryService(FakeDb())

    result = await service.get_task("task-1", source_id="src-other")

    assert result is None
