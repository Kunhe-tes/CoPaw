# -*- coding: utf-8 -*-
"""Tests for the latest cron execution subtask-count API."""

from unittest.mock import AsyncMock

from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
import pytest
from starlette.requests import Request

from monitor.app._app import app
from monitor.app.models.cron import LatestExecutionSubtaskCountResponse
from monitor.app.routers.cron import router as cron_router
from monitor.app.routers.external import (
    get_latest_execution_subtask_count,
    require_external_source_id,
    router,
)
from monitor.app.services.cron import query_service as query_service_module
from monitor.app.services.cron import get_query_service
from monitor.app.services.cron.query_service import QueryService


class FakeDb:
    def __init__(self, one_results):
        self.one_results = list(one_results)
        self.fetch_one_calls = []

    async def fetch_one(self, sql, params=None):
        self.fetch_one_calls.append((sql, params))
        return self.one_results.pop(0) if self.one_results else None


def _request(*, source_id: str | None = "source-a") -> Request:
    headers = []
    if source_id is not None:
        headers.append((b"x-source-id", source_id.encode("utf-8")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
        },
    )


def test_latest_execution_subtask_count_route_contract():
    matches = [
        route
        for route in router.routes
        if getattr(route, "path", "")
        == (
            "/monitor/external/cron/jobs/{job_id}/latest-execution/"
            "subtask-count"
        )
    ]

    assert len(matches) == 1
    assert matches[0].methods == {"GET"}
    assert matches[0].response_model is LatestExecutionSubtaskCountResponse

    registered_paths = set(app.openapi()["paths"])
    assert (
        "/api/monitor/external/cron/jobs/{job_id}/latest-execution/"
        "subtask-count"
        in registered_paths
    )
    assert (
        "/api/monitor/cron/jobs/{job_id}/latest-execution/subtask-count"
        not in registered_paths
    )
    operation = app.openapi()["paths"][
        "/api/monitor/external/cron/jobs/{job_id}/latest-execution/"
        "subtask-count"
    ]["get"]
    assert operation["tags"] == ["external"]
    assert {"200", "400", "404"}.issubset(operation["responses"])
    source_header = next(
        parameter
        for parameter in operation["parameters"]
        if parameter["name"] == "X-Source-Id"
    )
    assert source_header["in"] == "header"
    assert source_header["required"] is True
    assert all(
        getattr(route, "path", "")
        != "/monitor/cron/jobs/{job_id}/latest-execution/subtask-count"
        for route in cron_router.routes
    )


@pytest.mark.asyncio
async def test_latest_execution_subtask_count_uses_scoped_latest_execution(
    monkeypatch,
):
    db = FakeDb(
        [
            {"id": "job-1", "tenant_id": "tenant-a"},
            {
                "execution_id": 42,
                "trace_id": "trace-42",
                "subtask_count": 7,
            },
        ],
    )
    monkeypatch.setattr(
        query_service_module,
        "get_db_connection",
        lambda: db,
    )

    result = await QueryService().get_latest_execution_subtask_count(
        job_id="job-1",
        source_id="source-a",
    )

    assert result is not None
    assert result.model_dump() == {
        "job_id": "job-1",
        "execution_id": 42,
        "trace_id": "trace-42",
        "subtask_count": 7,
    }
    job_sql, job_params = db.fetch_one_calls[0]
    assert "FROM swe_cron_jobs" in job_sql
    assert "source_id = %s" in job_sql
    assert job_params == ("job-1", "source-a")

    execution_sql, execution_params = db.fetch_one_calls[1]
    assert "FROM swe_cron_executions e" in execution_sql
    assert "FROM swe_cron_subtasks s" in execution_sql
    assert "ORDER BY e.actual_time DESC, e.id DESC" in execution_sql
    assert execution_params == ("job-1", "tenant-a")


@pytest.mark.asyncio
async def test_latest_execution_subtask_count_returns_zero_without_execution(
    monkeypatch,
):
    db = FakeDb([{"id": "job-1", "tenant_id": "tenant-a"}, None])
    monkeypatch.setattr(
        query_service_module,
        "get_db_connection",
        lambda: db,
    )

    result = await QueryService().get_latest_execution_subtask_count(
        job_id="job-1",
        source_id="source-a",
    )

    assert result is not None
    assert result.model_dump() == {
        "job_id": "job-1",
        "execution_id": None,
        "trace_id": None,
        "subtask_count": 0,
    }


@pytest.mark.asyncio
async def test_latest_execution_subtask_count_rejects_job_outside_source(
    monkeypatch,
):
    db = FakeDb([None])
    monkeypatch.setattr(
        query_service_module,
        "get_db_connection",
        lambda: db,
    )

    result = await QueryService().get_latest_execution_subtask_count(
        job_id="job-1",
        source_id="source-b",
    )

    assert result is None
    assert len(db.fetch_one_calls) == 1


@pytest.mark.asyncio
async def test_latest_execution_without_trace_does_not_count_older_subtasks(
    monkeypatch,
):
    db = FakeDb(
        [
            {"id": "job-1", "tenant_id": "tenant-a"},
            {
                "execution_id": 43,
                "trace_id": "",
                "subtask_count": 99,
            },
        ],
    )
    monkeypatch.setattr(
        query_service_module,
        "get_db_connection",
        lambda: db,
    )

    result = await QueryService().get_latest_execution_subtask_count(
        job_id="job-1",
        source_id="source-a",
    )

    assert result is not None
    assert result.execution_id == 43
    assert result.trace_id is None
    assert result.subtask_count == 0


@pytest.mark.asyncio
async def test_latest_execution_subtask_count_route_uses_gateway_source():
    service = AsyncMock()
    service.get_latest_execution_subtask_count.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await get_latest_execution_subtask_count(
            job_id="job-1",
            source_id="source-a",
            service=service,
        )

    assert exc_info.value.status_code == 404
    service.get_latest_execution_subtask_count.assert_awaited_once_with(
        job_id="job-1",
        source_id="source-a",
    )


def test_latest_execution_subtask_count_route_requires_gateway_source():
    with pytest.raises(HTTPException) as exc_info:
        require_external_source_id(_request(source_id=None))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "X-Source-Id header is required"


@pytest.mark.asyncio
async def test_external_endpoint_enforces_and_forwards_gateway_source():
    service = AsyncMock()
    service.get_latest_execution_subtask_count.return_value = (
        LatestExecutionSubtaskCountResponse(
            job_id="job-1",
            execution_id=42,
            trace_id="trace-42",
            subtask_count=7,
        )
    )
    app.dependency_overrides[get_query_service] = lambda: service

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            missing_source = await client.get(
                "/api/monitor/external/cron/jobs/job-1/"
                "latest-execution/subtask-count",
            )
            response = await client.get(
                "/api/monitor/external/cron/jobs/job-1/"
                "latest-execution/subtask-count",
                headers={"X-Source-Id": "source-a"},
            )
    finally:
        app.dependency_overrides.clear()

    assert missing_source.status_code == 400
    assert response.status_code == 200
    assert response.json() == {
        "job_id": "job-1",
        "execution_id": 42,
        "trace_id": "trace-42",
        "subtask_count": 7,
    }
    service.get_latest_execution_subtask_count.assert_awaited_once_with(
        job_id="job-1",
        source_id="source-a",
    )
