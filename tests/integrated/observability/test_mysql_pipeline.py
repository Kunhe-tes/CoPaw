# -*- coding: utf-8 -*-
"""Real MySQL contract test; point only at a disposable *_test database."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from io import StringIO
from uuid import uuid4

import pytest
import httpx
from fastapi import FastAPI, Request

from swe.database import DatabaseConfig, DatabaseConnection
from swe.observability import Observability, Scope, bind_context
from swe.observability.emitter import JsonlEmitter
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
            "Agent observability integration DB name must end in _test",
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
) -> dict:
    occurred = occurred_at.isoformat(timespec="microseconds").replace(
        "+00:00",
        "Z",
    )
    started = started_at.isoformat(timespec="microseconds").replace(
        "+00:00",
        "Z",
    )
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
                "ended_at": ended_at.isoformat(
                    timespec="microseconds",
                ).replace(
                    "+00:00",
                    "Z",
                ),
                "status": status,
                "terminal_fact_source": "business_settlement",
                "metrics": {"duration_us": 1234},
            }
            if ended_at
            else {"status": status}
        ),
    }


async def _verify_partial_run_ordering(store, ingest, started, ended):
    run_id = str(uuid4())
    running_at = started + timedelta(milliseconds=500)
    running_ingest_id = await ingest(
        _event(
            run_id=run_id,
            event_name="run.state",
            phase="running",
            status="running",
            occurred_at=running_at,
            started_at=started,
            ended_at=None,
        ),
    )
    late_accepted_ingest_id = await ingest(
        _event(
            run_id=run_id,
            event_name="run.accepted",
            phase="accepted",
            status="accepted",
            occurred_at=started - timedelta(seconds=1),
            started_at=started,
            ended_at=None,
        ),
    )
    rows = await store.list_runs(
        service_unit_id="swe",
        source_ids=["agentobs-integration"],
        limit=10,
        start_at=started - timedelta(seconds=1),
        end_at=ended + timedelta(seconds=1),
    )
    projected = next(row for row in rows if row["run_id"] == run_id)
    assert projected["status"] == "running"
    assert projected["quality"] == "partial"

    waiting_at = started + timedelta(seconds=1)
    for phase, status, occurred_at in (
        ("waiting-approval", "waiting_approval", waiting_at),
        ("running-late", "running", running_at),
        ("running-same-time", "running", waiting_at),
    ):
        await ingest(
            _event(
                run_id=run_id,
                event_name="run.state",
                phase=phase,
                status=status,
                occurred_at=occurred_at,
                started_at=started,
                ended_at=None,
            ),
        )
    rows = await store.list_runs(
        service_unit_id="swe",
        source_ids=["agentobs-integration"],
        limit=10,
        start_at=started - timedelta(seconds=1),
        end_at=ended + timedelta(seconds=1),
    )
    projected = next(row for row in rows if row["run_id"] == run_id)
    assert projected["status"] == "waiting_approval"
    assert projected["quality"] == "partial"

    await ingest(
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
    rows = await store.list_runs(
        service_unit_id="swe",
        source_ids=["agentobs-integration"],
        limit=10,
        start_at=started - timedelta(seconds=1),
        end_at=ended + timedelta(seconds=1),
    )
    projected = next(row for row in rows if row["run_id"] == run_id)
    assert projected["status"] == "succeeded"
    assert projected["quality"] == "observed"
    return running_ingest_id, late_accepted_ingest_id


@pytest.mark.asyncio
async def test_manual_inbox_to_mysql_projection_and_authorized_run_list(
    monkeypatch,
):
    monkeypatch.setenv(
        "SWE_AGENTOBS_CURSOR_SECRET",
        "integration-cursor-secret-at-least-32",
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
        running_ingest_id, late_accepted_ingest_id = (
            await _verify_partial_run_ordering(
                store,
                ingest,
                started,
                ended,
            )
        )

        partial_span_run_id = str(uuid4())
        partial_span_id = str(uuid4())
        partial_span = _event(
            run_id=partial_span_run_id,
            event_name="span.started",
            phase="started",
            status="running",
            occurred_at=started,
            started_at=started,
            ended_at=None,
        )
        partial_span.update(
            {
                "entity_kind": "span",
                "entity_id": partial_span_id,
                "obs_span_id": partial_span_id,
                "span_type": "Agent",
                "operation": "execute",
                "kind": "SERVER",
                "name": "agent.execute",
            },
        )
        await ingest(partial_span)
        partial_span_rows = await store.list_spans(
            run_id=partial_span_run_id,
        )
        assert len(partial_span_rows) == 1
        assert partial_span_rows[0]["quality"] == "partial"
        assert partial_span_rows[0]["ended_at"] is None

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
            transport=httpx.ASGITransport(app=api),
            base_url="http://agentobs.test",
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
            next(
                item
                for item in response.json()["items"]
                if item["run_id"] == run_id
            )["status"]
            == "succeeded"
        )

        async with connection.acquire() as session:
            inbox_rows = await session.fetch_all(
                "SELECT processing_state,payload_text FROM swe_agentobs_inbox "
                "WHERE ingest_id IN (%s,%s,%s,%s,%s) ORDER BY ingest_id",
                (
                    ended_ingest_id,
                    accepted_ingest_id,
                    running_ingest_id,
                    late_accepted_ingest_id,
                    malformed_ingest_id,
                ),
            )
        assert len(inbox_rows) == 5
        assert sum(row["processing_state"] == 1 for row in inbox_rows) == 4
        assert sum(row["processing_state"] == 2 for row in inbox_rows) == 1
        assert all(row["payload_text"] is None for row in inbox_rows)
    finally:
        await connection.close()


def _emit_retry_events():
    sink = StringIO()
    emitter = JsonlEmitter(stream=sink)
    observability = Observability(emitter)
    context = observability.admit_run(
        scope=Scope(
            "swe",
            "agentobs-integration",
            "integration-user",
            "default",
        ),
        enabled=True,
    )
    attempt = observability.start_attempt(context)
    with bind_context(attempt):
        for span_index in range(3):
            span = observability.span(
                "LLM",
                "chat",
                name="model.call",
                kind="CLIENT",
                step_index=span_index + 1,
            )
            assert span is not None
            with span:
                for retry_index in range(12):
                    span.event(
                        "retry",
                        retries=retry_index + 1,
                        loop_count=12,
                    )
    assert emitter.close(timeout=1) == 0
    return context.obs_run_id, [
        json.loads(line) for line in sink.getvalue().splitlines()
    ]


async def _assert_events_projected(connection, run_id, records):
    async with connection.acquire() as session:
        projected_rows = await session.fetch_all(
            "SELECT event_id FROM swe_agentobs_events WHERE run_id=%s",
            (run_id,),
        )
        inbox_rows = await session.fetch_all(
            "SELECT event_id,processing_state,reason_code "
            "FROM swe_agentobs_inbox WHERE event_id IN ("
            + ",".join(["%s"] * len(records))
            + ")",
            tuple(record["event_id"] for record in records),
        )
    projected_ids = {row["event_id"] for row in projected_rows}
    inbox_by_id = {row["event_id"]: row for row in inbox_rows}
    missing_records = [
        record for record in records if record["event_id"] not in projected_ids
    ]
    assert not missing_records, [
        (
            record["event_name"],
            inbox_by_id.get(record["event_id"], {}).get("processing_state"),
            inbox_by_id.get(record["event_id"], {}).get("reason_code"),
        )
        for record in missing_records
    ]
    assert len(inbox_rows) == len(records)


async def _read_span_pages(client, run_id):
    spans = []
    cursor = None
    for _ in range(4):
        response = await client.get(
            f"/agent-observability/runs/{run_id}",
            headers={
                "X-User-Role": "manager",
                "X-Source-Id": "agentobs-integration",
            },
            params={
                "span_limit": 2,
                **({"span_cursor": cursor} if cursor else {}),
            },
        )
        assert response.status_code == 200, response.text
        page = response.json()
        spans.extend(page["spans"])
        cursor = page["spans_next_cursor"]
        if cursor is None:
            break
    return spans


@pytest.mark.asyncio
async def test_mysql_event_api_pages_more_than_one_event_array(monkeypatch):
    monkeypatch.setenv(
        "SWE_AGENTOBS_CURSOR_SECRET",
        "integration-cursor-secret-at-least-32",
    )
    connection = DatabaseConnection(_test_db_config())
    await connection.connect()
    try:
        store = ObservabilityStore(connection)
        assert (await store.readiness())["ready"]
        run_id, records = _emit_retry_events()
        async with connection.transaction() as session:
            for record in records:
                await session.insert(
                    "INSERT INTO swe_agentobs_inbox (payload_text) VALUES (%s)",
                    (json.dumps(record, separators=(",", ":")),),
                )
        projector = InboxProjector(store, poll_seconds=0.01)
        while await projector.project_batch():
            pass
        await _assert_events_projected(connection, run_id, records)

        api = FastAPI()
        api.state.agent_observability_store = store

        @api.middleware("http")
        async def bind_source(request: Request, call_next):
            request.state.source_id = request.headers.get("X-Source-Id")
            return await call_next(request)

        api.include_router(observability_router)
        pages = []
        cursor = None
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api),
            base_url="http://agentobs.test",
        ) as client:
            monkeypatch.delenv("SWE_AGENTOBS_CURSOR_SECRET")
            unpaged = await client.get(
                f"/agent-observability/runs/{run_id}",
                headers={
                    "X-User-Role": "manager",
                    "X-Source-Id": "agentobs-integration",
                },
                params={"span_limit": 10},
            )
            assert unpaged.status_code == 200, unpaged.text
            assert unpaged.json()["spans_next_cursor"] is None
            monkeypatch.setenv(
                "SWE_AGENTOBS_CURSOR_SECRET",
                "integration-cursor-secret-at-least-32",
            )
            for _ in range(10):
                response = await client.get(
                    f"/agent-observability/runs/{run_id}/events",
                    headers={
                        "X-User-Role": "manager",
                        "X-Source-Id": "agentobs-integration",
                    },
                    params={
                        "limit": 17,
                        **({"cursor": cursor} if cursor else {}),
                    },
                )
                assert response.status_code == 200, response.text
                page = response.json()
                pages.extend(page["items"])
                cursor = page["next_cursor"]
                if cursor is None:
                    break
            span_pages = await _read_span_pages(client, run_id)
            hidden = await client.get(
                f"/agent-observability/runs/{run_id}/events",
                headers={
                    "X-User-Role": "manager",
                    "X-Source-Id": "different-source",
                },
            )
            forbidden = await client.get(
                f"/agent-observability/runs/{run_id}/events",
                headers={"X-User-Role": "user"},
            )
        assert len({item["event_id"] for item in pages}) == len(pages)
        assert len(pages) == len(records)
        assert (
            sum(
                item["metadata"].get("event_kind") == "retry" for item in pages
            )
            == 36
        )
        span_ids = {
            record["entity_id"]
            for record in records
            if record["event_name"] == "span.started"
        }
        assert all(
            item["entity_id"] in span_ids
            for item in pages
            if item["event_name"] == "span.event"
        )
        assert len(span_pages) == 3
        assert len({span["span_id"] for span in span_pages}) == 3
        assert hidden.status_code == 404
        assert forbidden.status_code == 403
    finally:
        await connection.close()
