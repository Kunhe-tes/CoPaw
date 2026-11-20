# -*- coding: utf-8 -*-
"""Exact Run and Attempt identity queries include historical records."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Request

from swe.database import DatabaseConfig, DatabaseConnection
from swe.observability.projector import InboxProjector
from swe.observability.query import router as observability_router
from swe.observability.store import ObservabilityStore

_DB_HOST = os.getenv("SWE_AGENTOBS_TEST_DB_HOST")
pytestmark = pytest.mark.skipif(
    not _DB_HOST,
    reason="set SWE_AGENTOBS_TEST_DB_HOST to a disposable MySQL *_test database",
)


def _test_db_config() -> DatabaseConfig:
    database = os.getenv("SWE_AGENTOBS_TEST_DB_NAME", "")
    if not database.endswith("_test"):
        raise RuntimeError(
            "Agent observability integration DB must end in _test",
        )
    return DatabaseConfig(
        host=_DB_HOST or "",
        port=int(os.getenv("SWE_AGENTOBS_TEST_DB_PORT", "3306")),
        user=os.getenv("SWE_AGENTOBS_TEST_DB_USER", "root"),
        password=os.getenv("SWE_AGENTOBS_TEST_DB_PASSWORD", ""),
        database=database,
        min_connections=1,
        max_connections=3,
        ssl_disabled=True,
        time_zone="+00:00",
        acquire_timeout=5,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
        cleanup_timeout=1,
    )


def _event(
    *,
    run_id: str,
    event_name: str,
    phase: str,
    status: str,
    occurred_at: datetime,
    started_at: datetime,
    ended_at: datetime | None,
    entity_kind: str,
    entity_id: str,
    attempt_id: str | None = None,
    attempt_started_at: datetime | None = None,
) -> dict:
    event = {
        "schema_version": 1,
        "event_id": str(uuid4()),
        "event_name": event_name,
        "occurred_at": occurred_at.isoformat(timespec="microseconds"),
        "producer_id": f"mysql-test:{uuid4()}",
        "obs_run_id": run_id,
        "run_started_at": started_at.isoformat(timespec="microseconds"),
        "capture_enabled": True,
        "entity_kind": entity_kind,
        "entity_id": entity_id,
        "phase_key": phase,
        "local_seq": 0,
        "scope": {
            "service_unit_id": "swe",
            "source_id": "agentobs-integration",
            "tenant_id": "integration-user",
            "agent_id": "default",
        },
        "business_ref": {
            "chat_id": f"chat-{run_id}",
            "root_question_msgid": f"question-{run_id}",
            "session_id": f"session-{run_id}",
        },
        "started_at": started_at.isoformat(timespec="microseconds"),
        "status": status,
    }
    if attempt_id is not None:
        event["started_at"] = (attempt_started_at or started_at).isoformat(
            timespec="microseconds",
        )
        event.update(
            obs_attempt_id=attempt_id,
            attempt_index=1,
            attempt_started_at=(attempt_started_at or started_at).isoformat(
                timespec="microseconds",
            ),
        )
    if ended_at is not None:
        event["ended_at"] = ended_at.isoformat(timespec="microseconds")
        event["terminal_fact_source"] = "business_settlement"
        event["metrics"] = {"duration_us": 2_000_000}
    return event


@pytest.mark.asyncio
async def test_exact_run_and_attempt_queries_include_historical_records(
    monkeypatch,
):
    monkeypatch.setenv(
        "SWE_AGENTOBS_CURSOR_SECRET",
        "historical-run-query-cursor-secret-at-least-32",
    )
    connection = DatabaseConnection(_test_db_config())
    await connection.connect()
    try:
        store = ObservabilityStore(connection)
        assert (await store.readiness())["ready"]
        projector = InboxProjector(store, poll_seconds=0.01)

        async def ingest(event: dict) -> None:
            async with connection.transaction() as session:
                ingest_id = await session.insert(
                    "INSERT INTO swe_agentobs_inbox (payload_text) VALUES (%s)",
                    (json.dumps(event, separators=(",", ":")),),
                )
            for _ in range(10):
                await projector.project_batch()
                async with connection.acquire() as session:
                    row = await session.fetch_one(
                        "SELECT processing_state FROM swe_agentobs_inbox "
                        "WHERE ingest_id=%s",
                        (ingest_id,),
                    )
                if row and row["processing_state"] != 0:
                    break
            assert row and row["processing_state"] == 1, row

        now = datetime.now(timezone.utc)
        run_started = now - timedelta(days=7)
        attempt_started = run_started + timedelta(seconds=1)
        ended = run_started + timedelta(seconds=2)
        run_id = str(uuid4())
        attempt_id = str(uuid4())
        await ingest(
            _event(
                run_id=run_id,
                event_name="run.accepted",
                phase="accepted",
                status="accepted",
                occurred_at=run_started,
                started_at=run_started,
                ended_at=None,
                entity_kind="run",
                entity_id=run_id,
            ),
        )
        await ingest(
            _event(
                run_id=run_id,
                event_name="attempt.started",
                phase="started",
                status="running",
                occurred_at=attempt_started,
                started_at=run_started,
                ended_at=None,
                entity_kind="attempt",
                entity_id=attempt_id,
                attempt_id=attempt_id,
                attempt_started_at=attempt_started,
            ),
        )
        await ingest(
            _event(
                run_id=run_id,
                event_name="attempt.ended",
                phase="ended",
                status="succeeded",
                occurred_at=ended,
                started_at=run_started,
                ended_at=ended,
                entity_kind="attempt",
                entity_id=attempt_id,
                attempt_id=attempt_id,
                attempt_started_at=attempt_started,
            ),
        )
        await ingest(
            _event(
                run_id=run_id,
                event_name="run.ended",
                phase="ended",
                status="succeeded",
                occurred_at=ended,
                started_at=run_started,
                ended_at=ended,
                entity_kind="run",
                entity_id=run_id,
            ),
        )

        api = FastAPI()
        api.state.agent_observability_store = store

        @api.middleware("http")
        async def bind_test_source(request: Request, call_next):
            request.state.source_id = request.headers.get("X-Source-Id")
            request.state.effective_tenant_id = "integration-user"
            return await call_next(request)

        api.include_router(observability_router)
        headers = {
            "X-User-Role": "manager",
            "X-Source-Id": "agentobs-integration",
        }
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api),
            base_url="http://agentobs.test",
        ) as client:
            recent = await client.get(
                "/agent-observability/runs",
                headers=headers,
            )
            exact_run = await client.get(
                "/agent-observability/runs",
                headers=headers,
                params={"run_id": run_id},
            )
            exact_attempt = await client.get(
                "/agent-observability/runs",
                headers=headers,
                params={"attempt_id": attempt_id},
            )

        assert recent.status_code == 200, recent.text
        assert all(item["run_id"] != run_id for item in recent.json()["items"])
        assert exact_run.status_code == 200, exact_run.text
        assert [item["run_id"] for item in exact_run.json()["items"]] == [
            run_id,
        ]
        assert exact_attempt.status_code == 200, exact_attempt.text
        assert [item["run_id"] for item in exact_attempt.json()["items"]] == [
            run_id,
        ]
    finally:
        await connection.close()
