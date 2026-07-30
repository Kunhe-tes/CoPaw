# -*- coding: utf-8 -*-
"""市场技能数据库操作类单元测试."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from market.marketplace.market_skill_registry import MarketSkillRegistry


@pytest.mark.asyncio
class TestMarketSkillRegistry:
    """MarketSkillRegistry 单元测试."""

    def test_is_connected(self):
        """测试数据库连接状态检查."""
        db = MagicMock()
        db.is_connected = True
        registry = MarketSkillRegistry(db)
        assert registry.is_connected() is True

    async def test_upsert_market_skill_insert(self):
        """测试插入新记录."""
        db = MagicMock()
        db.is_connected = True
        db.fetch_one = AsyncMock(return_value=None)
        db.execute = AsyncMock()

        registry = MarketSkillRegistry(db)
        result = await registry.upsert_market_skill(
            source_id="test_source",
            item_id="test_item",
            skill_id="test_skill_id",
            skill_name="test_skill",
            cn_name="测试技能",
            include_in_statistics=True,
            creator_id="user1",
            creator_name="用户1",
        )

        assert result is True
        db.execute.assert_called_once()

    async def test_upsert_market_skill_update(self):
        """测试更新现有记录."""
        db = MagicMock()
        db.is_connected = True
        db.fetch_one = AsyncMock(return_value={"id": 1})
        db.execute = AsyncMock()

        registry = MarketSkillRegistry(db)
        result = await registry.upsert_market_skill(
            source_id="test_source",
            item_id="test_item",
            skill_id="test_skill_id",
            skill_name="test_skill",
            cn_name="测试技能",
            include_in_statistics=False,
            updator_id="user2",
            updator_name="用户2",
        )

        assert result is True
        db.execute.assert_called_once()

    async def test_update_statistics_config(self):
        """测试更新统计配置."""
        db = MagicMock()
        db.is_connected = True
        db.execute = AsyncMock()

        registry = MarketSkillRegistry(db)
        result = await registry.update_statistics_config(
            source_id="test_source",
            item_id="test_item",
            include_in_statistics=False,
            updator_id="admin",
            updator_name="管理员",
        )

        assert result is True
        db.execute.assert_called_once()

    async def test_get_statistics_eligible_skill_names(self):
        """测试获取纳入统计的技能名称."""
        db = MagicMock()
        db.is_connected = True
        db.fetch_all = AsyncMock(
            return_value=[
                {"skill_name": "skill1"},
                {"skill_name": "skill2"},
            ],
        )

        registry = MarketSkillRegistry(db)
        result = await registry.get_statistics_eligible_skill_names(
            "test_source",
        )

        assert result == {"skill1", "skill2"}

    async def test_database_not_connected(self):
        """测试数据库未连接时的处理."""
        db = MagicMock()
        db.is_connected = False

        registry = MarketSkillRegistry(db)
        result = await registry.upsert_market_skill(
            source_id="test_source",
            item_id="test_item",
            skill_id="test_skill_id",
            skill_name="test_skill",
        )

        assert result is False
