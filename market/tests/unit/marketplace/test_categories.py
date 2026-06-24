# -*- coding: utf-8 -*-
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient


def _make_app(mock_db):
    from fastapi import FastAPI
    from market.app.routers.categories import router
    from market.app.deps import get_db

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: mock_db
    return app


def test_get_categories_returns_list():
    mock_db = AsyncMock()
    mock_db.is_connected = True
    mock_db.fetch_all = AsyncMock(
        return_value=[
            {
                "id": 1,
                "source_id": "src_a",
                "name": "数据分析",
                "sort_order": 0,
                "created_at": None,
            },
            {
                "id": 2,
                "source_id": "src_a",
                "name": "报表",
                "sort_order": 1,
                "created_at": None,
            },
        ],
    )
    app = _make_app(mock_db)
    client = TestClient(app)
    response = client.get(
        "/api/market/categories",
        headers={"X-Source-Id": "src_a"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "数据分析"


def test_get_categories_missing_source_id_returns_400():
    mock_db = AsyncMock()
    mock_db.is_connected = True
    app = _make_app(mock_db)
    client = TestClient(app)
    response = client.get("/api/market/categories")
    assert response.status_code == 400


def test_get_categories_db_not_connected_returns_503():
    mock_db = MagicMock()
    mock_db.is_connected = False
    app = _make_app(mock_db)
    client = TestClient(app)
    response = client.get(
        "/api/market/categories",
        headers={"X-Source-Id": "src_a"},
    )
    assert response.status_code == 503


def test_create_category_success():
    """测试成功创建分类."""
    mock_db = AsyncMock()
    mock_db.is_connected = True

    # 第一次 fetch_one: 检查同名（返回 None 表示无重复）
    # 第二次 fetch_one: 获取 max sort_order
    # 第三次 fetch_one: 插入后查询新记录
    mock_db.fetch_one = AsyncMock(
        side_effect=[
            None,  # 无同名分类
            {"max_order": 2},  # 当前最大 sort_order
            {
                "id": 3,
                "source_id": "src_a",
                "name": "新分类",
                "sort_order": 3,
                "created_at": "2025-01-01T00:00:00",
            },
        ],
    )
    mock_db.execute = AsyncMock(return_value=1)

    app = _make_app(mock_db)
    client = TestClient(app)
    response = client.post(
        "/api/market/categories",
        json={"name": "新分类"},
        headers={"X-Source-Id": "src_a"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 3
    assert data["name"] == "新分类"
    assert data["sort_order"] == 3


def test_create_category_duplicate_name_returns_409():
    """测试重复分类名返回 409."""
    mock_db = AsyncMock()
    mock_db.is_connected = True
    mock_db.fetch_one = AsyncMock(return_value={"id": 1})  # 同名已存在

    app = _make_app(mock_db)
    client = TestClient(app)
    response = client.post(
        "/api/market/categories",
        json={"name": "数据分析"},
        headers={"X-Source-Id": "src_a"},
    )
    assert response.status_code == 409
    assert "已存在" in response.json()["detail"]


def test_create_category_missing_source_id_returns_400():
    """测试缺少 source_id 返回 400."""
    mock_db = AsyncMock()
    mock_db.is_connected = True

    app = _make_app(mock_db)
    client = TestClient(app)
    response = client.post(
        "/api/market/categories",
        json={"name": "新分类"},
    )
    assert response.status_code == 400


def test_create_category_empty_name_returns_400():
    """测试空分类名返回 400."""
    mock_db = AsyncMock()
    mock_db.is_connected = True

    app = _make_app(mock_db)
    client = TestClient(app)
    response = client.post(
        "/api/market/categories",
        json={"name": "   "},
        headers={"X-Source-Id": "src_a"},
    )
    assert response.status_code == 400


def test_create_category_db_not_connected_returns_503():
    """测试数据库不可用返回 503."""
    mock_db = MagicMock()
    mock_db.is_connected = False

    app = _make_app(mock_db)
    client = TestClient(app)
    response = client.post(
        "/api/market/categories",
        json={"name": "新分类"},
        headers={"X-Source-Id": "src_a"},
    )
    assert response.status_code == 503
