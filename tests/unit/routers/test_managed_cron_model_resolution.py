# -*- coding: utf-8 -*-
"""Resolve a scoped default and persist it through the real HTTP boundary."""

import httpx
import pytest
from fastapi import FastAPI

from tests.unit.app.test_managed_cron_broadcast_models import model_manager
from tests.unit.scheduler.test_managed_cron_executions import execution_setup
from tests.unit.scheduler.test_managed_cron_management import create_payload


def model_app(monkeypatch, *, available=True):
    from swe.app.crons import managed_model_api

    seen = []

    def manager(spec):
        seen.append((spec.tenant_id, spec.source_id))
        return model_manager(default_available=available)

    monkeypatch.setattr(managed_model_api, "get_model_manager", manager)
    app = FastAPI()
    app.include_router(managed_model_api.router, prefix="/api")
    return app, seen


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "slot",
    [
        None,
        {"provider_id": "receiver-provider", "model": "default-model"},
        {"provider_id": "removed-provider", "model": "removed-model"},
    ],
)
async def test_resolves_only_target_tenant_model(monkeypatch, slot):
    app, seen = model_app(monkeypatch)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://swe",
    ) as client:
        response = await client.post(
            "/api/internal/cron/managed/resolve-model",
            headers={
                "X-User-Id": "alice",
                "X-Tenant-Id": "alice",
                "X-Source-Id": "bank",
            },
            json={"model_slot": slot},
        )
    assert response.status_code == 200
    assert response.json() == {
        "provider_id": "receiver-provider",
        "model": "default-model",
    }
    assert seen == [("alice", "bank")]


@pytest.mark.asyncio
async def test_no_available_default_is_an_error(monkeypatch):
    app, _ = model_app(monkeypatch, available=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://swe",
    ) as client:
        response = await client.post(
            "/api/internal/cron/managed/resolve-model",
            headers={"X-User-Id": "alice", "X-Source-Id": "bank"},
            json={},
        )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_bad_identity_is_rejected_before_provider_access(monkeypatch):
    app, seen = model_app(monkeypatch)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://swe",
    ) as client:
        response = await client.post(
            "/api/internal/cron/managed/resolve-model",
            headers={
                "X-User-Id": "alice",
                "X-Source-Id": "bank",
                "X-Scope-Id": "bob-other",
            },
            json={},
        )
    assert response.status_code == 400
    assert seen == []


@pytest.mark.asyncio
async def test_http_resolution_is_stored_in_execution_pool(
    monkeypatch,
    execution_setup,
):
    from scheduler.app.services.cron.managed import (
        executions,
        model_resolution,
    )

    app, seen = model_app(monkeypatch)
    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        model_resolution.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(
            transport=httpx.ASGITransport(app=app),
            **kwargs,
        ),
    )
    monkeypatch.setenv("SCHEDULER_SWE_API_BASE_URL", "http://swe/api")
    monkeypatch.setattr(
        executions,
        "resolve_agent_model",
        model_resolution.resolve_agent_model,
    )
    db, caller, management = execution_setup
    created = await management.create(caller, create_payload())
    run, _ = await executions.ExecutionStore(db).enqueue(
        caller,
        created["job_id"],
        executions.ExecutionRequest("manual", "click"),
    )
    stored = await db.fetch_one(
        "SELECT provider_id,model_id FROM swe_cron_execution_runs WHERE execution_id=%s",
        (run["execution_id"],),
    )
    assert stored == {
        "provider_id": "receiver-provider",
        "model_id": "default-model",
    }
    assert seen == [("alice", "bank")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [
        {"provider_id": "default", "model": "default"},
        {"provider_id": "p", "model": " default "},
        {},
        [],
    ],
)
async def test_client_rejects_unresolved_identity(monkeypatch, value):
    from scheduler.app.services.cron.managed import model_resolution

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        model_resolution.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=value),
            ),
            **kwargs,
        ),
    )
    monkeypatch.setenv("SCHEDULER_SWE_API_BASE_URL", "http://swe")
    row = {
        "tenant_id": "alice",
        "source_id": "bank",
        "agent_id": "default",
        "creator_user_id": "alice",
    }
    with pytest.raises(ValueError, match="cron_execution_model_unavailable"):
        await model_resolution.resolve_agent_model(row, {})
