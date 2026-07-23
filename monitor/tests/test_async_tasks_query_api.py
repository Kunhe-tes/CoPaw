# -*- coding: utf-8 -*-
"""异步任务查询接口的服务层测试。"""

from datetime import datetime
import sys
from types import ModuleType

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

openpyxl_stub = ModuleType("openpyxl")
openpyxl_stub.Workbook = object
openpyxl_styles_stub = ModuleType("openpyxl.styles")
openpyxl_styles_stub.Font = object
openpyxl_styles_stub.Alignment = object
openpyxl_styles_stub.PatternFill = object
openpyxl_utils_stub = ModuleType("openpyxl.utils")
openpyxl_utils_stub.get_column_letter = str
sys.modules.setdefault("openpyxl", openpyxl_stub)
sys.modules.setdefault("openpyxl.styles", openpyxl_styles_stub)
sys.modules.setdefault("openpyxl.utils", openpyxl_utils_stub)

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
                "target_name": "用户A",
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
    assert result.items[0].title == "分发供应商配置"
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
    assert "tenant_id LIKE" not in count_sql
    assert "%task-1%" in count_params
    assert "%task-1%" in list_params


@pytest.mark.asyncio
async def test_get_async_task_returns_items() -> None:
    """详情查询应返回主任务和目标明细。"""
    service = AsyncTaskQueryService(FakeDb())

    result = await service.get_task("task-1", source_id="src1")

    assert result is not None
    assert result.task_id == "task-1"
    assert result.title == "分发供应商配置"
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


def test_async_task_router_uses_monitor_prefix() -> None:
    """任务中心接口应挂在 /api/monitor/tasks，匹配 Console 调用路径。"""
    from monitor.app.routers.async_tasks import (  # pylint: disable=import-outside-toplevel
        get_async_task_query_service,
        router as async_tasks_router,
    )

    app = FastAPI()
    service = AsyncTaskQueryService(FakeDb())
    app.dependency_overrides[get_async_task_query_service] = lambda: service
    app.include_router(async_tasks_router, prefix="/api")

    try:
        client = TestClient(app)
        response = client.get(
            "/api/monitor/tasks?page=1&page_size=20",
            headers={"X-Source-Id": "src1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["task_id"] == "task-1"


def test_async_task_router_accepts_source_id_query() -> None:
    """列表查询应允许页面显式传 source_id 查询参数。"""
    from monitor.app.routers.async_tasks import (  # pylint: disable=import-outside-toplevel
        get_async_task_query_service,
        router as async_tasks_router,
    )

    app = FastAPI()
    service = AsyncTaskQueryService(FakeDb())
    app.dependency_overrides[get_async_task_query_service] = lambda: service
    app.include_router(async_tasks_router, prefix="/api")

    try:
        client = TestClient(app)
        response = client.get(
            "/api/monitor/tasks?page=1&page_size=20&source_id=src1",
            headers={"X-Source-Id": "src-other"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    count_sql, count_params = service.db.fetch_one_calls[0]
    assert "source_id = %s" in count_sql
    assert count_params[0] == "src1"
