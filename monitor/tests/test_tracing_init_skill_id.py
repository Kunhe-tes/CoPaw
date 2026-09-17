# -*- coding: utf-8 -*-
"""Tests for tracing skill_id initialization service and admin endpoint."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from monitor.app.routers.tracing import init_span_skill_id
from monitor.app.models.tracing import (
    InitSpanSkillIdRequest,
    InitSpanSkillIdResponse,
)
from monitor.app.services.tracing.skill_id_initializer import (
    PENDING_SPAN_SCAN_SQL_TEMPLATE,
    SKILL_CANDIDATE_SORT,
    SkillIdInitializer,
)


def _make_db(fetch_sequences: list | None = None) -> SimpleNamespace:
    """构造一个简单的可被多次调用的 db mock.

    fetch_sequences: 每次 fetch_all 调用按顺序返回的结果列表
    """
    sequences = list(fetch_sequences or [])
    return SimpleNamespace(
        is_connected=True,
        fetch_all=AsyncMock(side_effect=sequences),
        execute_many=AsyncMock(return_value=0),
    )


class TestSkillIdInitializer:
    """针对 SkillIdInitializer 服务的测试."""

    @pytest.mark.asyncio
    async def test_initialize_writes_skill_id_for_unique_match(self):
        """唯一匹配时正常写入并计入 matched。"""
        pending_span = {
            "span_id": "seed-1",
            "source_id": "default",
            "skill_name": "search",
            "start_time": datetime(2026, 1, 1, 0, 0, 0),
        }
        candidate = {
            "id": 10,
            "source_id": "default",
            "skill_name": "search",
            "skill_id": "skill-search",
            "cn_name": "搜索",
            "enabled": 1,
            "updated_at": None,
        }
        db = _make_db(
            fetch_sequences=[
                [pending_span],  # scan pending
                [candidate],  # fetch candidates
                [],  # second batch: empty
            ],
        )
        db.execute_many = AsyncMock(return_value=1)

        result = await SkillIdInitializer(db=db).initialize()

        assert result.scanned == 1
        assert result.matched == 1
        assert result.updated == 1
        assert result.unmatched == 0
        assert result.ambiguous == 0
        # 默认起始游标应为 (datetime(1000, 1, 1), "")
        scan_sql, scan_params = db.fetch_all.await_args_list[0].args
        assert "(start_time, span_id) > (%s, %s)" in scan_sql
        assert scan_params[0] == datetime(1000, 1, 1)
        assert scan_params[1] == ""
        # execute_many 只被调用一次（第二批无数据）
        assert db.execute_many.await_count == 1
        _sql, updates = db.execute_many.await_args.args
        assert updates == [("skill-search", "seed-1")]

    @pytest.mark.asyncio
    async def test_initialize_counts_unmatched(self):
        """没有候选时计入 unmatched/skipped，不写库."""
        pending_span = {
            "span_id": "seed-2",
            "source_id": "default",
            "skill_name": "missing",
            "start_time": datetime(2026, 1, 1, 0, 0, 0),
        }
        db = _make_db(
            fetch_sequences=[
                [pending_span],
                [],
                [],
            ],
        )
        result = await SkillIdInitializer(db=db).initialize()

        assert result.scanned == 1
        assert result.matched == 0
        assert result.updated == 0
        assert result.unmatched == 1
        assert result.skipped == 1
        assert result.ambiguous == 0
        assert db.execute_many.await_count == 0
        assert result.samples and result.samples[0]["kind"] == "unmatched"

    @pytest.mark.asyncio
    async def test_initialize_picks_stable_candidate_when_ambiguous(self):
        """多个候选时按优先级选一个并写入，计入 ambiguous."""
        pending_span = {
            "span_id": "seed-3",
            "source_id": "default",
            "skill_name": "report",
            "start_time": datetime(2026, 1, 1, 0, 0, 0),
        }
        # 候选需按 SQL 排序返回（cn_name 空时优先 enabled=1）
        candidates = [
            {
                "id": 21,
                "source_id": "default",
                "skill_name": "report",
                "skill_id": "skill-report-enabled",
                "cn_name": "",
                "enabled": 1,
                "updated_at": None,
            },
            {
                "id": 20,
                "source_id": "default",
                "skill_name": "report",
                "skill_id": "skill-report-disabled",
                "cn_name": "",
                "enabled": 0,
                "updated_at": None,
            },
        ]
        db = _make_db(
            fetch_sequences=[
                [pending_span],
                candidates,
                [],
            ],
        )
        db.execute_many = AsyncMock(return_value=1)

        result = await SkillIdInitializer(db=db).initialize()

        assert result.scanned == 1
        assert result.matched == 0
        assert result.updated == 1
        assert result.unmatched == 0
        assert result.ambiguous == 1
        assert result.selected_from_ambiguous == 1
        # 应该按 enabled=1 优先选择 skill-report-enabled
        _sql, updates = db.execute_many.await_args.args
        assert updates == [("skill-report-enabled", "seed-3")]
        sample = next(
            s for s in result.samples if s.get("kind") == "ambiguous"
        )
        assert sample["chosen_skill_id"] == "skill-report-enabled"
        assert len(sample["candidates"]) == 2

    @pytest.mark.asyncio
    async def test_dry_run_does_not_write(self):
        """dry_run=True 时不写库。"""
        pending_span = {
            "span_id": "seed-4",
            "source_id": "default",
            "skill_name": "x",
            "start_time": datetime(2026, 1, 1, 0, 0, 0),
        }
        candidate = {
            "id": 30,
            "source_id": "default",
            "skill_name": "x",
            "skill_id": "skill-x",
            "cn_name": "X",
            "enabled": 1,
            "updated_at": None,
        }
        db = _make_db(
            fetch_sequences=[
                [pending_span],
                [candidate],
                [],
            ],
        )
        result = await SkillIdInitializer(db=db).initialize(dry_run=True)

        assert result.scanned == 1
        assert result.matched == 1
        assert result.updated == 0  # dry_run 不更新
        assert result.dry_run is True
        assert db.execute_many.await_count == 0

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self):
        """重复执行不会再次处理已初始化的 span."""
        # 第一批返回空（已没有待初始化的 span）
        db = _make_db(fetch_sequences=[[]])
        result = await SkillIdInitializer(db=db).initialize()

        assert result.scanned == 0
        assert result.matched == 0
        assert result.updated == 0
        assert result.unmatched == 0
        assert db.execute_many.await_count == 0

    @pytest.mark.asyncio
    async def test_initialize_advances_composite_cursor_between_batches(self):
        """第一批满后游标应推进到本批最后一行 (start_time, span_id)."""
        first_batch = [
            {
                "span_id": "seed-a",
                "source_id": "default",
                "skill_name": "a",
                "start_time": datetime(2026, 1, 1, 0, 0, 0),
            },
            {
                "span_id": "seed-b",
                "source_id": "default",
                "skill_name": "b",
                "start_time": datetime(2026, 1, 1, 0, 0, 1),
            },
        ]
        # batch_size=2 触发继续循环：
        #   1) scan pending → 2 条
        #   2) fetch candidates → 空
        #   3) scan pending → 0 条
        db = _make_db(
            fetch_sequences=[
                first_batch,
                [],  # candidates
                [],  # 第二批 scan: 已无数据
            ],
        )

        result = await SkillIdInitializer(db=db).initialize(batch_size=2)
        assert result.scanned == 2
        # 第二批 scan 调用应使用第一批最后一行作为游标
        second_scan_sql, second_scan_params = db.fetch_all.await_args_list[
            2
        ].args
        assert "(start_time, span_id) > (%s, %s)" in second_scan_sql
        assert second_scan_params[0] == datetime(2026, 1, 1, 0, 0, 1)
        assert second_scan_params[1] == "seed-b"

    @pytest.mark.asyncio
    async def test_initialize_filters_by_source_id(self):
        """传入 source_id 时 SQL 应带上 source 过滤."""
        pending_span = {
            "span_id": "seed-r",
            "source_id": "RMASSIST",
            "skill_name": "x",
            "start_time": datetime(2026, 1, 1, 0, 0, 0),
        }
        db = _make_db(
            fetch_sequences=[
                [pending_span],
                [],
                [],
            ],
        )
        await SkillIdInitializer(db=db).initialize(source_id="RMASSIST")

        scan_sql, scan_params = db.fetch_all.await_args_list[0].args
        assert "source_id = %s" in scan_sql
        assert "RMASSIST" in scan_params

    def test_candidate_sort_prioritises_cn_name_then_enabled_then_recency(
        self,
    ):
        """排序 SQL 包含明确的优先级字段。"""
        assert "cn_name" in SKILL_CANDIDATE_SORT
        assert "enabled" in SKILL_CANDIDATE_SORT
        assert "updated_at DESC" in SKILL_CANDIDATE_SORT
        assert "id DESC" in SKILL_CANDIDATE_SORT

    def test_scan_sql_uses_composite_cursor(self):
        """扫描 SQL 必须使用 (start_time, span_id) 复合游标。"""
        sql = PENDING_SPAN_SCAN_SQL_TEMPLATE
        assert "(start_time, span_id) > (%s, %s)" in sql
        assert "ORDER BY start_time ASC, span_id ASC" in sql
        # 不再使用单 id 游标
        assert "id > %s" not in sql


class TestInitSpanSkillIdEndpoint:
    """针对 init_span_skill_id 路由端点的测试."""

    @pytest.mark.asyncio
    async def test_endpoint_returns_init_response(self, monkeypatch):
        """路由端点能正确返回 InitSpanSkillIdResponse。"""
        from monitor.app.services.tracing import skill_id_initializer

        fake_result = SimpleNamespace(
            to_dict=lambda: {
                "dry_run": True,
                "scanned": 5,
                "matched": 4,
                "updated": 0,
                "unmatched": 1,
                "skipped": 1,
                "ambiguous": 0,
                "selected_from_ambiguous": 0,
                "errors": [],
                "samples": [],
            },
        )

        async def fake_initialize(self, **kwargs):  # noqa: ARG001
            return fake_result

        monkeypatch.setattr(
            skill_id_initializer.SkillIdInitializer,
            "initialize",
            fake_initialize,
        )
        monkeypatch.setattr(
            "monitor.app.routers.tracing.get_db_connection",
            lambda: SimpleNamespace(is_connected=True),
        )

        body = InitSpanSkillIdRequest(
            source_id="default",
            dry_run=True,
            batch_size=100,
        )
        response = await init_span_skill_id(body)

        assert isinstance(response, InitSpanSkillIdResponse)
        assert response.dry_run is True
        assert response.scanned == 5
        assert response.matched == 4
        assert response.unmatched == 1

    @pytest.mark.asyncio
    async def test_endpoint_wraps_db_errors(self, monkeypatch):
        """数据库异常时返回 500。"""
        from fastapi import HTTPException

        from monitor.app.services.tracing import skill_id_initializer

        async def boom(self, **kwargs):  # noqa: ARG001
            raise RuntimeError("db is down")

        monkeypatch.setattr(
            skill_id_initializer.SkillIdInitializer,
            "initialize",
            boom,
        )
        monkeypatch.setattr(
            "monitor.app.routers.tracing.get_db_connection",
            lambda: SimpleNamespace(is_connected=True),
        )

        with pytest.raises(HTTPException) as exc_info:
            await init_span_skill_id(InitSpanSkillIdRequest(dry_run=True))
        assert exc_info.value.status_code == 500
