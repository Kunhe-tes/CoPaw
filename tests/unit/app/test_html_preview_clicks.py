# -*- coding: utf-8 -*-
"""HTML 预览点击统计模块测试。"""

import importlib
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from swe.app.html_preview_clicks.models import (
    HtmlPreviewClickEventCreate,
    HtmlPreviewClickSummaryItem,
    HtmlPreviewCustomerClickItem,
    HtmlPreviewCustomerClickSummaryItem,
    HtmlPreviewListSnapshotCreate,
    HtmlPreviewListSnapshotCustomer,
    HtmlPreviewListSummaryItem,
)
from swe.app.html_preview_clicks.router import (
    router as html_preview_click_router,
)
from swe.app.html_preview_clicks.store import HtmlPreviewClickStore

html_preview_router_module = importlib.import_module(
    "swe.app.html_preview_clicks.router",
)


@pytest.fixture
def mock_db():
    """构造一个可编排返回值的数据库桩。"""
    db = MagicMock()
    db.is_connected = True
    db.execute = AsyncMock(return_value=1)
    db.fetch_all = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_create_event_writes_click_detail(mock_db):
    """点击明细应按一期字段写入数据库。"""
    store = HtmlPreviewClickStore(mock_db)
    clicked_at = datetime(2026, 5, 30, 10, 0, 0)

    await store.create_event(
        HtmlPreviewClickEventCreate(
            source_id="copaw",
            user_id="u-1",
            bbk_id="branch-1",
            cron_task_id="task-1",
            cron_task_name="存款到期提醒",
            file_url="https://example.com/a.html",
            file_name="存款到期完整客户名单.html",
            button_id="follow",
            button_name="立即跟进",
            button_text="立即跟进",
            customer_info={"客户姓名": "祝话", "到期金额": "18.00万元"},
            clicked_at=clicked_at,
        ),
    )

    query, params = mock_db.execute.call_args[0]
    assert "INSERT INTO swe_html_preview_click_events" in query
    assert "bbk_id" in query
    assert "customer_info" in query
    assert params == (
        "copaw",
        "u-1",
        "branch-1",
        "task-1",
        "存款到期提醒",
        "https://example.com/a.html",
        "存款到期完整客户名单.html",
        "https://example.com/a.html",
        "存款到期完整客户名单.html",
        "follow",
        "立即跟进",
        "立即跟进",
        "other",
        None,
        "祝话",
        '{"客户姓名": "祝话", "到期金额": "18.00万元"}',
        clicked_at,
    )


@pytest.mark.asyncio
async def test_create_event_classifies_view_plan_click(mock_db):
    """查看方案链接应归类为独立的方案点击。"""
    store = HtmlPreviewClickStore(mock_db)
    clicked_at = datetime(2026, 5, 30, 10, 30, 0)

    await store.create_event(
        HtmlPreviewClickEventCreate(
            source_id="copaw",
            user_id="u-1",
            bbk_id="branch-1",
            file_url="https://example.com/a.html",
            file_name="存款到期完整客户名单.html",
            button_id="plan",
            button_name="查看方案",
            button_text="查看方案",
            customer_id="CUST-001",
            customer_name="祝话",
            clicked_at=clicked_at,
        ),
    )

    _, params = mock_db.execute.call_args[0]
    assert params[12] == "plan"
    assert params[13] == "CUST-001"
    assert params[14] == "祝话"


@pytest.mark.asyncio
async def test_create_list_snapshot_writes_distinct_customers(mock_db):
    """名单快照应覆盖旧快照并按客户去重写入。"""
    store = HtmlPreviewClickStore(mock_db)
    snapshot_at = datetime(2026, 5, 30, 10, 0, 0)

    inserted = await store.create_list_snapshot(
        HtmlPreviewListSnapshotCreate(
            source_id="copaw",
            bbk_id="branch-1",
            cron_task_id="task-1",
            cron_task_name="存款到期提醒",
            list_key="list-1",
            list_name="存款到期名单",
            file_url="https://example.com/a.html",
            file_name="a.html",
            snapshot_at=snapshot_at,
            customers=[
                HtmlPreviewListSnapshotCustomer(
                    customer_id="CUST-001",
                    customer_name="祝话",
                    extra_info={"客户姓名": "祝话"},
                ),
                HtmlPreviewListSnapshotCustomer(
                    customer_id="CUST-001",
                    customer_name="祝话",
                ),
                HtmlPreviewListSnapshotCustomer(
                    customer_id=None,
                    customer_name="程广泛",
                ),
            ],
        ),
    )

    assert inserted == 2
    calls = mock_db.execute.call_args_list
    assert "DELETE FROM swe_html_preview_list_snapshots" in calls[0].args[0]
    assert "INSERT INTO swe_html_preview_list_snapshots" in calls[1].args[0]
    assert calls[0].args[1] == ("copaw", "branch-1", "list-1")
    assert calls[1].args[1][8:11] == (
        "CUST-001",
        "祝话",
        '{"客户姓名": "祝话"}',
    )


