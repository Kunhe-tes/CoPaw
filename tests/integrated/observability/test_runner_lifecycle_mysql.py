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


async def _assert_projected_run_available(
    connection,
    records,
    *,
    expected_status="succeeded",
) -> None:
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
    run_end_event = next(
        (record for record in records if record["event_name"] == "run.ended"),
        None,
    )
    window_end = (
        run_end_event["ended_at"]
        if run_end_event
        else records[-1]["occurred_at"]
    )
    rows = await store.list_runs(
        service_unit_id="swe",
        source_ids=["runner-integration"],
        limit=20,
        start_at=datetime.fromisoformat(
            records[0]["run_started_at"].replace("Z", "+00:00"),
        ),
        end_at=datetime.fromisoformat(window_end.replace("Z", "+00:00")),
    )
    row = next(item for item in rows if item["run_id"] == run_id)
    assert row["status"] == expected_status
    if run_end_event:
        assert row["quality"] == "observed"
        assert row["ended_at"] is not None
        assert row["duration_us"] > 0
        expected_run_end = datetime.fromisoformat(
            run_end_event["ended_at"].replace("Z", "+00:00"),
        ).replace(tzinfo=None)
        assert row["ended_at"] == expected_run_end
    else:
        assert row["quality"] == "partial"
        assert row["ended_at"] is None
        assert row["duration_us"] is None

    attempt_id = next(
        record["obs_attempt_id"]
        for record in records
        if record["event_name"] == "attempt.ended"
    )
    async with connection.acquire() as session:
        attempts = await session.fetch_all(
            "SELECT ended_at,status FROM swe_agentobs_attempts WHERE attempt_id = %s",
            (attempt_id,),
        )
    assert len(attempts) == 1
    assert attempts[0]["status"] == expected_status
    expected_attempt_end = datetime.fromisoformat(
        next(
            record["ended_at"]
            for record in records
            if record["event_name"] == "attempt.ended"
        ).replace("Z", "+00:00"),
    ).replace(tzinfo=None)
    assert attempts[0]["ended_at"] == expected_attempt_end
    if run_end_event:
        assert attempts[0]["ended_at"] < row["ended_at"]

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
                "end": window_end,
            },
        )
    assert response.status_code == 200
    api_row = next(
        item for item in response.json()["items"] if item["run_id"] == run_id
    )
    assert api_row["status"] == expected_status


def _make_runner_case(
    coordinator_enabled: bool,
    expert_pending: bool | None,
):
    from swe.app.answer_turn.models import TurnIdentity, TurnOutcome
    from swe.app.runner.runner import AgentRunner
    from swe.app.runner.query_execution.admission import stream_admission
    from swe.app.runner.expert_main_runtime import (
        EXPERT_MAIN_TOKEN_KEY,
        ExpertMainRegistry,
    )

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
        channel_meta={
            "answer_turn_identity": identity,
            "chat_id": chat_id,
            "source_id": "runner-integration",
        },
        execution_origin="interactive",
    )
    expert_registry = None
    if expert_pending is not None:
        expert_registry = ExpertMainRegistry()
        token = expert_registry.register(
            SimpleNamespace(),
            chat_id=chat_id,
            user_id="user-a",
            source_id="runner-integration",
            turn_id=question_id,
        )
        request.channel_meta[EXPERT_MAIN_TOKEN_KEY] = token
        lease = expert_registry.get(request)
        lease.agent = SimpleNamespace(
            _tool_guard_pending_info=(
                {"request_id": "approval-1"} if expert_pending else None
            ),
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
        execution.state["turn_states"][question_id] = {"status": "completed"}
        yield Msg("assistant", "private answer body", "assistant"), True

    owner = AgentRunner.__new__(AgentRunner)
    owner.agent_id = "default"
    owner.tenant_id = "tenant-a"
    owner._workspace = SimpleNamespace(conversation_storage=None)
    owner.session = Session()
    owner._answer_turn_coordinator = object() if coordinator_enabled else None
    owner._answer_turn_runtimes = {identity: (None, execution)}
    owner._answer_turn_locations = {}
    owner._agent_observability_contexts = {}
    if expert_registry is not None:
        owner._expert_main_executions = expert_registry
        owner._get_expert_main_execution = (
            AgentRunner._get_expert_main_execution.__get__(owner, AgentRunner)
        )
    else:
        owner._get_expert_main_execution = lambda _request: None
    owner._prepare_query_preflight = preflight
    owner._stream_query_after_preflight = successful_execution
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
@pytest.mark.parametrize(
    "coordinator_enabled,expert_pending,expected_status",
    [
        pytest.param(True, None, "succeeded", id="coordinator-settlement"),
        pytest.param(False, None, "succeeded", id="legacy-settlement"),
        pytest.param(True, False, "succeeded", id="expert-main-success"),
        pytest.param(
            True,
            True,
            "waiting_approval",
            id="expert-main-waiting-approval",
        ),
    ],
)
async def test_runner_admission_settlement_emits_and_projects_one_run(
    monkeypatch,
    coordinator_enabled,
    expert_pending,
    expected_status,
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
    ) = _make_runner_case(coordinator_enabled, expert_pending)

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
        if coordinator_enabled:
            await AgentRunner.persist_outcome(
                owner,
                TurnOutcome.completed(identity),
            )
            assert not owner._agent_observability_contexts

        assert emitter.close(timeout=1) == 0
        records = [json.loads(line) for line in sink.getvalue().splitlines()]
        event_names = [record["event_name"] for record in records]
        assert event_names[:3] == [
            "run.accepted",
            "run.state",
            "attempt.started",
        ]
        if expected_status == "waiting_approval":
            assert event_names[-1] == "attempt.ended"
            assert "run.ended" not in event_names
            assert any(
                record.get("status") == "waiting_approval"
                for record in records
            )
        else:
            assert event_names[-2:] == ["attempt.ended", "run.ended"]
        assert all(
            _validate_payload(json.dumps(record, ensure_ascii=False))
            for record in records
        )
        assert all(
            "private question body" not in line
            and "private answer body" not in line
            for line in sink.getvalue().splitlines()
        )

        await _assert_projected_run_available(
            connection,
            records,
            expected_status=expected_status,
        )
    finally:
        emitter.close(timeout=1)
        await connection.close()
