# -*- coding: utf-8 -*-
"""Market 异步任务写入器测试。"""

from __future__ import annotations

import pytest

from market.app.async_tasks import AsyncTaskStore


class FakeDb:
    """记录 SQL 调用的数据库替身。"""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self.executed_many: list[tuple[str, list[tuple]]] = []

    async def execute(self, sql: str, params: tuple | None = None) -> int:
        self.executed.append((sql, params))
        return 1

    async def execute_many(self, sql: str, params_list: list[tuple]) -> int:
        self.executed_many.append((sql, params_list))
        return len(params_list)


@pytest.mark.asyncio
async def test_start_task_inserts_master_and_items() -> None:
    """开始任务时写入主任务和批量目标明细。"""
    db = FakeDb()
    store = AsyncTaskStore(db)

    await store.start_task(
        task_id="task-1",
        service="market",
        task_type="market.skill.distribute",
        title="分发技能",
        target_ids=["u1", "u2"],
    )

    assert "INSERT INTO swe_async_tasks" in db.executed[0][0]
    assert "INSERT INTO swe_async_task_items" in db.executed_many[0][0]
    assert db.executed_many[0][1] == [
        ("task-1", "u1", None, "queued", None, None),
        ("task-1", "u2", None, "queued", None, None),
    ]


@pytest.mark.asyncio
async def test_record_item_result_updates_item() -> None:
    """单个目标完成时更新明细。"""
    db = FakeDb()
    store = AsyncTaskStore(db)

    await store.record_item_result(
        task_id="task-1",
        target_id="u1",
        success=False,
        error_message="failed",
    )

    sql, params = db.executed[0]
    assert "UPDATE swe_async_task_items" in sql
    assert params is not None
    assert params[0] == "failed"
    assert params[-2:] == ("task-1", "u1")