@pytest.mark.asyncio
async def test_list_summary_filters_by_source_and_time(mock_db):
    """聚合查询应带上来源、时间范围并按点击次数排序。"""
    clicked_at = datetime(2026, 5, 30, 11, 0, 0)
    mock_db.fetch_all.return_value = [
        {
            "button_label": "立即跟进",
            "button_id": "follow",
            "button_name": "立即跟进",
            "button_text": "立即跟进",
            "bbk_id": "branch-1",
            "cron_task_id": "task-1",
            "cron_task_name": "存款到期提醒",
            "list_key": "https://example.com/a.html",
            "list_name": "a.html",
            "file_url": "https://example.com/a.html",
            "file_name": "a.html",
            "click_count": 3,
            "last_clicked_at": clicked_at,
        },
    ]
    store = HtmlPreviewClickStore(mock_db)

    items = await store.list_summary(
        source_id="copaw",
        start_time=datetime(2026, 5, 30, 0, 0, 0),
        end_time=datetime(2026, 5, 30, 23, 59, 59),
        bbk_ids=["branch-1", "branch-2"],
        limit=50,
    )

    query, params = mock_db.fetch_all.call_args[0]
    assert "source_id <=> %s" in query
    assert "clicked_at >= %s" in query
    assert "clicked_at <= %s" in query
    assert "bbk_id IN (%s, %s)" in query
    assert "ORDER BY click_count DESC, last_clicked_at DESC" in query
    assert params[0] == "copaw"
    assert "branch-1" in params
    assert "branch-2" in params
    assert len(items) == 1
    assert items[0].click_count == 3
    assert items[0].last_clicked_at == clicked_at


@pytest.mark.asyncio
async def test_list_events_returns_customer_info(mock_db):
    """点击明细应返回按钮和客户信息。"""
    clicked_at = datetime(2026, 5, 30, 11, 0, 0)
    mock_db.fetch_all.return_value = [
        {
            "id": 7,
            "source_id": "copaw",
            "user_id": "u-1",
            "bbk_id": "branch-1",
            "cron_task_id": "task-1",
            "cron_task_name": "存款到期提醒",
            "file_url": "https://example.com/a.html",
            "file_name": "a.html",
            "list_key": "https://example.com/a.html",
            "list_name": "a.html",
            "button_id": "insight",
            "button_name": "洞察页面",
            "button_text": "洞察页面",
            "button_type": "insight",
            "customer_id": "CUST-001",
            "customer_name": "祝话",
            "customer_info": '{"客户姓名": "祝话"}',
            "clicked_at": clicked_at,
        },
    ]
    store = HtmlPreviewClickStore(mock_db)

    items = await store.list_events(
        source_id="copaw",
        start_time=datetime(2026, 5, 30, 0, 0, 0),
        end_time=datetime(2026, 5, 30, 23, 59, 59),
        limit=20,
    )

    query, params = mock_db.fetch_all.call_args[0]
    assert "customer_info" in query
    assert "ORDER BY clicked_at DESC, id DESC" in query
    assert params[0] == "copaw"
    assert items[0].button_name == "洞察页面"
    assert items[0].button_type == "insight"
    assert items[0].customer_id == "CUST-001"
    assert items[0].customer_name == "祝话"
    assert items[0].customer_info == {"客户姓名": "祝话"}


