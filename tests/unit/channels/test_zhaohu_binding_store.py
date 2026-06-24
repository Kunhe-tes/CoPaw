# -*- coding: utf-8 -*-
"""招乎渠道绑定 Store 单元测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.swe.app.channels.zhaohu.binding_store import (
    ZhaohuChannelBindingStore,
    init_zhaohu_binding_module,
    get_zhaohu_binding_store,
)


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.fetch_one = AsyncMock(return_value=None)
    db.fetch_all = AsyncMock(return_value=[])
    return db


@pytest.fixture
def store(mock_db):
    s = ZhaohuChannelBindingStore()
    s.initialize(mock_db)
    return s


@pytest.fixture(autouse=True)
def reset_singleton():
    yield
    init_zhaohu_binding_module(None)


class TestUpsertBinding:
    async def test_insert_new_record(self, store, mock_db):
        result = await store.upsert_binding(
            "tenant1",
            "zhaohu",
            "robot1",
            "open1",
        )
        assert result is True
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert "ON DUPLICATE KEY UPDATE" in call_args[0][0]

    async def test_update_on_conflict(self, store, mock_db):
        result = await store.upsert_binding(
            "tenant1",
            "zhaohu",
            "robot_new",
            "open_new",
        )
        assert result is True
        # Same SQL with ON DUPLICATE KEY UPDATE handles both insert and update
        mock_db.execute.assert_called_once()

    async def test_open_id_optional(self, store, mock_db):
        result = await store.upsert_binding("tenant1", "zhaohu", "robot1")
        assert result is True
        # open_id should be None
        call_args = mock_db.execute.call_args
        assert call_args[0][1][3] is None  # 4th param is open_id

    async def test_returns_false_when_db_unavailable(self):
        store = ZhaohuChannelBindingStore()
        store.initialize(None)
        result = await store.upsert_binding("tenant1", "zhaohu", "robot1")
        assert result is False

    async def test_returns_false_on_db_error(self, store, mock_db):
        mock_db.execute.side_effect = Exception("DB error")
        result = await store.upsert_binding("tenant1", "zhaohu", "robot1")
        assert result is False


class TestGetBinding:
    async def test_returns_binding_when_found(self, store, mock_db):
        expected = {
            "tenant_id": "tenant1",
            "source_id": "zhaohu",
            "robot_id": "robot1",
            "open_id": "open1",
        }
        mock_db.fetch_one.return_value = expected
        result = await store.get_binding("tenant1", "zhaohu")
        assert result == expected

    async def test_returns_none_when_not_found(self, store, mock_db):
        mock_db.fetch_one.return_value = None
        result = await store.get_binding("tenant1", "zhaohu")
        assert result is None

    async def test_returns_none_when_db_unavailable(self):
        store = ZhaohuChannelBindingStore()
        store.initialize(None)
        result = await store.get_binding("tenant1", "zhaohu")
        assert result is None


class TestGetRobotId:
    async def test_returns_robot_id_when_found(self, store, mock_db):
        mock_db.fetch_one.return_value = {"robot_id": "robot1"}
        result = await store.get_robot_id("tenant1", "zhaohu")
        assert result == "robot1"

    async def test_returns_none_when_not_found(self, store, mock_db):
        mock_db.fetch_one.return_value = None
        result = await store.get_robot_id("tenant1", "zhaohu")
        assert result is None


class TestGetBindingByOpenId:
    async def test_returns_binding_when_found(self, store, mock_db):
        expected = {
            "tenant_id": "tenant1",
            "source_id": "zhaohu",
            "robot_id": "robot1",
            "open_id": "open1",
        }
        mock_db.fetch_one.return_value = expected
        result = await store.get_binding_by_open_id("open1")
        assert result == expected

    async def test_returns_none_when_not_found(self, store, mock_db):
        mock_db.fetch_one.return_value = None
        result = await store.get_binding_by_open_id("open1")
        assert result is None


class TestModuleSingleton:
    def test_init_creates_store(self, mock_db):
        init_zhaohu_binding_module(mock_db)
        store = get_zhaohu_binding_store()
        assert store is not None

    def test_init_with_none_clears_store(self, mock_db):
        init_zhaohu_binding_module(mock_db)
        init_zhaohu_binding_module(None)
        store = get_zhaohu_binding_store()
        assert store is None

    def test_get_store_returns_none_before_init(self):
        store = get_zhaohu_binding_store()
        assert store is None
