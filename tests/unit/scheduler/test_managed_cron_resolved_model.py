# -*- coding: utf-8 -*-
"""Admission freezes a concrete tenant model, never a synthetic pool name."""

import json
from unittest.mock import AsyncMock

import pytest

from tests.unit.scheduler.test_managed_cron_executions import execution_setup
from tests.unit.scheduler.test_managed_cron_management import create_payload


@pytest.mark.asyncio
async def test_default_is_resolved_per_execution_and_frozen(
    monkeypatch,
    execution_setup,
):
    from scheduler.app.services.cron.managed import executions

    resolve = AsyncMock(
        side_effect=[
            {"provider_id": "tenant-provider", "model": "model-one"},
            {"provider_id": "tenant-provider", "model": "model-two"},
        ],
    )
    monkeypatch.setattr(
        executions,
        "resolve_agent_model",
        resolve,
        raising=False,
    )
    db, caller, management = execution_setup
    created = await management.create(caller, create_payload())
    store = executions.ExecutionStore(db)
    first, _ = await store.enqueue(
        caller,
        created["job_id"],
        executions.ExecutionRequest("manual", "one"),
    )
    repeated, reused = await store.enqueue(
        caller,
        created["job_id"],
        executions.ExecutionRequest("manual", "one"),
    )
    assert reused and repeated["execution_id"] == first["execution_id"]
    assert resolve.await_count == 1
    assert (first["provider_id"], first["model_id"]) == (
        "tenant-provider",
        "model-one",
    )
    assert json.loads(first["spec_json"])["model_slot"] == {
        "provider_id": "tenant-provider",
        "model": "model-one",
    }
    # End the first run so a distinct manual request can be admitted.
    await db.execute(
        "UPDATE swe_cron_execution_runs SET status='success' WHERE execution_id=%s",
        (first["execution_id"],),
    )
    second, _ = await store.enqueue(
        caller,
        created["job_id"],
        executions.ExecutionRequest("manual", "two"),
    )
    assert second["model_id"] == "model-two"
    definition = await db.fetch_one(
        "SELECT spec_json FROM swe_cron_jobs_v2 WHERE job_id=%s",
        (created["job_id"],),
    )
    assert json.loads(definition["spec_json"]).get("model_slot") is None


@pytest.mark.asyncio
async def test_resolution_failure_does_not_insert_execution(
    monkeypatch,
    execution_setup,
):
    from scheduler.app.services.cron.managed import executions

    monkeypatch.setattr(
        executions,
        "resolve_agent_model",
        AsyncMock(side_effect=ValueError("cron_default_model_unavailable")),
        raising=False,
    )
    db, caller, management = execution_setup
    created = await management.create(caller, create_payload())
    with pytest.raises(ValueError, match="cron_default_model_unavailable"):
        await executions.ExecutionStore(db).enqueue(
            caller,
            created["job_id"],
            executions.ExecutionRequest("manual", "one"),
        )
    assert (
        await db.fetch_one("SELECT execution_id FROM swe_cron_execution_runs")
        is None
    )


@pytest.mark.asyncio
async def test_completion_records_effective_fallback_model(execution_setup):
    from swe.app.crons.managed_results import ExecutionOutcome, ExecutionWriter
    from tests.unit.scheduler.test_managed_cron_executions import enqueue

    db = execution_setup[0]
    run, _ = await enqueue(execution_setup)
    key = tuple(
        run[name] for name in ("tenant_id", "source_id", "agent_id", "job_id")
    )
    writer = ExecutionWriter(db)
    await writer.accept(run["execution_id"], key)
    await writer.start(run["execution_id"], key, "worker")
    await writer.complete(
        run["execution_id"],
        key,
        "worker",
        ExecutionOutcome(
            "success",
            execution_meta={
                "effective_model_slot": {
                    "provider_id": "fallback-provider",
                    "model": "fallback-model",
                },
            },
        ),
    )
    row = await db.fetch_one(
        "SELECT provider_id, model_id FROM swe_cron_execution_runs",
    )
    assert (row["provider_id"], row["model_id"]) == (
        "fallback-provider",
        "fallback-model",
    )


@pytest.mark.parametrize(
    "slot",
    [
        None,
        {},
        {"provider_id": "default", "model": "default"},
        {"provider_id": "p", "model": " default "},
    ],
)
def test_unresolved_result_cannot_replace_concrete_pool(slot):
    from swe.app.crons.managed_results import (
        ExecutionOutcome,
        effective_model_values,
    )

    assert (
        effective_model_values(
            ExecutionOutcome(
                "error",
                execution_meta={"effective_model_slot": slot},
            ),
        )
        == {}
    )
