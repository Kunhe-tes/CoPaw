# -*- coding: utf-8 -*-
"""Approval denial and timeout terminal Run contracts on MySQL."""

from __future__ import annotations

from io import StringIO
import json
import os
from types import SimpleNamespace

import httpx
from fastapi import FastAPI
import pytest

from swe.app.approvals.service import ApprovalService
from swe.app.runner.runner import AgentRunner
from swe.config.context import get_current_effective_tenant_id, tenant_context
from swe.database import DatabaseConnection
from swe.observability import Observability, Scope, bind_context
from swe.observability.emitter import JsonlEmitter
from swe.observability.projector import InboxProjector
from swe.observability.query import router as observability_router
from swe.observability import runner_lifecycle
from swe.observability.store import ObservabilityStore
from tests.integrated.observability.test_mysql_pipeline import _test_db_config

pytestmark = pytest.mark.skipif(
    not os.getenv("SWE_AGENTOBS_TEST_DB_HOST"),
    reason="set SWE_AGENTOBS_TEST_DB_HOST to a disposable MySQL *_test database",
)


async def _resolve_approval_with_runner(
    approval_service,
    pending,
    attempt,
    decision,
):
    runner = AgentRunner()
    if decision == "timed_out":
        runner._APPROVAL_TIMEOUT_SECONDS = -1
    with (
        tenant_context(
            tenant_id="default",
            source_id="agentobs-integration",
        ),
        bind_context(attempt),
    ):
        response, consumed, approved_tool_call = (
            await runner._resolve_pending_approval(
                pending.session_id,
                f"/deny {pending.request_id}",
                request=SimpleNamespace(
                    session_id=pending.session_id,
                    user_id=pending.user_id,
                    source_id="agentobs-integration",
                    channel_meta={},
                ),
            )
        )
        resolved = await approval_service.get_request(pending.request_id)
    return response, consumed, approved_tool_call, resolved


async def _project_and_query_run(connection, store, records, run_id):
    async with connection.transaction() as session:
        for record in records:
            await session.insert(
                "INSERT INTO swe_agentobs_inbox (payload_text) VALUES (%s)",
                (json.dumps(record, separators=(",", ":")),),
            )
    projector = InboxProjector(store, poll_seconds=0.01)
    while await projector.project_batch():
        pass

    api = FastAPI()
    api.state.agent_observability_store = store

    @api.middleware("http")
    async def bind_source(request, call_next):
        request.state.source_id = "agentobs-integration"
        request.state.effective_tenant_id = records[0]["scope"]["tenant_id"]
        return await call_next(request)

    api.include_router(observability_router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api),
        base_url="http://agentobs.test",
    ) as client:
        detail = await client.get(
            f"/agent-observability/runs/{run_id}",
            headers={"X-User-Role": "manager"},
        )
        events = await client.get(
            f"/agent-observability/runs/{run_id}/events",
            headers={"X-User-Role": "manager"},
        )
    return detail, events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "approval_status", "expected_status"),
    [
        ("denied", "denied", "rejected"),
        ("timed_out", "timeout", "timed_out"),
    ],
)
async def test_mysql_denied_or_timed_out_approval_ends_waiting_run(
    monkeypatch,
    decision,
    approval_status,
    expected_status,
):
    monkeypatch.setenv(
        "SWE_AGENTOBS_CURSOR_SECRET",
        "integration-cursor-secret-at-least-32",
    )
    connection = DatabaseConnection(_test_db_config())
    await connection.connect()
    try:
        store = ObservabilityStore(connection)
        assert (await store.readiness())["ready"]
        sink = StringIO()
        emitter = JsonlEmitter(stream=sink)
        observer = Observability(emitter)
        monkeypatch.setattr(runner_lifecycle, "_OBSERVABILITY", observer)
        with tenant_context(
            tenant_id="default",
            source_id="agentobs-integration",
        ):
            tenant_id = get_current_effective_tenant_id()
        context = observer.admit_run(
            scope=Scope("swe", "agentobs-integration", tenant_id, "default"),
            business_ref={
                "chat_id": "approval-terminal-chat",
                "root_question_msgid": "approval-terminal-question",
                "session_id": "approval-terminal-session",
            },
            enabled=True,
        )
        attempt = observer.start_attempt(context)
        approval_service = ApprovalService()
        with tenant_context(
            tenant_id="default",
            source_id="agentobs-integration",
        ):
            pending = await approval_service.create_pending(
                session_id="approval-terminal-session",
                user_id="user-a",
                channel="console",
                tool_name="execute_shell_command",
                result=SimpleNamespace(findings=[], findings_count=0),
                extra={
                    "source_id": "agentobs-integration",
                    "tenant_id": tenant_id,
                    "agent_id": "default",
                    "chat_id": "approval-terminal-chat",
                    "msgid": "approval-terminal-question",
                    "agent_observability_context": attempt.to_carrier(),
                },
            )
        approval_id = pending.request_id
        monkeypatch.setattr(
            "swe.app.approvals.service._approval_service",
            approval_service,
        )
        with bind_context(attempt):
            runner_lifecycle.record_approval_requested(attempt, approval_id)
        runner_lifecycle.finish_query_run(
            context,
            attempt,
            "completed",
            waiting_for_approval=True,
        )
        response, consumed, approved_tool_call, resolved = (
            await _resolve_approval_with_runner(
                approval_service,
                pending,
                attempt,
                decision,
            )
        )
        assert response is not None
        assert consumed is True
        assert approved_tool_call is None
        assert resolved is not None
        assert resolved.status == approval_status
        assert emitter.close(timeout=1) == 0
        records = [json.loads(line) for line in sink.getvalue().splitlines()]
        detail, events = await _project_and_query_run(
            connection,
            store,
            records,
            context.obs_run_id,
        )

        assert detail.status_code == events.status_code == 200
        body = detail.json()
        assert body["run"]["status"] == expected_status
        assert [item["status"] for item in body["attempts"]] == [
            "waiting_approval",
        ]
        event_rows = events.json()["items"]
        approval_events = [
            item
            for item in event_rows
            if item["event_name"]
            in {"approval.requested", "approval.resolved"}
        ]
        assert len(approval_events) == 2
        requested = next(
            item
            for item in approval_events
            if item["event_name"] == "approval.requested"
        )
        resolved = next(
            item
            for item in approval_events
            if item["event_name"] == "approval.resolved"
        )
        assert requested["entity_id"] == resolved["entity_id"] == approval_id
        assert (
            requested["attempt_id"]
            == resolved["attempt_id"]
            == (attempt.obs_attempt_id)
        )
        assert requested["occurred_at"] < resolved["occurred_at"]
        assert resolved["metadata"]["decision"] == decision
        assert [item["event_name"] for item in event_rows].count(
            "run.ended",
        ) == 1
    finally:
        await connection.close()
