# -*- coding: utf-8 -*-
"""Real MySQL contract test; point only at a disposable *_test database."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import httpx
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
        raise RuntimeError("Agent observability integration DB name must end in _test")
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
) -> dict:
    occurred = occurred_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
    started = started_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return {
        "schema_version": 1,
        "event_id": str(uuid4()),
        "event_name": event_name,
        "occurred_at": occurred,
        "producer_id": f"mysql-test:{uuid4()}",
        "obs_run_id": run_id,
        "run_started_at": started,
        "capture_enabled": True,
        "entity_kind": "run",
        "entity_id": run_id,
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
        },
        "started_at": started,
        **(
            {
                "ended_at": ended_at.isoformat(timespec="microseconds").replace(
                    "+00:00", "Z",
                ),
                "status": status,
                "terminal_fact_source": "business_settlement",
                "metrics": {"duration_us": 1234},
            }
            if ended_at
            else {"status": status}
        ),
    }


@pytest.mark.asyncio
async def test_manual_inbox_to_mysql_projection_and_authorized_run_list(monkeypatch):
    monkeypatch.setenv(
        "SWE_AGENTOBS_CURSOR_SECRET", "integration-cursor-secret-at-least-32",
    )
    connection = DatabaseConnection(_test_db_config())
    await connection.connect()
    try:
        store = ObservabilityStore(connection)
        readiness = await store.readiness()
        assert readiness["ready"], readiness

        projector = InboxProjector(store, poll_seconds=0.01)
        now = datetime.now(timezone.utc)
        started = now - timedelta(seconds=3)
        ended = now - timedelta(seconds=1)
        run_id = str(uuid4())

        async def ingest(event: dict) -> int:
            async with connection.transaction() as session:
                ingest_id = await session.insert(
                    "INSERT INTO swe_agentobs_inbox (payload_text) VALUES (%s)",
                    (json.dumps(event, separators=(",", ":")),),
                )
            assert await projector.project_batch() == 1
            return int(ingest_id)

        ended_ingest_id = await ingest(
            _event(
                run_id=run_id,
                event_name="run.ended",
                phase="ended",
                status="succeeded",
                occurred_at=ended,
                started_at=started,
                ended_at=ended,
            ),
        )
        accepted_ingest_id = await ingest(
            _event(
                run_id=run_id,
                event_name="run.accepted",
                phase="accepted",
                status="accepted",
                occurred_at=started,
                started_at=started,
                ended_at=None,
            ),
        )
        malformed_terminal = _event(
            run_id=str(uuid4()),
            event_name="run.ended",
            phase="ended",
            status="failed",
            occurred_at=ended,
            started_at=started,
            ended_at=ended,
        )
        malformed_terminal.pop("status")
        malformed_ingest_id = await ingest(malformed_terminal)

        rows = await store.list_runs(
            service_unit_id="swe",
            source_ids=["agentobs-integration"],
            limit=10,
            start_at=started - timedelta(seconds=1),
            end_at=ended + timedelta(seconds=1),
        )
        projected = next(row for row in rows if row["run_id"] == run_id)
        assert projected["status"] == "succeeded"
        assert projected["ended_at"] is not None

        api = FastAPI()
        api.state.agent_observability_store = store

        @api.middleware("http")
        async def bind_test_source(request: Request, call_next):
            request.state.source_id = request.headers.get("X-Source-Id")
            return await call_next(request)

        api.include_router(observability_router)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url="http://agentobs.test",
        ) as client:
            response = await client.get(
                "/agent-observability/runs",
                headers={
                    "X-User-Role": "manager",
                    "X-Source-Id": "agentobs-integration",
                },
                params={
                    "start": (started - timedelta(seconds=1)).isoformat(),
                    "end": (ended + timedelta(seconds=1)).isoformat(),
                },
            )
        assert response.status_code == 200
        assert (
            next(item for item in response.json()["items"] if item["run_id"] == run_id)[
                "status"
            ]
            == "succeeded"
        )

        async with connection.acquire() as session:
            inbox_rows = await session.fetch_all(
                "SELECT processing_state,payload_text FROM swe_agentobs_inbox "
                "WHERE ingest_id IN (%s,%s,%s) ORDER BY ingest_id",
                (ended_ingest_id, accepted_ingest_id, malformed_ingest_id),
            )
        assert len(inbox_rows) == 3
        assert sum(row["processing_state"] == 1 for row in inbox_rows) == 2
        assert sum(row["processing_state"] == 2 for row in inbox_rows) == 1
        assert all(row["payload_text"] is None for row in inbox_rows)
    finally:
        await connection.close()