@pytest.mark.asyncio
async def test_list_customer_summary_groups_touchpoint_counts(mock_db):
    """客户维度聚合应分别返回洞察、电访和方案次数。"""
    clicked_at = datetime(2026, 5, 30, 11, 0, 0)
    mock_db.fetch_all.return_value = [
        {
            "list_key": "https://example.com/a.html",
            "list_name": "a.html",
            "button_id": "insight_page",
            "button_name": "洞察",
            "button_text": "洞察",
            "button_type": "insight",
            "customer_id": "CUST-001",
            "customer_name": "祝话",
            "customer_info": '{"customer_id": "CUST-001", "name": "祝话"}',
            "clicked_at": clicked_at,
        },
        {
            "list_key": "https://example.com/a.html",
            "list_name": "a.html",
            "button_id": "phone",
            "button_name": "电访",
            "button_text": "电话访问",
            "button_type": "phone",
            "customer_id": "CUST-001",
            "customer_name": "祝话",
            "customer_info": '{"customer_id": "CUST-001", "name": "祝话"}',
            "clicked_at": datetime(2026, 5, 30, 10, 0, 0),
        },
        {
            "list_key": "https://example.com/a.html",
            "list_name": "a.html",
            "button_id": "plan",
            "button_name": "查看方案",
            "button_text": "查看方案",
            "button_type": "plan",
            "customer_id": "CUST-001",
            "customer_name": "祝话",
            "customer_info": '{"customer_id": "CUST-001", "name": "祝话"}',
            "clicked_at": datetime(2026, 5, 30, 9, 0, 0),
        },
    ]
    store = HtmlPreviewClickStore(mock_db)

    items = await store.list_customer_summary(
        source_id="copaw",
        start_time=datetime(2026, 5, 30, 0, 0, 0),
        end_time=datetime(2026, 5, 30, 23, 59, 59),
        bbk_ids=["branch-1"],
        limit=20,
    )

    query, params = mock_db.fetch_all.call_args[0]
    assert "customer_info" in query
    assert "JSON_EXTRACT" not in query
    assert "swe_html_preview_list_snapshots" not in query
    assert "ORDER BY clicked_at DESC, id DESC" in query
    assert mock_db.fetch_all.call_count == 1
    assert params[0] == "copaw"
    assert "branch-1" in params
    assert items[0].customer_id == "CUST-001"
    assert items[0].customer_name == "祝话"
    assert items[0].insight_count == 1
    assert items[0].phone_count == 1
    assert items[0].plan_count == 1
    assert items[0].total_click_count == 3


@pytest.mark.asyncio
async def test_list_lists_combines_snapshot_and_clicks(mock_db):
    """名单统计应组合名单客户总数和点击客户数。"""
    clicked_at = datetime(2026, 5, 30, 11, 0, 0)
    mock_db.fetch_all.side_effect = [
        [
            {
                "list_key": "list-1",
                "list_name": "存款到期名单",
                "file_url": "https://example.com/a.html",
                "file_name": "a.html",
                "cron_task_id": "task-1",
                "cron_task_name": "存款到期提醒",
                "customer_id": "CUST-001",
                "customer_name": "祝话",
            },
            {
                "list_key": "list-1",
                "list_name": "存款到期名单",
                "file_url": "https://example.com/a.html",
                "file_name": "a.html",
                "cron_task_id": "task-1",
                "cron_task_name": "存款到期提醒",
                "customer_id": "CUST-002",
                "customer_name": "程广泛",
            },
        ],
        [
            {
                "list_key": "list-1",
                "list_name": "存款到期名单",
                "file_url": "https://example.com/a.html",
                "file_name": "a.html",
                "cron_task_id": "task-1",
                "cron_task_name": "存款到期提醒",
                "button_type": "insight",
                "customer_id": "CUST-001",
                "customer_name": "祝话",
                "customer_info": None,
                "clicked_at": clicked_at,
            },
            {
                "list_key": "list-1",
                "list_name": "存款到期名单",
                "file_url": "https://example.com/a.html",
                "file_name": "a.html",
                "cron_task_id": "task-1",
                "cron_task_name": "存款到期提醒",
                "button_type": "phone",
                "customer_id": "CUST-001",
                "customer_name": "祝话",
                "customer_info": None,
                "clicked_at": clicked_at,
            },
            {
                "list_key": "list-1",
                "list_name": "存款到期名单",
                "file_url": "https://example.com/a.html",
                "file_name": "a.html",
                "cron_task_id": "task-1",
                "cron_task_name": "存款到期提醒",
                "button_type": "plan",
                "customer_id": "CUST-001",
                "customer_name": "祝话",
                "customer_info": None,
                "clicked_at": clicked_at,
            },
        ],
    ]
    store = HtmlPreviewClickStore(mock_db)

    items = await store.list_lists(
        source_id="copaw",
        start_time=datetime(2026, 5, 30, 0, 0, 0),
        end_time=datetime(2026, 5, 30, 23, 59, 59),
        bbk_ids=["branch-1"],
        limit=20,
    )

    assert items[0].list_key == "list-1"
    assert items[0].customer_count == 2
    assert items[0].clicked_customer_count == 1
    assert items[0].insight_count == 1
    assert items[0].phone_count == 1
    assert items[0].plan_count == 1
    assert items[0].total_click_count == 3


