# -*- coding: utf-8 -*-
"""Tool business and technical status contract on MySQL."""

from __future__ import annotations

from io import StringIO
import json
import os
from uuid import uuid4

import httpx
from fastapi import FastAPI
import pytest

from swe.agents.tool_guard_mixin import ToolGuardMixin
from swe.database import DatabaseConnection
from swe.observability import Observability, Scope, bind_context
from swe.observability.config import EmitterConfig
from swe.observability.emitter import JsonlEmitter
from swe.observability.projector import InboxProjector
from swe.observability.query import router as observability_router
from swe.observability.store import ObservabilityStore
from tests.integrated.observability.test_mysql_pipeline import _test_db_config

pytestmark = pytest.mark.skipif(
    not os.getenv("SWE_AGENTOBS_TEST_DB_HOST"),
    reason="set SWE_AGENTOBS_TEST_DB_HOST to a disposable MySQL *_test database",
)


class _ToolExecutor:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    async def _acting(self, tool_call):
        self.calls.append(tool_call)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class _ToolAgent(ToolGuardMixin, _ToolExecutor):
    def _resolve_mcp_server(self, _tool_name):
        return None

    def _tool_has_specific_timeout(self, _tool_name):
        return True


async def _project_events(connection, store, records):
    async with connection.transaction() as session:
        for record in records:
            await session.insert(
                "INSERT INTO swe_agentobs_inbox (payload_text) VALUES (%s)",
                (json.dumps(record, separators=(",", ":")),),
            )
    projector = InboxProjector(store, poll_seconds=0.01)
    while await projector.project_batch():
        pass


async def _assert_authorized_tool_api(
    store,
    run_id,
    expected_run_status,
    expected_tool_status,
    expected_technical_status,
    expected_has_error,
    expected_error_type,
):
    api = FastAPI()
    api.state.agent_observability_store = store

    @api.middleware("http")
    async def bind_source(request, call_next):
        request.state.source_id = request.headers.get("X-Source-Id")
        return await call_next(request)

    api.include_router(observability_router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api),
        base_url="http://agentobs.test",
    ) as client:
        detail = await client.get(
            f"/agent-observability/runs/{run_id}",
            headers={
                "X-User-Role": "manager",
                "X-Source-Id": "agentobs-integration",
            },
        )
        forbidden = await client.get(
            f"/agent-observability/runs/{run_id}",
            headers={
                "X-User-Role": "manager",
                "X-Source-Id": "another-source",
            },
        )

    assert detail.status_code == 200
    assert forbidden.status_code == 404
    body = detail.json()
    assert body["run"]["status"] == expected_run_status
    tool_span = next(
        item for item in body["spans"] if item["span_type"] == "Tool"
    )
    assert tool_span["status"] == expected_tool_status
    assert tool_span["technical_status"] == expected_technical_status
    assert tool_span["has_error"] == expected_has_error
    assert tool_span["error_type"] == expected_error_type
    detail_payload = json.dumps(body, ensure_ascii=False)
    assert "PRIVATE_TOOL_ARGUMENT" not in detail_payload
    assert "PRIVATE_TOOL_EXCEPTION" not in detail_payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "outcome",
        "expected_tool_status",
        "expected_technical_status",
        "expected_has_error",
        "expected_error_type",
        "expected_run_status",
    ),
    [
        (
            {"isError": True, "error_type": "permission_denied"},
            "failed",
            "OK",
            0,
            "permission_denied",
            "succeeded",
        ),
        (
            RuntimeError("PRIVATE_TOOL_EXCEPTION"),
            "failed",
            "ERROR",
            1,
            "RuntimeError",
            "failed",
        ),
    ],
    ids=["business-denial", "technical-exception"],
)
async def test_real_tool_span_statuses_reach_authorized_mysql_api(
    monkeypatch,
    outcome,
    expected_tool_status,
    expected_technical_status,
    expected_has_error,
    expected_error_type,
    expected_run_status,
):
    monkeypatch.setenv(
        "SWE_AGENTOBS_CURSOR_SECRET",
        "integration-cursor-secret-at-least-32",
    )
    sink = StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=sink)
    monkeypatch.setattr(
        "swe.observability.instrumentation.default_emitter",
        lambda: emitter,
    )
    observer = Observability(emitter)
    context = observer.admit_run(
        scope=Scope("swe", "agentobs-integration", "user-a", "default"),
        enabled=True,
    )
    attempt = observer.start_attempt(context)
    agent = _ToolAgent(outcome)
    tool_call = {
        "id": str(uuid4()),
        "name": "read_file",
        "input": {"path": "PRIVATE_TOOL_ARGUMENT"},
    }
    with bind_context(attempt):
        try:
            await agent._run_tool_call_with_hard_timeout_impl(
                tool_call,
                "read_file",
                tool_call["input"],
            )
        except RuntimeError as exc:
            assert isinstance(outcome, RuntimeError)
            assert exc is outcome
            observer.end_attempt(attempt, status="failed")
            observer.end_run(context, status="failed")
        else:
            assert isinstance(outcome, dict)
            observer.end_attempt(attempt, status="succeeded")
            observer.end_run(context, status="succeeded")
    assert agent.calls == [tool_call]
    assert emitter.close(timeout=1) == 0

    payload = sink.getvalue()
    assert "PRIVATE_TOOL_ARGUMENT" not in payload
    assert "PRIVATE_TOOL_EXCEPTION" not in payload
    records = [json.loads(line) for line in payload.splitlines()]
    tool_ends = [
        item
        for item in records
        if item["event_name"] == "span.ended"
        and item.get("span_type") == "Tool"
    ]
    assert len(tool_ends) == 1
    assert tool_ends[0]["status"] == expected_tool_status
    assert tool_ends[0]["technical_status"] == expected_technical_status
    assert tool_ends[0]["has_error"] is bool(expected_has_error)
    assert tool_ends[0]["error_type"] == expected_error_type

    connection = DatabaseConnection(_test_db_config())
    await connection.connect()
    try:
        store = ObservabilityStore(connection)
        assert (await store.readiness())["ready"]
        await _project_events(connection, store, records)
        await _assert_authorized_tool_api(
            store,
            context.obs_run_id,
            expected_run_status,
            expected_tool_status,
            expected_technical_status,
            expected_has_error,
            expected_error_type,
        )
    finally:
        await connection.close()
