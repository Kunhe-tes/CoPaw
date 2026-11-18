# -*- coding: utf-8 -*-
"""Approval denial and timeout terminal Run contracts on MySQL."""

from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
import json
import os
from uuid import uuid4

import httpx
from fastapi import FastAPI
import pytest

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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "business_status", "expected_status"),
    [
        ("denied", "rejected", "rejected"),
        ("timed_out", "timed_out", "timed_out"),
    ],
)
async def test_mysql_denied_or_timed_out_approval_ends_waiting_run(
    monkeypatch,
    decision,
    business_status,
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
        context = observer.admit_run(
            scope=Scope("swe", "agentobs-integration", "user-a", "default"),
            business_ref={
                "chat_id": "approval-terminal-chat",
                "root_question_msgid": "approval-terminal-question",
            },
            enabled=True,
        )
        attempt = observer.start_attempt(context)
        approval_id = str(uuid4())
        started_at = datetime.now(timezone.utc).timestamp() - 3
        with bind_context(attempt):
            runner_lifecycle.record_approval_requested(
                attempt,
                approval_id,
                started_at=started_at,
            )
        runner_lifecycle.finish_query_run(
            context,
            attempt,
            "completed",
            waiting_for_approval=True,
        )
        with bind_context(attempt):
            runner_lifecycle.record_approval_resolved(
                approval_id,
                decision,
                started_at=started_at,
            )
        runner_lifecycle.finish_query_run(context, None, business_status)
        assert emitter.close(timeout=1) == 0
        records = [json.loads(line) for line in sink.getvalue().splitlines()]
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
            return await call_next(request)

        api.include_router(observability_router)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api),
            base_url="http://agentobs.test",
        ) as client:
            detail = await client.get(
                f"/agent-observability/runs/{context.obs_run_id}",
                headers={"X-User-Role": "manager"},
            )
            events = await client.get(
                f"/agent-observability/runs/{context.obs_run_id}/events",
                headers={"X-User-Role": "manager"},
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