def test_create_route_enriches_source_and_user(monkeypatch):
    """路由应从请求上下文补齐来源和用户标识。"""

    class _FakeService:
        async def create_event(self, event):
            assert event.source_id == "copaw"
            assert event.user_id == "user-9"
            assert event.bbk_id == "branch-1"
            assert event.file_url == "https://example.com/a.html"

    app = FastAPI()

    @app.middleware("http")
    async def _inject_state(request: Request, call_next):
        request.state.source_id = "copaw"
        request.state.user_id = "user-9"
        request.state.bbk = "branch-1"
        return await call_next(request)

    app.include_router(html_preview_click_router)
    monkeypatch.setattr(html_preview_router_module, "_service", _FakeService())

    client = TestClient(app)
    response = client.post(
        "/html-preview/events",
        json={
            "source_id": "forged-source",
            "user_id": "forged-user",
            "bbk_id": "forged-branch",
            "file_url": "https://example.com/a.html",
            "button_id": "follow",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_summary_route_returns_items(monkeypatch):
    """聚合路由应返回服务层查询结果。"""

    class _FakeService:
        async def list_summary(self, **kwargs):
            assert kwargs["source_id"] == "copaw"
            assert kwargs["bbk_ids"] == ["branch-1", "branch-2"]
            assert kwargs["limit"] == 20
            return [
                HtmlPreviewClickSummaryItem(
                    button_label="立即跟进",
                    button_id="follow",
                    click_count=2,
                ),
            ]

    app = FastAPI()

    @app.middleware("http")
    async def _inject_state(request: Request, call_next):
        request.state.source_id = "copaw"
        return await call_next(request)

    app.include_router(html_preview_click_router)
    monkeypatch.setattr(html_preview_router_module, "_service", _FakeService())

    client = TestClient(app)
    response = client.get(
        "/html-preview/events/summary",
        params={"limit": 20, "bbk_ids": "branch-1, branch-2"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["items"][0]["button_id"] == "follow"


def test_customer_summary_route_returns_customer_items(monkeypatch):
    """客户聚合路由应返回洞察和电访点击次数。"""

    class _FakeService:
        async def list_customer_summary(self, **kwargs):
            assert kwargs["source_id"] == "copaw"
            assert kwargs["bbk_ids"] == ["branch-1"]
            assert kwargs["limit"] == 20
            return [
                HtmlPreviewCustomerClickSummaryItem(
                    customer_id="CUST-001",
                    customer_name="祝话",
                    insight_count=2,
                    phone_count=1,
                    plan_count=1,
                ),
            ]

    app = FastAPI()

    @app.middleware("http")
    async def _inject_state(request: Request, call_next):
        request.state.source_id = "copaw"
        return await call_next(request)

    app.include_router(html_preview_click_router)
    monkeypatch.setattr(html_preview_router_module, "_service", _FakeService())

    client = TestClient(app)
    response = client.get(
        "/html-preview/events/customer-summary",
        params={"limit": 20, "bbk_ids": "branch-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["items"][0]["customer_id"] == "CUST-001"
    assert payload["items"][0]["insight_count"] == 2
    assert payload["items"][0]["phone_count"] == 1
    assert payload["items"][0]["plan_count"] == 1


def test_list_snapshot_route_enriches_context(monkeypatch):
    """名单快照路由应从请求上下文补齐来源和分行。"""

    class _FakeService:
        async def create_list_snapshot(self, snapshot):
            assert snapshot.source_id == "copaw"
            assert snapshot.bbk_id == "branch-1"
            assert snapshot.list_key == "list-1"
            assert snapshot.customers[0].customer_name == "祝话"
            return 1

    app = FastAPI()

    @app.middleware("http")
    async def _inject_state(request: Request, call_next):
        request.state.source_id = "copaw"
        request.state.bbk = "branch-1"
        return await call_next(request)

    app.include_router(html_preview_click_router)
    monkeypatch.setattr(html_preview_router_module, "_service", _FakeService())

    client = TestClient(app)
    response = client.post(
        "/html-preview/list-snapshot",
        json={
            "source_id": "forged-source",
            "bbk_id": "forged-branch",
            "list_key": "list-1",
            "file_url": "https://example.com/a.html",
            "customers": [{"customer_name": "祝话"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["customer_count"] == 1


def test_lists_route_returns_list_items(monkeypatch):
    """名单统计路由应返回名单维度指标。"""

    class _FakeService:
        async def list_lists(self, **kwargs):
            assert kwargs["source_id"] == "copaw"
            assert kwargs["bbk_ids"] == ["branch-1"]
            return [
                HtmlPreviewListSummaryItem(
                    list_key="list-1",
                    list_name="存款到期名单",
                    customer_count=16,
                    clicked_customer_count=3,
                    insight_count=4,
                    phone_count=2,
                    plan_count=1,
                    total_click_count=7,
                ),
            ]

    app = FastAPI()

    @app.middleware("http")
    async def _inject_state(request: Request, call_next):
        request.state.source_id = "copaw"
        return await call_next(request)

    app.include_router(html_preview_click_router)
    monkeypatch.setattr(html_preview_router_module, "_service", _FakeService())

    client = TestClient(app)
    response = client.get(
        "/html-preview/lists",
        params={"bbk_ids": "branch-1", "limit": 20},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["items"][0]["list_key"] == "list-1"
    assert payload["items"][0]["customer_count"] == 16
    assert payload["items"][0]["plan_count"] == 1


def test_customer_clicks_route_returns_customer_items(monkeypatch):
    """客户点击明细路由应支持名单和未点击开关参数。"""

    class _FakeService:
        async def list_customer_clicks(self, **kwargs):
            assert kwargs["source_id"] == "copaw"
            assert kwargs["bbk_ids"] == ["branch-1"]
            assert kwargs["list_key"] == "list-1"
            assert kwargs["include_unclicked"] is True
            return [
                HtmlPreviewCustomerClickItem(
                    customer_id="CUST-001",
                    customer_name="祝话",
                    list_key="list-1",
                    list_name="存款到期名单",
                    insight_count=2,
                    phone_count=1,
                    plan_count=1,
                    total_click_count=4,
                ),
            ]

    app = FastAPI()

    @app.middleware("http")
    async def _inject_state(request: Request, call_next):
        request.state.source_id = "copaw"
        return await call_next(request)

    app.include_router(html_preview_click_router)
    monkeypatch.setattr(html_preview_router_module, "_service", _FakeService())

    client = TestClient(app)
    response = client.get(
        "/html-preview/customer-clicks",
        params={
            "bbk_ids": "branch-1",
            "list_key": "list-1",
            "include_unclicked": "true",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["items"][0]["customer_id"] == "CUST-001"
    assert payload["items"][0]["plan_count"] == 1
    assert payload["items"][0]["total_click_count"] == 4


def test_event_list_route_returns_customer_items(monkeypatch):
    """点击明细路由应透出客户信息。"""

    class _FakeService:
        async def list_events(self, **kwargs):
            assert kwargs["source_id"] == "copaw"
            assert kwargs["limit"] == 20
            return [
                {
                    "id": 1,
                    "file_url": "https://example.com/a.html",
                    "button_name": "洞察页面",
                    "customer_info": {"客户姓名": "祝话"},
                    "clicked_at": datetime(2026, 5, 30, 11, 0, 0),
                },
            ]

    app = FastAPI()

    @app.middleware("http")
    async def _inject_state(request: Request, call_next):
        request.state.source_id = "copaw"
        return await call_next(request)

    app.include_router(html_preview_click_router)
    monkeypatch.setattr(html_preview_router_module, "_service", _FakeService())

    client = TestClient(app)
    response = client.get("/html-preview/events", params={"limit": 20})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["items"][0]["customer_info"]["客户姓名"] == "祝话"
