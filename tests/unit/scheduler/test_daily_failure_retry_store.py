# -*- coding: utf-8 -*-
"""用真实查询验证来源、窗口、租约和调用记录，不使用假固定响应。"""

from datetime import datetime, timedelta

import pytest

from tests.fakes.daily_failure_retry import DailyRetryDatabase
from scheduler.app.services.cron.managed.daily_retry_store import (
    DailyRetryCalls,
)


@pytest.fixture
def db():
    value = DailyRetryDatabase()
    yield value
    value.conn.close()


@pytest.mark.asyncio
async def test_submit_keeps_each_call_and_beijing_day_window(db):
    now = datetime(2026, 10, 27, 1, 30)
    service = DailyRetryCalls(db, clock=lambda: now)
    first = await service.submit("bank")
    second = await service.submit("bank")
    assert first["call_id"] != second["call_id"]
    row = await service.get("bank", first["call_id"])
    assert row["business_date"] == "2026-10-27"
    assert row["window_start"].startswith("2026-10-26T16:00:00")
    assert row["cutoff_at"].startswith("2026-10-27T01:30:00")
    assert row["status"] == "queued"
    with pytest.raises(LookupError):
        await service.get("BANK", first["call_id"])


@pytest.mark.asyncio
async def test_lease_is_exclusive_and_expired_worker_is_fenced(db):
    now = [datetime(2026, 10, 27, 1)]
    service = DailyRetryCalls(db, clock=lambda: now[0])
    call = await service.submit("bank")
    assert await service.claim(call["call_id"], "worker-one")
    assert not await service.claim(call["call_id"], "worker-two")
    now[0] += timedelta(seconds=181)
    assert await service.claim(call["call_id"], "worker-two")
    async with db.transaction():
        with pytest.raises(RuntimeError, match="cron_daily_retry_lease_lost"):
            await service.locked(db, call["call_id"], "worker-one")
        row = await service.locked(db, call["call_id"], "worker-two")
        assert row["queue_cursor"] == 0


@pytest.mark.asyncio
async def test_source_validation_and_missing_schema_are_not_empty_success(db):
    service = DailyRetryCalls(db)
    for source in ("", " bank", "bank\n", "a" * 129):
        with pytest.raises(ValueError):
            await service.submit(source)
    db.conn.execute("DROP TABLE swe_cron_failure_retry_calls")
    with pytest.raises(
        RuntimeError,
        match="cron_daily_retry_storage_unavailable",
    ):
        await service.submit("bank")
