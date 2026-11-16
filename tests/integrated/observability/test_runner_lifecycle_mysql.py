# -*- coding: utf-8 -*-
"""Runner admission to authorized MySQL projection integration contract."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from io import StringIO
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from agentscope.message import Msg
from fastapi import FastAPI, Request

from swe.database import DatabaseConfig, DatabaseConnection
from swe.observability.emitter import JsonlEmitter
from swe.observability.instrumentation import Observability
from swe.observability.projector import InboxProjector, _validate_payload
from swe.observability.query import router as observability_router
from swe.observability.store import ObservabilityStore

_DB_HOST = os.getenv("SWE_AGENTOBS_TEST_DB_HOST")
pytestmark = pytest.mark.skipif(
    not _DB_HOST,
    reason="set SWE_AGENTOBS_TEST_DB_HOST to a disposable MySQL *_test database",
)


def _config() -> DatabaseConfig:
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


async def _assert_projected_run_available(connection, records) -> None:
    store = ObservabilityStore(connection)
    projector = InboxProjector(store, poll_seconds=0.01)
    async with connection.transaction() as session:
        for record in records:
            await session.insert(
                "INSERT INTO swe_agentobs_inbox (payload_text) VALUES (%s)",
                (json.dumps(record, separators=(",", ":")),),
            )
    while await projector.project_batch():
        pass
    run_id = records[0]["obs_run_id"]
    rows = await store.list_runs(
        service_unit_id="swe",
        source_ids=["runner-integration"],
        limit=20,
        start_at=datetime.fromisoformat(
            records[0]["run_started_at"].replace("Z", "+00:00"),
        ),
        end_at=datetime.fromisoformat(
            records[-1]["ended_at"].replace("Z", "+00:00"),
        ),
    )
    row = next(item for item in rows if item["run_id"] == run_id)
    assert row["status"] == "succeeded"
    assert row["quality"] == "observed"

    api = FastAPI()
    api.state.agent_observability_store = store

    @api.middleware("http")
    async def bind_source(http_request: Request, call_next):
        http_request.state.source_id = "runner-integration"
        return await call_next(http_request)

    api.include_router(observability_router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api),
        base_url="http://runner.test",
    ) as client:
        response = await client.get(
            "/agent-observability/runs",
            headers={"X-User-Role": "manager"},
            params={
                "start": records[0]["run_started_at"],
                "end": records[-1]["ended_at"],
            },
        )
    assert response.status_code == 200
    assert any(item["run_id"] == run_id for item in response.json()["items"])


def _make_runner_case():
    from swe.app.answer_turn.models import TurnIdentity, TurnOutcome
    from swe.app.runner.runner import AgentRunner
    from swe.app.runner.query_execution.admission import stream_admission

    class SessionExecution:
        def __init__(self):
            self.state = {"turn_states": {}}
            self.is_active = True

        async def hydrate_turn(self, _turn_id):
            return None

        def mark_state_dirty(self):
            return None

        async def commit_state(self, _state):
            return None

    execution = SessionExecution()

    class Session:
        @asynccontextmanager
        async def execution(self, _session_id, *, user_id, timeout_seconds):
            assert user_id == "user-a"
            assert timeout_seconds == 5.0
            yield execution

    question_id = str(uuid4())
    chat_id = str(uuid4())
    identity = TurnIdentity.create(chat_id=chat_id, msgid=question_id)
    request = SimpleNamespace(
        channel="console",
        session_id="session-a",
        user_id="user-a",
        source_id="runner-integration",
        channel_meta={"answer_turn_identity": identity, "chat_id": chat_id},
        execution_origin="interactive",
    )
    question = Msg("user", "private question body", "user")
    question.id = question_id

    async def preflight(**_kwargs):
        return SimpleNamespace(
            response=None,
            cleanup_denied_memory=False,
            approval_consumed=False,
        )

    async def successful_execution(_msgs, **_kwargs):
        yield Msg("assistant", "private answer body", "assistant"), True

    owner = AgentRunner.__new__(AgentRunner)
    owner.agent_id = "default"
    owner.tenant_id = "tenant-a"
    owner._workspace = SimpleNamespace(conversation_storage=None)
    owner.session = Session()
    owner._answer_turn_coordinator = object()
    owner._answer_turn_runtimes = {identity: (None, execution)}
    owner._answer_turn_locations = {}
    owner._agent_observability_contexts = {}
    owner._prepare_query_preflight = preflight
    owner._stream_query_after_preflight = successful_execution
    owner._get_expert_main_execution = lambda _request: None
    owner._answer_turn_identity = AgentRunner._answer_turn_identity
    return (
        AgentRunner,
        TurnOutcome,
        stream_admission,
        owner,
        request,
        question,
        identity,
    )


@pytest.mark.asyncio
async def test_runner_admission_settlement_emits_and_projects_one_run(
    monkeypatch,
):
    monkeypatch.setenv("SWE_ALLOW_MISSING_TRACE_SDK", "true")
    monkeypatch.setenv("SWE_AGENTOBS_ENABLED", "true")
    monkeypatch.setenv(
        "SWE_AGENTOBS_CURSOR_SECRET",
        "runner-integration-secret-at-least-32",
    )

    from swe.observability import runner_lifecycle

    sink = StringIO()
    emitter = JsonlEmitter(stream=sink)
    monkeypatch.setattr(
        runner_lifecycle,
        "_OBSERVABILITY",
        Observability(emitter),
    )
    connection = DatabaseConnection(_config())
    await connection.connect()

    (
        AgentRunner,
        TurnOutcome,
        stream_admission,
        owner,
        request,
        question,
        identity,
    ) = _make_runner_case()

    try:
        frames = [
            frame
            async for frame in stream_admission(
                owner,
                [question],
                request=request,
                query="private question body",
                session_id="session-a",
                user_id="user-a",
            )
        ]
        assert len(frames) == 1 and frames[0][1] is True
        await AgentRunner.persist_outcome(
            owner,
            TurnOutcome.completed(identity),
        )
        assert not owner._agent_observability_contexts

        assert emitter.close(timeout=1) == 0
        records = [json.loads(line) for line in sink.getvalue().splitlines()]
        assert [record["event_name"] for record in records] == [
            "run.accepted",
            "run.state",
            "attempt.started",
            "attempt.ended",
            "run.ended",
        ]
        assert all(
            _validate_payload(json.dumps(record, ensure_ascii=False))
            for record in records
        )
        assert all(
            "private question body" not in line
            and "private answer body" not in line
            for line in sink.getvalue().splitlines()
        )

        await _assert_projected_run_available(connection, records)
    finally:
        emitter.close(timeout=1)
        await connection.close()
