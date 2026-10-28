# -*- coding: utf-8 -*-
"""外部平台只传来源的受理/查询契约和脱敏错误日志。"""

import logging

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from tests.unit.scheduler.test_daily_failure_retry import scenario
from scheduler.app.routers import daily_failure_retry as api
from scheduler.app.services.cron.managed.daily_retry_service import (
    DailyFailureRetry,
)

PATH = "/api/scheduler/cron/failure-reruns"


@pytest.mark.asyncio
async def test_body_only_202_queries_and_source_isolation(scenario):
    await scenario.run()
    service = DailyFailureRetry(scenario.db, clock=scenario.clock)
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    app.dependency_overrides[api.daily_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(PATH, json={"source_id": "bank"})
        assert response.status_code == 202
        call_id = response.json()["call"]["call_id"]
        assert (
            scenario.db.conn.execute(
                "SELECT COUNT(*) FROM swe_cron_execution_runs",
            ).fetchone()[0]
            == 1
        )
        await service.process(call_id)
        result = await client.get(
            f"{PATH}/{call_id}",
            params={"source_id": "bank"},
        )
        assert result.status_code == 200
        assert result.json()["call"]["status"] == "completed"
        assert result.json()["items"][0]["execution"]["status"] == "queued"
        assert (
            await client.get(f"{PATH}/{call_id}", params={"source_id": "BANK"})
        ).status_code == 404
        assert (
            await client.get(
                f"{PATH}/{call_id}",
                params={"source_id": "bank", "limit": 201},
            )
        ).status_code == 422


@pytest.mark.asyncio
async def test_invalid_body_runtime_and_storage_have_no_fake_acceptance(
    scenario,
    caplog,
):
    service = DailyFailureRetry(scenario.db, clock=scenario.clock)
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    app.dependency_overrides[api.daily_service] = lambda: service
    caplog.set_level(logging.WARNING)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        for body in (
            {},
            {"source_id": ""},
            {"source_id": "bank", "tenant_id": "private-user"},
            {"source_id": " bank"},
        ):
            assert (await client.post(PATH, json=body)).status_code == 422
        app.state.managed_cron_runtime_prepared = True
        app.state.managed_cron_runtime_ready = False
        assert (
            await client.post(PATH, json={"source_id": "bank"})
        ).status_code == 503
        app.state.managed_cron_runtime_ready = True
        scenario.db.conn.execute("DROP TABLE swe_cron_failure_retry_calls")
        response = await client.post(PATH, json={"source_id": "bank"})
        assert response.status_code == 503
        assert response.json() == {
            "detail": "cron_daily_retry_storage_unavailable",
        }
    assert "补跑接口失败" in caplog.text
    assert "private-user" not in caplog.text


@pytest.mark.asyncio
async def test_query_pages_and_each_request_has_its_own_call(scenario):
    await scenario.run()
    await scenario.run()
    service = DailyFailureRetry(scenario.db, clock=scenario.clock)
    first = await service.calls.submit("bank")
    second = await service.calls.submit("bank")
    assert first["call_id"] != second["call_id"]
    await service.process(first["call_id"])
    one = await service.detail("bank", first["call_id"], limit=1)
    assert len(one["items"]) == 1
    assert one["next_event_order"]
    two = await service.detail(
        "bank",
        first["call_id"],
        after=one["next_event_order"],
        limit=1,
    )
    assert len(two["items"]) == 1
    assert (
        one["items"][0]["execution"]["execution_id"]
        != two["items"][0]["execution"]["execution_id"]
    )
