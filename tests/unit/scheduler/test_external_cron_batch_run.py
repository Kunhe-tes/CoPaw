# -*- coding: utf-8 -*-
"""Verify external batch admission through HTTP and the real queue store."""

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.unit.scheduler.test_managed_cron_callbacks import (
    callback_setup,
    create_source,
)
from tests.unit.scheduler.test_managed_cron_distribution import payload

PATH = "/api/scheduler/external/cron/batch/run"
HEADERS = {"X-User-Id": "alice", "X-Source-Id": "bank"}
NOW = datetime(2026, 11, 8, 3, tzinfo=timezone.utc)  # Sunday


def batch_client(db):
    from scheduler.app.routers import external_cron
    from scheduler.app.routers.managed_callbacks import scheduling_service
    from scheduler.app.services.cron.managed.scheduling import (
        ManagedSchedulingService,
    )

    app = FastAPI()
    app.include_router(external_cron.router, prefix="/api")
    app.dependency_overrides[scheduling_service] = lambda: (
        ManagedSchedulingService(db, clock=lambda: NOW)
    )
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


@pytest.mark.asyncio
async def test_external_batch_enqueues_parent_and_children(callback_setup):
    from scheduler.app.services.cron.managed.distribution import BroadcastStore
    from scheduler.app.services.cron.managed.distribution_worker import (
        BroadcastProcessor,
    )

    db, caller, management = callback_setup
    parent = await create_source(callback_setup, "batch_enabled")
    job_id = parent["job_id"]
    distribution = await BroadcastStore(db).submit(caller, job_id, payload())
    await BroadcastProcessor(
        db,
        management.resources,
        management.platform,
    ).process(
        distribution["task_id"],
    )
    # Platform references are unnecessary for authenticated manual triggering.
    db.conn.execute(
        "UPDATE swe_cron_job_states SET batch_external_job_id=NULL",
    )

    async with batch_client(db) as client:
        first = await client.post(
            PATH,
            json={"jobId": job_id},
            headers=HEADERS,
        )
        child = await db.fetch_one(
            "SELECT job_id, tenant_id FROM swe_cron_jobs_v2 WHERE parent_job_id=?",
            (job_id,),
        )
        child_response = await client.post(
            PATH,
            json={"jobId": child["job_id"]},
            headers={
                **HEADERS,
                "X-Tenant-Id": child["tenant_id"],
                "X-User-Role": "manager",
            },
        )

    assert first.status_code == 202
    assert first.json()["accepted"] is True
    assert first.json()["enqueued_intents"] == 3
    assert first.json()["trigger_time_basis"] == "manual"
    assert child_response.status_code == 409
    assert child_response.json()["detail"] == "cron_batch_run_requires_parent"
    members = await db.fetch_all(
        "SELECT tenant_id FROM swe_cron_managed_batch_members WHERE batch_id=?",
        (first.json()["batch_id"],),
    )
    assert len({member["tenant_id"] for member in members}) == 3


@pytest.mark.asyncio
async def test_concurrent_external_requests_create_only_one_batch(
    callback_setup,
):
    db, _, _ = callback_setup
    parent = await create_source(callback_setup, "batch_enabled")
    async with batch_client(db) as client:
        results = await asyncio.gather(
            *(
                client.post(
                    PATH,
                    json={"jobId": parent["job_id"]},
                    headers=HEADERS,
                )
                for _ in range(2)
            ),
        )
    accepted, conflict = sorted(
        results,
        key=lambda response: response.status_code,
    )
    assert accepted.status_code == 202
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == {
        "code": "cron_batch_already_active",
        "batch_id": accepted.json()["batch_id"],
    }
    assert (
        len(
            await db.fetch_all(
                "SELECT * FROM swe_cron_managed_trigger_receipts",
            ),
        )
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["running", "dispatch_failed", "success"])
async def test_unfinished_platform_batch_blocks_external_trigger(
    callback_setup,
    status,
):
    from scheduler.app.services.cron.managed.scheduling import (
        ManagedSchedulingService,
    )

    db, caller, _ = callback_setup
    parent = await create_source(
        callback_setup,
        "batch_enabled",
        allow_non_workday=True,
    )
    platform_batch = await ManagedSchedulingService(
        db,
        clock=lambda: NOW,
    ).accept(
        caller,
        {
            "job_id": parent["job_id"],
            "operation_id": parent["operation_id"],
            "callback_protocol": "scheduler_managed_v1",
        },
        "batch",
    )
    assert platform_batch["accepted"]
    db.conn.execute("UPDATE swe_cron_execution_runs SET status=?", (status,))
    async with batch_client(db) as client:
        command = {"jobId": parent["job_id"]}
        conflict = await client.post(PATH, json=command, headers=HEADERS)
        assert conflict.status_code == 409
        assert (
            conflict.json()["detail"]["batch_id"] == platform_batch["batch_id"]
        )
        db.conn.execute(
            "UPDATE swe_cron_execution_runs SET status='success', settled_status='success'",
        )
        accepted = await client.post(PATH, json=command, headers=HEADERS)
    assert accepted.status_code == 202
    assert accepted.json()["batch_id"] != platform_batch["batch_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "extra", "status"),
    [
        ({}, {}, 400),
        ({**HEADERS, "X-Tenant-Id": "other"}, {}, 404),
        ({**HEADERS, "X-Source-Id": "other"}, {}, 404),
        ({**HEADERS, "X-User-Id": "other", "X-Tenant-Id": "alice"}, {}, 404),
        (HEADERS, {"operation_id": "extra"}, 422),
    ],
)
async def test_external_batch_requires_authorized_gateway_identity(
    callback_setup,
    headers,
    extra,
    status,
):
    db, _, _ = callback_setup
    parent = await create_source(callback_setup, "batch_enabled")
    async with batch_client(db) as client:
        response = await client.post(
            PATH,
            json={"jobId": parent["job_id"], **extra},
            headers=headers,
        )
    assert response.status_code == status
    assert await db.fetch_all("SELECT * FROM swe_cron_execution_runs") == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "sql", "reason"),
    [
        ("batch_paused", "", "batch_paused"),
        ("ordinary", "", "job_not_in_batch_mode"),
        (
            "batch_enabled",
            "UPDATE swe_cron_jobs_v2 SET enabled=0",
            "job_not_eligible",
        ),
        (
            "batch_enabled",
            "UPDATE swe_cron_jobs_v2 SET run_end_date='2026-11-07'",
            "job_outside_date_range",
        ),
    ],
)
async def test_external_batch_preserves_execution_gates(
    callback_setup,
    mode,
    sql,
    reason,
):
    db, _, _ = callback_setup
    parent = await create_source(callback_setup, mode)
    if sql:
        db.conn.execute(sql)
    async with batch_client(db) as client:
        response = await client.post(
            PATH,
            json={"jobId": parent["job_id"]},
            headers=HEADERS,
        )
    assert response.status_code == 409
    assert response.json()["detail"] == reason
    assert await db.fetch_all("SELECT * FROM swe_cron_execution_runs") == []
