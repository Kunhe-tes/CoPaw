# -*- coding: utf-8 -*-
"""新工作域必须可恢复，并且缺少新表不能破坏原有执行域。"""

from datetime import timedelta

import pytest

from tests.unit.scheduler.test_daily_failure_retry import scenario
from tests.unit.scheduler.test_managed_cron_management import ResourceClient
from tests.unit.scheduler.test_managed_cron_dispatch_state import ModePlatform
from scheduler.app.services.cron.managed.recovery import ManagedRecoveryWorker
from scheduler.app.services.cron.managed.daily_retry_service import (
    DailyFailureRetry,
)


@pytest.mark.asyncio
async def test_recovery_tick_resumes_expired_call(scenario, monkeypatch):
    await scenario.run()
    old = DailyFailureRetry(scenario.db, clock=scenario.clock)
    call = await old.calls.submit("bank")
    await old.calls.claim(call["call_id"], "dead-worker")
    scenario.now[0] += timedelta(seconds=181)
    worker = ManagedRecoveryWorker(
        scenario.db,
        ResourceClient(),
        ModePlatform(),
        None,
    )
    worker.daily_retry = DailyFailureRetry(scenario.db, clock=scenario.clock)

    async def no_network():
        return 0

    monkeypatch.setattr(worker, "_dispatch", no_network)
    monkeypatch.setattr(worker, "_recover", no_network)
    result = await worker.tick()
    assert result["daily_failure_retry"] == 1
    row = await worker.daily_retry.calls.get("bank", call["call_id"])
    assert row["queued_count"] == 1
    assert row["status"] == "completed"


@pytest.mark.asyncio
async def test_missing_call_table_does_not_block_existing_lanes(
    scenario,
    monkeypatch,
):
    scenario.db.conn.execute("DROP TABLE swe_cron_failure_retry_calls")
    worker = ManagedRecoveryWorker(
        scenario.db,
        ResourceClient(),
        ModePlatform(),
        None,
    )
    seen = []

    async def dispatch():
        seen.append(True)
        return 1

    async def recover():
        return 0

    monkeypatch.setattr(worker, "_dispatch", dispatch)
    monkeypatch.setattr(worker, "_recover", recover)
    result = await worker.tick()
    assert result["daily_failure_retry"] == 0
    assert result["dispatched"] == 1
    assert seen == [True]
