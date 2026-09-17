# -*- coding: utf-8 -*-
"""Tests for skill ranking query and skill mapping SQL."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from monitor.app.services.tracing.query_service import (
    SKILL_DISPLAY_MAPPING_SQL_TEMPLATE,
    TracingQueryService,
)


class FakeDB:
    """可被多次调用的简单 db 替身."""

    def __init__(self, fetch_sequences: list):
        self._sequences = list(fetch_sequences)
        self._calls: list[tuple] = []
        self.is_connected = True

    async def fetch_all(self, sql: str, params=None):
        self._calls.append((sql, params))
        if not self._sequences:
            return []
        return self._sequences.pop(0)

    async def fetch_one(self, sql: str, params=None):
        self._calls.append((sql, params))
        if not self._sequences:
            return None
        item = self._sequences.pop(0)
        if isinstance(item, list):
            return item[0] if item else None
        return item

    async def execute(self, sql: str, params=None):
        self._calls.append((sql, params))
        return 0

    async def execute_many(self, sql: str, seq=None):
        self._calls.append((sql, seq))
        return len(seq or [])


class TestGetSkillDisplayMapping:
    """_get_skill_display_mapping 单元测试：透传 cn_name 与 description."""

    @pytest.mark.asyncio
    async def test_dedupes_by_skill_id_with_priority(self):
        """多个 swe_skills 记录只返回按优先级选出的稳定一条."""
        db = FakeDB(
            fetch_sequences=[
                [
                    {
                        "skill_id": "skill-x",
                        "skill_name": "x",
                        "cn_name": "X技能",
                        "description": "X 描述",
                    },
                    {
                        "skill_id": "skill-y",
                        "skill_name": "y",
                        "cn_name": "",
                        "description": "",
                    },
                ],
            ],
        )
        service = TracingQueryService(db=db)

        mapping = await service._get_skill_display_mapping()

        assert mapping == {
            "skill-x": {
                "skill_name": "x",
                "cn_name": "X技能",
                "description": "X 描述",
            },
            "skill-y": {
                "skill_name": "y",
                "cn_name": "",
                "description": "",
            },
        }
        sql, _ = db._calls[0]
        assert "ROW_NUMBER() OVER" in sql
        assert "PARTITION BY skill_id" in sql
        assert "cn_name" in sql
        assert "enabled" in sql

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_skill_ids(self):
        """传入空 skill_ids 列表时直接返回空映射，不查询数据库."""
        db = FakeDB(fetch_sequences=[])
        service = TracingQueryService(db=db)

        mapping = await service._get_skill_display_mapping([])

        assert mapping == {}
        assert db._calls == []

    @pytest.mark.asyncio
    async def test_handles_db_error_gracefully(self):
        """数据库异常时返回空映射，不影响主流程."""

        class _BadDB(FakeDB):
            async def fetch_all(self, sql, params=None):
                raise RuntimeError("db down")

        service = TracingQueryService(db=_BadDB([]))
        mapping = await service._get_skill_display_mapping()
        assert mapping == {}


class TestSkillRankingQuery:
    """端到端验证：同一 skill_id 对应多条 swe_skills 记录不放大 count."""

    @pytest.mark.asyncio
    async def test_get_skills_paginated_does_not_inflate_count_for_multi_user(
        self,
    ):
        """每个 (skill_id, skill_name) 组合只被聚合一次."""
        db = FakeDB(
            fetch_sequences=[
                [],  # eligible skills
                [{"total": 1}],  # count
                [
                    {
                        "skill_id": "skill-search",
                        "skill_name": "search",
                        "count": 12,
                        "avg_duration": 500,
                    },
                ],  # data
                [
                    {
                        "skill_id": "skill-search",
                        "skill_name": "search",
                        "cn_name": "智能搜索",
                    },
                ],  # mapping
            ],
        )
        service = TracingQueryService(db=db)

        items, total = await service.get_skills_paginated(
            source_id="default",
            page=1,
            page_size=10,
        )

        assert total == 1
        assert len(items) == 1
        assert items[0].skill_id == "skill-search"
        assert items[0].skill_name == "search"
        # 12 次调用聚合自 12 条 span，不应被 swe_skills 多用户记录放大
        assert items[0].count == 12
        # 后端只透传 cn_name，由前端决定展示回退
        assert items[0].cn_name == "智能搜索"

    @pytest.mark.asyncio
    async def test_get_skills_paginated_returns_empty_cn_name_when_mapping_empty(
        self,
    ):
        """cn_name 为空时透传 None，前端会回退 skill_name."""
        db = FakeDB(
            fetch_sequences=[
                [],
                [{"total": 1}],
                [
                    {
                        "skill_id": "skill-x",
                        "skill_name": "x",
                        "count": 3,
                        "avg_duration": 100,
                    },
                ],
                [
                    {
                        "skill_id": "skill-x",
                        "skill_name": "x",
                        "cn_name": "",
                    },
                ],
            ],
        )
        service = TracingQueryService(db=db)

        items, _ = await service.get_skills_paginated(
            source_id="default",
            page=1,
            page_size=10,
        )

        assert items[0].cn_name is None
        assert items[0].count == 3

    @pytest.mark.asyncio
    async def test_get_skills_paginated_cn_name_none_when_no_skill_id(
        self,
    ):
        """未初始化 skill_id 的 span 不参与 mapping，cn_name 为 None."""
        db = FakeDB(
            fetch_sequences=[
                [],
                [{"total": 1}],
                [
                    {
                        "skill_id": None,  # 未初始化
                        "skill_name": "legacy",
                        "count": 4,
                        "avg_duration": 200,
                    },
                ],
                [],  # 不会调用 mapping
            ],
        )
        service = TracingQueryService(db=db)

        items, _ = await service.get_skills_paginated(
            source_id="default",
            page=1,
            page_size=10,
        )

        assert items[0].skill_id is None
        assert items[0].skill_name == "legacy"
        assert items[0].cn_name is None

    @pytest.mark.asyncio
    async def test_get_skills_paginated_uses_skill_id_in_query(self):
        """聚合 SQL 使用了 skill_id 维度（避免直接 join swe_skills）."""
        db = FakeDB(
            fetch_sequences=[
                [],
                [{"total": 1}],
                [
                    {
                        "skill_id": "skill-x",
                        "skill_name": "x",
                        "count": 1,
                        "avg_duration": 100,
                    },
                ],
                [
                    {
                        "skill_id": "skill-x",
                        "skill_name": "x",
                        "cn_name": "X",
                    },
                ],
            ],
        )
        service = TracingQueryService(db=db)

        await service.get_skills_paginated(source_id="default", page=1)

        data_query = db._calls[2][0]
        # 聚合维度包含 skill_id
        assert "MAX(NULLIF(skill_id, ''))" in data_query
        # 没有直接 LEFT JOIN swe_skills（按两步聚合）
        assert "LEFT JOIN swe_skills" not in data_query
        # 4) mapping 查询使用了去重后的 SQL
        mapping_query = db._calls[3][0]
        assert "ROW_NUMBER() OVER" in mapping_query


class TestDisplayMappingSqlTemplate:
    """SQL 模板必须按稳定优先级排序，避免依赖 GROUP BY 非确定性结果."""

    def test_template_uses_window_function_for_dedup(self):
        assert "ROW_NUMBER() OVER" in SKILL_DISPLAY_MAPPING_SQL_TEMPLATE
        assert "PARTITION BY skill_id" in SKILL_DISPLAY_MAPPING_SQL_TEMPLATE
        assert "WHERE rn = 1" in SKILL_DISPLAY_MAPPING_SQL_TEMPLATE

    def test_template_priority_order(self):
        sql = SKILL_DISPLAY_MAPPING_SQL_TEMPLATE
        # cn_name 优先级位置必须早于 enabled
        cn_pos = sql.find("cn_name")
        enabled_pos = sql.find("enabled")
        updated_pos = sql.find("updated_at")
        id_pos = sql.find("id DESC")
        assert -1 < cn_pos < enabled_pos < updated_pos < id_pos
