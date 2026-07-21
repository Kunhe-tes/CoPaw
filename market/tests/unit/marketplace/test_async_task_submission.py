# -*- coding: utf-8 -*-
"""Market 异步任务提交接口测试。"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from market.app.routers import mcp_market as mcp_router
from market.app.routers import skills_market as skills_router
from market.database.connection import DatabaseConnection
from market.marketplace.schemas import (
    MCPDistributionRequest,
    MCPDistributionResponse,
    MCPDistributionTenantResult,
    PublishMCPRequest,
)
from market.marketplace.service import MarketplaceService


def _make_app(tmp_path):
    """构造带市场服务的测试应用。"""
    mock_db = AsyncMock(spec=DatabaseConnection)
    mock_db.is_connected = True
    mock_db.execute = AsyncMock(return_value=1)
    mock_db.execute_many = AsyncMock(return_value=1)
    mock_db.fetch_one = AsyncMock(return_value=None)
    mock_db.fetch_all = AsyncMock(return_value=[])

    svc = MarketplaceService(
        db=mock_db,
        marketplace_root=tmp_path / "market",
        swe_root=tmp_path / "swe",
    )
    app = FastAPI()
    app.state.marketplace = svc
    app.state.db = mock_db
    from market.app.routers import api_router

    app.include_router(api_router, prefix="/api")
    return app


@pytest.mark.asyncio
async def test_distribute_skill_returns_task_submission(tmp_path, monkeypatch):
    """技能分发应返回受理中的任务。"""
    from market.marketplace.schemas import PublishSkillRequest

    app = _make_app(tmp_path)
    svc = app.state.marketplace
    svc._resolve_target_users = AsyncMock(  # noqa: SLF001
        return_value=[
            {
                "tenant_id": "tenant-a",
                "tenant_name": "用户A",
                "bbk_id": "100",
            },
        ],
    )
    await svc.publish_skill(
        "src1",
        PublishSkillRequest(
            name="skill-a",
            description="",
            creator_id="alice",
            creator_name="Alice",
            skill_json={},
            skill_md="",
        ),
    )

    monkeypatch.setattr(
        skills_router.asyncio,
        "create_task",
        lambda coro: coro.close() or object(),
    )

    client = TestClient(app)
    resp = client.post(
        "/api/market/skills/skill-a/distribute",
        json={"target_type": "all", "target_values": []},
        headers={
            "X-Source-Id": "src1",
            "X-Manager": "true",
            "X-User-Id": "admin",
            "X-User-Name": "admin",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    task_id = resp.json()["task_id"]
    assert task_id
    item_insert_call = next(
        call
        for call in app.state.db.execute_many.await_args_list
        if "INSERT INTO swe_async_task_items" in call.args[0]
    )
    assert item_insert_call.args[1] == [
        (task_id, "tenant-a", "用户A", "queued", None, None),
    ]


@pytest.mark.asyncio
async def test_distribute_mcp_returns_task_submission(tmp_path, monkeypatch):
    """MCP 分发应返回受理中的任务。"""
    app = _make_app(tmp_path)
    svc = app.state.marketplace
    item, _ = await svc.publish_mcp(
        "src1",
        PublishMCPRequest(
            client_key="mcp-a",
            name="demo",
            description="demo",
            creator_id="alice",
            creator_name="Alice",
            config={"name": "demo", "transport": "stdio", "command": "/a"},
            version="1.0.0",
        ),
    )

    monkeypatch.setattr(
        mcp_router.asyncio,
        "create_task",
        lambda coro: coro.close() or object(),
    )

    client = TestClient(app)
    resp = client.post(
        f"/api/market/mcp/{item.item_id}/distribute",
        json={"target_tenant_ids": ["tenant-a"], "overwrite": True},
        headers={
            "X-Source-Id": "src1",
            "X-Manager": "true",
            "X-User-Id": "admin",
            "X-User-Name": "admin",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    assert resp.json()["task_id"]


@pytest.mark.asyncio
async def test_mcp_distribution_records_failed_item_target_name() -> None:
    """MCP 失败明细也应保留可回填目标名称的结果。"""

    class FakeStore:
        """记录后台任务写入参数的任务表替身。"""

        def __init__(self) -> None:
            self.items: list[dict[str, Any]] = []

        async def mark_running(self, task_id: str) -> None:
            assert task_id == "task-1"

        async def record_item_result(self, **kwargs: Any) -> None:
            self.items.append(kwargs)

        async def finish_task(self, **kwargs: Any) -> None:
            assert kwargs["status"] == "failed"

    class FakeService:
        """返回带用户名称的 MCP 分发结果。"""

        async def distribute_mcp(
            self,
            *args: Any,
            **kwargs: Any,
        ) -> MCPDistributionResponse:
            del args, kwargs
            return MCPDistributionResponse(
                source_agent_id="mcp-a",
                results=[
                    MCPDistributionTenantResult(
                        tenant_id="tenant-a",
                        tenant_name="用户A",
                        success=False,
                        error="failed",
                    ),
                ],
            )

    store = FakeStore()

    await mcp_router._run_mcp_distribution_task(  # noqa: SLF001
        task_id="task-1",
        store=store,
        svc=FakeService(),
        source_id="src1",
        item_id="mcp-a",
        operator_id="admin",
        operator_name="admin",
        req=MCPDistributionRequest(target_tenant_ids=["tenant-a"]),
    )

    assert store.items[0]["result"]["tenant_name"] == "用户A"
    assert store.items[0]["error_message"] == "failed"
