# -*- coding: utf-8 -*-
"""测试定时任务技能统计使用定义表绑定技能。"""

from datetime import datetime

import pytest

from monitor.app.services.cron.query_service import QueryService


class FakeDb:
    """记录查询 SQL 的最小假数据库。"""

    def __init__(self):
        self.calls = []

    async def fetch_all(self, sql, params=()):
        self.calls.append(("fetch_all", sql, params))
        return []

    async def fetch_one(self, sql, params=()):
        self.calls.append(("fetch_one", sql, params))
        return {"count": 0, "skill_count": 0}

    @property
    def last_sql(self):
        return self.calls[-1][1]


@pytest.mark.asyncio
async def test_branch_skills_raw_data_uses_bound_skill_ids():
    """分行技能排行应从任务定义的 skill_ids 展开技能。"""
    db = FakeDb()
    service = QueryService()

    await service._fetch_branch_skills_raw_data(
        db,
        "100",
        datetime(2026, 7, 1),
        datetime(2026, 7, 2),
        "default",
    )

    assert "JOIN swe_tracing_traces" not in db.last_sql
    assert "t.skills_used" not in db.last_sql
    assert "j.skill_ids" in db.last_sql
    assert "swe_skills" in db.last_sql


@pytest.mark.asyncio
async def test_branch_skill_manager_query_filters_by_bound_skill_id():
    """分行技能下钻应按绑定技能映射出的技能名称过滤。"""
    db = FakeDb()
    service = QueryService()
    import monitor.app.services.cron.query_service as query_service_module

    query_service_module.get_db_connection = lambda: db

    await service.get_branch_skill_managers(
        bbk_id="100",
        skill_name="保险营销客户分析技能",
        start_date="2026-07-01",
        end_date="2026-07-02",
        source_id="default",
    )

    sql = db.last_sql
    assert "JOIN swe_tracing_traces" not in sql
    assert "JSON_CONTAINS(t.skills_used" not in sql
    assert "FIND_IN_SET(s.skill_id, j.skill_ids)" in sql
    assert (
        "COALESCE(NULLIF(s.cn_name, ''), NULLIF(s.skill_name, ''), s.skill_id)"
        in sql
    )
