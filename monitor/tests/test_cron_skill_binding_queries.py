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
    assert "swe_marketplace_skills" in db.last_sql
    assert "s.include_in_statistics = 1" in db.last_sql
    assert "s.source_id = j.source_id" in db.last_sql


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
    assert "swe_marketplace_skills" in sql
    assert "s.include_in_statistics = 1" in sql
    assert "s.source_id = j.source_id" in sql
    assert (
        "COALESCE(NULLIF(s.cn_name, ''), NULLIF(s.skill_name, ''), s.skill_id)"
        in sql
    )


@pytest.mark.asyncio
async def test_manager_skill_detail_uses_marketplace_source_isolated_binding():
    """客户经理技能明细应按同应用的市场技能绑定统计。"""
    db = FakeDb()
    service = QueryService()

    await service._fetch_manager_skill_stats(
        db,
        "100",
        "manager-1",
        datetime(2026, 7, 1),
        datetime(2026, 7, 2),
        "default",
    )

    sql = db.last_sql
    assert "JOIN swe_tracing_traces" not in sql
    assert "skills_used" not in sql
    assert "JOIN swe_marketplace_skills s" in sql
    assert "FIND_IN_SET(s.skill_id, j.skill_ids)" in sql
    assert "s.include_in_statistics = 1" in sql
    assert "s.source_id = j.source_id" in sql


@pytest.mark.asyncio
async def test_manager_skill_detail_groups_by_skill_id_for_mysql_strict_mode():
    """客户经理技能明细应兼容 MySQL ONLY_FULL_GROUP_BY."""
    db = FakeDb()
    service = QueryService()

    await service._fetch_manager_skill_stats(
        db,
        "100",
        "manager-1",
        datetime(2026, 7, 1),
        datetime(2026, 7, 2),
        "default",
    )

    sql = db.last_sql
    assert "GROUP BY s.skill_id" in sql
    assert "GROUP BY skill_name" not in sql
    assert "NULLIF(MIN(s.cn_name), '')" in sql
    assert "NULLIF(MIN(s.skill_name), '')" in sql
    assert "s.skill_id" in sql
    assert "AS skill_name" in sql


@pytest.mark.asyncio
async def test_skill_ranking_uses_marketplace_statistics_flag_not_static_whitelist():
    """技能视角分行排行应使用市场表统计开关。"""
    db = FakeDb()
    service = QueryService()

    await service._fetch_branch_skill_total_tasks(
        db,
        "100",
        datetime(2026, 7, 1),
        datetime(2026, 7, 2),
        "default",
    )

    sql = db.last_sql
    params = db.calls[-1][2]
    assert "swe_marketplace_skills" in sql
    assert "include_in_statistics = 1" in sql
    assert "insurance_mkt" not in params
    assert "保险营销客户分析技能" not in params


@pytest.mark.asyncio
async def test_cron_detail_skill_view_queries_do_not_depend_on_tracing_skills_used():
    """定时任务详情技能视角统计应全部使用任务绑定技能。"""
    db = FakeDb()
    service = QueryService()
    start_time = datetime(2026, 7, 1)
    end_time = datetime(2026, 7, 2)

    await service._fetch_branch_skill_behavior_ids(
        db,
        start_time,
        end_time,
        "",
        [],
        " AND j.source_id = %s",
        ["default"],
    )
    await service._fetch_branch_skill_job_ids(
        db,
        "100",
        start_time,
        end_time,
        "default",
    )
    await service._fetch_branch_skill_count(
        db,
        "100",
        start_time,
        end_time,
        "default",
    )
    await service._fetch_branch_skill_manager_click_counts(
        db,
        "100",
        start_time,
        end_time,
        "default",
    )
    await service._fetch_branch_skill_customer_click_counts(
        db,
        "100",
        start_time,
        end_time,
        "default",
    )
    await service._fetch_branch_contact_stats(
        db,
        start_time,
        end_time,
        "",
        [],
        " AND j.source_id = %s",
        ["default"],
    )
    await service._fetch_branch_skill_recommended_customers(
        db,
        "100",
        start_time,
        end_time,
        "default",
    )
    await service._fetch_branch_skill_involved_managers(
        db,
        "100",
        start_time,
        end_time,
        "default",
    )
    await service._fetch_branch_skill_result_view_managers(
        db,
        "100",
        start_time,
        end_time,
        "default",
    )
    await service._fetch_manager_base_info(
        db,
        "100",
        start_time,
        end_time,
        "default",
    )
    await service._fetch_manager_skill_count(
        db,
        "100",
        start_time,
        end_time,
        "default",
    )
    await service._fetch_manager_recommended_customers(
        db,
        "100",
        start_time,
        end_time,
        "default",
    )
    await service._fetch_manager_click_stats(
        db,
        "100",
        start_time,
        end_time,
        "default",
    )
    await service._fetch_manager_contact_stats(
        db,
        "100",
        start_time,
        end_time,
        "default",
    )

    sql_text = "\n".join(sql for _, sql, _ in db.calls)
    assert "swe_tracing_traces" not in sql_text
    assert "skills_used" not in sql_text
    assert "swe_marketplace_skills" in sql_text
    assert "FIND_IN_SET" in sql_text
