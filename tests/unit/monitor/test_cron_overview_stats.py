# -*- coding: utf-8 -*-
"""定时任务概览统计测试。"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from monitor.app.services.cron.query_service import QueryService


@pytest.mark.asyncio
async def test_get_overview_stats_includes_report_metrics(monkeypatch):
    """概览统计应返回查看方案及按钮行为指标。"""
    service = QueryService()
    mock_db = MagicMock()
    monkeypatch.setattr(
        "monitor.app.services.cron.query_service.get_db_connection",
        lambda: mock_db,
    )

    service._fetch_overview_task_count = AsyncMock(return_value=20)
    service._fetch_overview_branch_tenant_counts = AsyncMock(
        return_value=(12, 86),
    )
    service._fetch_overview_execution_counts = AsyncMock(
        return_value={
            "total_executions": 2480,
            "executed_job_count": 100,
            "success_count": 2112,
            "running_count": 24,
            "error_count": 154,
        },
    )
    service._fetch_overview_read_tasks = AsyncMock(return_value=61)
    service._fetch_overview_report_behavior_counts = AsyncMock(
        return_value={
            "report_count": 35,
            "insight_count": 12,
            "phone_count": 5,
        },
    )
    service._fetch_overview_new_cron_tasks = AsyncMock(return_value=3)

    result = await service.get_overview_stats(
        start_date="2026-06-01",
        end_date="2026-06-30",
    )

    assert result.report_rate == 35.0
    assert result.report_count == 35
    assert result.insight_count == 12
    assert result.phone_count == 5


@pytest.mark.asyncio
async def test_fetch_overview_report_behavior_counts_uses_snapshot_for_plan_views():
    """查看方案任务数应来自方案预览快照，洞察与电访仍来自点击。"""
    db = MagicMock()
    db.fetch_one = AsyncMock(
        side_effect=[
            {"report_count": 8},
            {"insight_count": 3, "phone_count": 1},
        ],
    )
    service = QueryService()

    result = await service._fetch_overview_report_behavior_counts(
        db=db,
        start_time=MagicMock(),
        end_time=MagicMock(),
        bbk_filter_sql=" AND j.bbk_id IN (%s, %s)",
        bbk_filter_params=["100", "V00"],
        source_filter_sql=" AND j.source_id = %s",
        source_filter_params=["src-1"],
    )

    view_sql, view_params = db.fetch_one.await_args_list[0].args
    click_sql, click_params = db.fetch_one.await_args_list[1].args

    assert "JOIN swe_html_preview_list_snapshots s" in view_sql
    assert "s.cron_task_id COLLATE utf8mb4_unicode_ci = e.job_id" in view_sql
    assert "s.snapshot_at >= %s AND s.snapshot_at <= %s" in view_sql
    assert "AND j.bbk_id IN (%s, %s)" in view_sql
    assert "AND j.source_id = %s" in view_sql
    assert list(view_params[4:]) == ["100", "V00", "src-1"]

    assert "JOIN swe_html_preview_click_events c" in click_sql
    assert "c.button_type = 'insight'" in click_sql
    assert "c.button_type = 'phone'" in click_sql
    assert "c.clicked_at >= %s AND c.clicked_at <= %s" in click_sql
    assert list(click_params[4:]) == ["100", "V00", "src-1"]

    assert result == {
        "report_count": 8,
        "insight_count": 3,
        "phone_count": 1,
    }


@pytest.mark.asyncio
async def test_fetch_branch_plan_view_counts_uses_snapshot_rows():
    """分行查看方案任务数应来自方案预览快照。"""
    db = MagicMock()
    db.fetch_all = AsyncMock(
        return_value=[
            {
                "bbk_id": "100",
                "task_count": 6,
            },
        ],
    )
    service = QueryService()

    result = await service._fetch_branch_plan_view_counts(
        db=db,
        start_time=MagicMock(),
        end_time=MagicMock(),
        source_id="src-1",
    )

    sql, params = db.fetch_all.await_args.args

    assert "JOIN swe_html_preview_list_snapshots s" in sql
    assert (
        "s.cron_task_id COLLATE utf8mb4_unicode_ci = executed_jobs.job_id"
        in sql
    )
    assert "s.snapshot_at >= %s AND s.snapshot_at <= %s" in sql
    assert "j.deleted_at IS NULL" in sql
    assert "j.status != 'deleted'" in sql
    assert params[-1] == "src-1"
    assert result == {"100": 6}


@pytest.mark.asyncio
async def test_fetch_branch_click_counts_uses_same_execution_window():
    """分行按钮点击统计应只统计同周期执行且被点击的任务。"""
    db = MagicMock()
    db.fetch_all = AsyncMock(
        return_value=[
            {
                "bbk_id": "100",
                "button_type": "plan",
                "task_count": 6,
                "total_clicks": 9,
            },
        ],
    )
    service = QueryService()

    result = await service._fetch_branch_click_counts(
        db=db,
        start_time=MagicMock(),
        end_time=MagicMock(),
        source_id="src-1",
    )

    sql, params = db.fetch_all.await_args.args

    assert "SELECT DISTINCT e.job_id, j.bbk_id" in sql
    assert "FROM swe_cron_executions e" in sql
    assert "JOIN swe_cron_jobs j ON e.job_id = j.id" in sql
    assert "JOIN swe_html_preview_click_events c" in sql
    assert (
        "c.cron_task_id COLLATE utf8mb4_unicode_ci = executed_jobs.job_id"
        in sql
    )
    assert "e.actual_time >= %s AND e.actual_time <= %s" in sql
    assert "c.clicked_at >= %s AND c.clicked_at <= %s" in sql
    assert "j.deleted_at IS NULL" in sql
    assert "j.status != 'deleted'" in sql
    assert params[-1] == "src-1"
    assert result == {
        "100": {
            "plan": {
                "task_count": 6,
                "total_clicks": 9,
            },
        },
    }
