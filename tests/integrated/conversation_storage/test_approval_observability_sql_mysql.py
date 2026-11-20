# -*- coding: utf-8 -*-
"""SQL-backed approval continuation emits one observable Run."""

from __future__ import annotations

import asyncio
import json
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
from agentscope.message import Msg
from fastapi import FastAPI, Request
import pytest

from swe.app.approvals.external import (
    ExternalApprovalDecision,
    submit_external_approval_decision,
)
from swe.app.approvals.service import ApprovalService
from swe.app.approvals.store import ApprovalAuditStore
from swe.app.conversation_storage.factory import WorkspaceConversationStorage
from swe.app.conversation_storage.runner_integration import (
    stream_indexed_query,
)
from swe.app.runner.query_contracts import _QueryPreflight
from swe.app.runner.runner import AgentRunner
from swe.config.context import get_current_effective_tenant_id, tenant_context
from swe.database import DatabaseConnection
from swe.observability import Observability, Scope, bind_context
from swe.observability.emitter import JsonlEmitter
from swe.observability import runner_lifecycle
from swe.observability.projector import InboxProjector
from swe.observability.query import router as observability_router
from swe.observability.store import ObservabilityStore
from tests.integrated.conversation_storage.conftest import apply_sql_script
from tests.integrated.conversation_storage.test_execution_mysql import (
    identity,
    seed,
)

_OBSERVABILITY_DDL = (
    Path(__file__).parents[3]
    / ".scratch"
    / "agent-observability"
    / "schema-draft.sql"
)


async def _create_waiting_approval(database, tmp_path, monkeypatch):
    await seed(database)
    await apply_sql_script(database, _OBSERVABILITY_DDL)
    monkeypatch.setenv("SWE_AGENTOBS_ENABLED", "true")
    monkeypatch.setenv("SWE_SERVICE_UNIT_ID", "schema-test-service")
    monkeypatch.setenv(
        "SWE_AGENTOBS_CURSOR_SECRET",
        "sql-approval-cursor-secret-at-least-32",
    )
    scope = identity().scope
    storage = WorkspaceConversationStorage(
        database,
        scope,
        tmp_path,
        cursor_secret=b"sql-approval-storage-test",
    )
    output = StringIO()
    emitter = JsonlEmitter(stream=output)
    observer = Observability(emitter)
    monkeypatch.setattr(runner_lifecycle, "_OBSERVABILITY", observer)
    with tenant_context(tenant_id="tenant", source_id="source"):
        effective_tenant_id = get_current_effective_tenant_id()
    assert effective_tenant_id is not None
    context = observer.admit_run(
        scope=Scope(
            scope.service_unit_id,
            scope.source_id,
            effective_tenant_id,
            scope.agent_id,
        ),
        business_ref={
            "chat_id": "one",
            "root_question_msgid": "original-question",
            "session_id": "session",
        },
        enabled=True,
    )
    waiting_attempt = observer.start_attempt(context)
    service = ApprovalService()
    with tenant_context(tenant_id="tenant", source_id="source"):
        with bind_context(waiting_attempt):
            carrier = runner_lifecycle.approval_context_carrier()
        pending = await service.create_pending(
            session_id="session",
            user_id="alice",
            channel="console",
            tool_name="execute_shell_command",
            result=SimpleNamespace(findings=[], findings_count=0),
            extra={
                "approval_kind": "tool_guard",
                "agent_id": "agent",
                "tenant_id": effective_tenant_id,
                "source_id": "source",
                "chat_id": "one",
                "msgid": "original-question",
                "agent_observability_context": carrier,
                "tool_call": {
                    "id": "call-sql-approval",
                    "name": "execute_shell_command",
                    "input": {"command": "echo safe"},
                },
            },
        )
        with bind_context(waiting_attempt):
            runner_lifecycle.record_approval_requested(
                context,
                pending.request_id,
                started_at=pending.created_at,
            )
        runner_lifecycle.finish_query_run(
            context,
            waiting_attempt,
            "completed",
            waiting_for_approval=True,
        )
    return (
        storage,
        output,
        emitter,
        context,
        waiting_attempt,
        service,
        pending,
        effective_tenant_id,
    )


def _runner_for_approval(
    service,
    effective_tenant_id,
    monkeypatch,
    *,
    create_followup=False,
):
    monkeypatch.setattr(
        "swe.app.approvals.service._approval_service",
        service,
    )
    runner = AgentRunner()
    runner.agent_id = "agent"
    runner.tenant_id = effective_tenant_id
    runner._APPROVAL_TIMEOUT_SECONDS = 60
    runner._get_or_create_chat = AsyncMock(
        return_value=SimpleNamespace(id="one"),
    )

    async def prepare(
        *,
        session_id,
        user_id,
        query,
        request,
        session_execution,
    ):
        response, consumed, approved_tool_call = (
            await runner._resolve_pending_approval(
                session_id,
                query,
                request=request,
            )
        )
        return _QueryPreflight(
            response=response,
            cleanup_denied_memory=response is not None,
            approval_consumed=consumed,
            approved_tool_call=approved_tool_call,
        )

    async def resume(_messages, **kwargs):
        assert (
            kwargs["preflight"]
            .approved_tool_call["id"]
            .startswith(
                "call-sql-approval",
            )
        )
        if create_followup and not getattr(runner, "_followup_created", False):
            execution = kwargs["session_execution"]
            with bind_context(runner_lifecycle.current_context()):
                carrier = runner_lifecycle.approval_context_carrier()
            with tenant_context(tenant_id="tenant", source_id="source"):
                followup = await service.create_pending(
                    session_id="session",
                    user_id="alice",
                    channel="console",
                    tool_name="execute_shell_command",
                    result=SimpleNamespace(findings=[], findings_count=0),
                    extra={
                        "approval_kind": "tool_guard",
                        "agent_id": "agent",
                        "tenant_id": effective_tenant_id,
                        "source_id": "source",
                        "chat_id": "one",
                        "msgid": "original-question",
                        "agent_observability_context": carrier,
                        "tool_call": {
                            "id": "call-sql-approval-followup",
                            "name": "execute_shell_command",
                            "input": {"command": "echo again"},
                        },
                    },
                )
            execution.indexed_query.runtime = SimpleNamespace(
                agent=SimpleNamespace(
                    _tool_guard_pending_info={
                        "request_id": followup.request_id,
                    },
                    state_dict=lambda: {},
                ),
            )
            runner._followup_created = True
        yield Msg("assistant", "tool resumed", "assistant"), True

    runner._prepare_query_preflight = prepare
    runner._cleanup_denied_session_memory = AsyncMock()
    runner._stream_query_after_preflight = resume
    runner._answer_turn_identity = lambda _request: None
    runner._answer_turn_runtimes = {}
    return runner


async def _submit_approval(runner, storage, query, request):
    message = Msg("user", query, "user")
    message.id = "approval-command-" + uuid4().hex
    with tenant_context(tenant_id="tenant", source_id="source"):
        return [
            frame
            async for frame in stream_indexed_query(
                runner,
                storage,
                [message],
                request=request,
                query=query,
            )
        ]


async def _project_and_fetch_detail(database, records, run_id):
    store = ObservabilityStore(database)
    async with database.transaction() as session:
        for record in records:
            await session.insert(
                "INSERT INTO swe_agentobs_inbox (payload_text) VALUES (%s)",
                (json.dumps(record, separators=(",", ":")),),
            )
    projector = InboxProjector(store, poll_seconds=0.01)
    while await projector.project_batch():
        pass
    assert (
        await store.get_run(
            service_unit_id="schema-test-service",
            run_id=run_id,
            source_ids=["source"],
        )
        is not None
    )
    api = FastAPI()
    api.state.agent_observability_store = store

    @api.middleware("http")
    async def bind_source(api_request: Request, call_next):
        api_request.state.source_id = "source"
        api_request.state.effective_tenant_id = records[0]["scope"][
            "tenant_id"
        ]
        return await call_next(api_request)

    api.include_router(observability_router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api),
        base_url="http://sql-approval.test",
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
async def test_same_message_replay_repairs_approval_audit(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    from swe.app.approvals.store import ApprovalAuditStore

    database = conversation_test_database
    storage, _, emitter, _, _, service, pending, tenant = (
        await _create_waiting_approval(database, tmp_path, monkeypatch)
    )
    audit = ApprovalAuditStore(database)
    await audit.initialize()

    class FlakyAudit:
        failed = False

        async def upsert_request(self, *args, **kwargs):
            await audit.upsert_request(*args, **kwargs)

        async def add_event(self, pending, event_type, **kwargs):
            if event_type == "resolved" and not self.failed:
                self.failed = True
                raise OSError("audit unavailable")
            await audit.add_event(pending, event_type, **kwargs)

    service.set_store(FlakyAudit())
    runner = _runner_for_approval(service, tenant, monkeypatch)
    text = f"/deny {pending.request_id}"
    question = Msg("user", text, "user")
    question.id = "approval-command-" + uuid4().hex
    request = SimpleNamespace(
        channel="console",
        session_id="session",
        user_id="alice",
        source_id="source",
        channel_meta={"source_id": "source", "chat_id": "one"},
    )
    with tenant_context(tenant_id="tenant", source_id="source"):
        for _ in range(2):
            async for _frame in stream_indexed_query(
                runner,
                storage,
                [question],
                request=request,
                query=text,
            ):
                pass
    events = await database.fetch_all(
        "SELECT status FROM swe_tool_approval_events "
        "WHERE request_id=%s AND event_type='resolved'",
        (pending.request_id,),
    )
    assert [event["status"] for event in events] == ["denied"]
    assert pending.status == "denied"
    assert runner._cleanup_denied_session_memory.await_count == 1
    assert emitter.close(timeout=1) == 0


@pytest.mark.asyncio
async def test_sql_waiting_approval_cancel_settles_original_run(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    database = conversation_test_database
    (
        _storage,
        output,
        emitter,
        root_context,
        waiting_attempt,
        _service,
        pending,
        _tenant,
    ) = await _create_waiting_approval(database, tmp_path, monkeypatch)

    owner = SimpleNamespace(_agent_observability_contexts={})
    identity = object()
    runner_lifecycle.defer_query_run_settlement(
        owner,
        identity,
        root_context,
        waiting_attempt,
        waiting_for_approval=True,
    )
    runner_lifecycle.update_deferred_query_run_approval(
        owner,
        identity,
        waiting_for_approval=False,
        clear_attempt=True,
    )
    runner_lifecycle.finish_deferred_query_run(owner, identity, "cancelled")
    assert emitter.close(timeout=1) == 0
    records = [json.loads(line) for line in output.getvalue().splitlines()]
    assert sum(event["event_name"] == "run.ended" for event in records) == 1
    assert not any(
        event["event_name"] == "approval.resolved" for event in records
    )
    detail, events = await _project_and_fetch_detail(
        database,
        records,
        root_context.obs_run_id,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["run"]["status"] == "cancelled"
    assert [item["status"] for item in detail.json()["attempts"]] == [
        "waiting_approval",
    ]
    assert not any(
        item["event_name"] == "approval.resolved"
        for item in events.json()["items"]
    )
    assert pending.status == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "query",
        "decision",
        "expected_run_status",
        "expected_attempts",
        "force_timeout",
    ),
    [
        ("/deny", "denied", "rejected", ["waiting_approval"], False),
        (
            "/daemon approve",
            "approved",
            "succeeded",
            ["waiting_approval", "succeeded"],
            False,
        ),
        ("/deny", "timeout", "timed_out", ["waiting_approval"], True),
    ],
)
async def test_sql_approval_resolution_projects_original_run(
    conversation_test_database,
    tmp_path,
    monkeypatch,
    query,
    decision,
    expected_run_status,
    expected_attempts,
    force_timeout,
):
    database = conversation_test_database
    (
        storage,
        output,
        emitter,
        root_context,
        waiting_attempt,
        service,
        pending,
        effective_tenant_id,
    ) = await _create_waiting_approval(database, tmp_path, monkeypatch)
    runner = _runner_for_approval(service, effective_tenant_id, monkeypatch)
    if force_timeout:
        runner._APPROVAL_TIMEOUT_SECONDS = -1
    question = Msg("user", query, "user")
    question.id = "approval-command-" + uuid4().hex
    request = SimpleNamespace(
        channel="console",
        session_id="session",
        user_id="alice",
        source_id="source",
        channel_meta={"source_id": "source", "chat_id": "one"},
    )

    with tenant_context(tenant_id="tenant", source_id="source"):
        frames = [
            frame
            async for frame in stream_indexed_query(
                runner,
                storage,
                [question],
                request=request,
                query=query,
            )
        ]
    assert frames
    assert pending.status == decision
    assert emitter.close(timeout=1) == 0

    records = [json.loads(line) for line in output.getvalue().splitlines()]
    assert {event["obs_run_id"] for event in records} == {
        root_context.obs_run_id,
    }
    assert sum(event["event_name"] == "run.accepted" for event in records) == 1
    assert sum(event["event_name"] == "run.ended" for event in records) == 1
    if decision == "approved":
        attempt_starts = [
            event
            for event in records
            if event["event_name"] == "attempt.started"
        ]
        assert len(attempt_starts) == 2
        resumed = next(
            event
            for event in attempt_starts
            if event.get("predecessor_attempt_id") is not None
        )
        assert resumed["predecessor_attempt_id"] == (
            waiting_attempt.obs_attempt_id
        )

    detail, events = await _project_and_fetch_detail(
        database,
        records,
        root_context.obs_run_id,
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["run"]["status"] == expected_run_status
    assert [attempt["status"] for attempt in body["attempts"]] == (
        expected_attempts
    )
    resolved_event = next(
        item
        for item in events.json()["items"]
        if item["event_name"] == "approval.resolved"
    )
    expected_decision = "timed_out" if force_timeout else decision
    assert resolved_event["metadata"]["decision"] == expected_decision
    assert resolved_event["attempt_id"] == waiting_attempt.obs_attempt_id


@pytest.mark.asyncio
async def test_sql_consecutive_approvals_keep_one_run_and_attempt_chain(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    database = conversation_test_database
    (
        storage,
        output,
        emitter,
        root_context,
        waiting_attempt,
        service,
        first_pending,
        effective_tenant_id,
    ) = await _create_waiting_approval(database, tmp_path, monkeypatch)
    runner = _runner_for_approval(
        service,
        effective_tenant_id,
        monkeypatch,
        create_followup=True,
    )
    request = SimpleNamespace(
        channel="console",
        session_id="session",
        user_id="alice",
        source_id="source",
        channel_meta={"source_id": "source", "chat_id": "one"},
    )
    first_frames = await _submit_approval(
        runner,
        storage,
        f"/approve {first_pending.request_id}",
        request,
    )
    with tenant_context(tenant_id="tenant", source_id="source"):
        followup = await service.get_pending_by_session("session")
    assert followup is not None
    second_frames = await _submit_approval(
        runner,
        storage,
        f"/approve {followup.request_id}",
        request,
    )
    assert first_frames and second_frames
    assert first_pending.status == followup.status == "approved"
    assert emitter.close(timeout=1) == 0

    records = [json.loads(line) for line in output.getvalue().splitlines()]
    assert {event["obs_run_id"] for event in records} == {
        root_context.obs_run_id,
    }
    assert sum(event["event_name"] == "run.accepted" for event in records) == 1
    assert sum(event["event_name"] == "run.ended" for event in records) == 1
    attempts = [
        event for event in records if event["event_name"] == "attempt.started"
    ]
    assert len(attempts) == 3
    assert attempts[1]["predecessor_attempt_id"] == (
        waiting_attempt.obs_attempt_id
    )
    assert (
        attempts[2]["predecessor_attempt_id"] == attempts[1]["obs_attempt_id"]
    )

    detail, events = await _project_and_fetch_detail(
        database,
        records,
        root_context.obs_run_id,
    )
    assert detail.status_code == 200, detail.text
    assert [item["status"] for item in detail.json()["attempts"]] == [
        "waiting_approval",
        "waiting_approval",
        "succeeded",
    ]
    resolved_events = [
        item
        for item in events.json()["items"]
        if item["event_name"] == "approval.resolved"
    ]
    assert len(resolved_events) == 2
    assert {item["entity_id"] for item in resolved_events} == {
        first_pending.request_id,
        followup.request_id,
    }
    resolved_attempts = {
        item["entity_id"]: item["attempt_id"] for item in resolved_events
    }
    assert resolved_attempts[first_pending.request_id] == (
        waiting_attempt.obs_attempt_id
    )
    assert (
        resolved_attempts[followup.request_id] == attempts[1]["obs_attempt_id"]
    )


@pytest.mark.asyncio
async def test_external_approval_submission_runs_sql_admission_and_projection(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    database = conversation_test_database
    (
        storage,
        output,
        emitter,
        root_context,
        waiting_attempt,
        service,
        pending,
        effective_tenant_id,
    ) = await _create_waiting_approval(database, tmp_path, monkeypatch)
    audit = ApprovalAuditStore(database)
    await audit.initialize()
    service.set_store(audit)
    await audit.upsert_request(pending)
    await audit.add_event(pending, "created", status="pending")
    monkeypatch.setattr(
        "swe.app.approvals.service._approval_service",
        service,
    )
    runner = _runner_for_approval(service, effective_tenant_id, monkeypatch)
    workspace, coordinator = _external_sql_approval_workspace(
        runner,
        storage,
        pending,
    )

    with tenant_context(tenant_id="tenant", source_id="source"):
        submission = await submit_external_approval_decision(
            workspace=workspace,
            pending=pending,
            decision=ExternalApprovalDecision.APPROVE,
            source_channel="zhaohu",
            source_user_id="operator-1",
            source_message_id="external-message-1",
            source_id="source",
        )
        await coordinator.producer_task
        frames = coordinator.frames

    assert submission.submitted is True
    assert submission.status == "submitted"
    assert coordinator.payload["meta"]["approval_source_channel"] == "zhaohu"
    assert frames
    assert pending.status == "approved"
    audit_events = await database.fetch_all(
        "SELECT event_type,status,actor_channel,actor_user_id "
        "FROM swe_tool_approval_events WHERE request_id=%s ORDER BY event_id",
        (pending.request_id,),
    )
    assert [event["event_type"] for event in audit_events] == [
        "created",
        "decision_submitted",
        "resolved",
    ]
    assert audit_events[1]["actor_channel"] == "zhaohu"
    assert audit_events[1]["actor_user_id"] == "operator-1"
    assert audit_events[2]["status"] == "approved"
    audit_request = await database.fetch_one(
        "SELECT scope_id,tenant_id,source_id,status,source_channel,"
        "source_user_id,source_message_id FROM swe_tool_approval_requests "
        "WHERE request_id=%s",
        (pending.request_id,),
    )
    assert audit_request == {
        "scope_id": pending.scope_id,
        "tenant_id": pending.extra["tenant_id"],
        "source_id": "source",
        "status": "approved",
        "source_channel": "zhaohu",
        "source_user_id": "operator-1",
        "source_message_id": "external-message-1",
    }
    assert emitter.close(timeout=1) == 0

    records = [json.loads(line) for line in output.getvalue().splitlines()]
    assert {event["obs_run_id"] for event in records} == {
        root_context.obs_run_id,
    }
    assert sum(event["event_name"] == "run.ended" for event in records) == 1
    assert (
        sum(event["event_name"] == "attempt.started" for event in records) == 2
    )
    detail, events = await _project_and_fetch_detail(
        database,
        records,
        root_context.obs_run_id,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["run"]["status"] == "succeeded"
    assert [attempt["status"] for attempt in detail.json()["attempts"]] == [
        "waiting_approval",
        "succeeded",
    ]
    resolved = next(
        item
        for item in events.json()["items"]
        if item["event_name"] == "approval.resolved"
    )
    assert resolved["entity_id"] == pending.request_id
    assert resolved["metadata"]["decision"] == "approved"
    assert resolved["attempt_id"] == waiting_attempt.obs_attempt_id


def _external_sql_approval_workspace(runner, storage, pending):
    chat = SimpleNamespace(id="one")

    class ConsoleChannel:
        async def stream_one(self, payload):
            external_submission = pending.extra["external_submission"]
            assert external_submission["source_channel"] == "zhaohu"
            command = payload["content_parts"][0].text
            question = Msg("user", command, "user")
            question.id = "external-approval-command-" + uuid4().hex
            request = SimpleNamespace(
                channel="console",
                session_id=pending.session_id,
                user_id=pending.user_id,
                source_id="source",
                channel_meta={**payload["meta"], "chat_id": chat.id},
            )
            with tenant_context(tenant_id="tenant", source_id="source"):
                async for frame in stream_indexed_query(
                    runner,
                    storage,
                    [question],
                    request=request,
                    query=command,
                ):
                    yield frame

    console = ConsoleChannel()

    class ChannelManager:
        async def get_channel(self, name):
            return console if name == "console" else None

    class TaskTracker:
        async def status(self, _run_key):
            return "idle"

    class Coordinator:
        def __init__(self):
            self.producer_started = False
            self.cancelled_unstarted = False

        async def start_or_attach(self, chat_id, payload, producer, **kwargs):
            self.payload = payload
            self.identity = SimpleNamespace(
                chat_id=chat_id,
                msgid=kwargs["msgid"],
            )

            async def run_producer():
                self.frames = [
                    frame async for frame in producer(self.identity, payload)
                ]

            self.producer_task = asyncio.create_task(run_producer())
            await asyncio.sleep(0)
            return SimpleNamespace(identity=self.identity, is_new_run=True)

        async def mark_producer_started(self, identity):
            if identity != self.identity or self.cancelled_unstarted:
                return False
            self.producer_started = True
            return True

        async def cancel_unstarted(self, identity):
            if identity == self.identity and not self.producer_started:
                self.cancelled_unstarted = True
                return True
            return False

    coordinator = Coordinator()
    workspace = SimpleNamespace(
        agent_id="agent",
        channel_manager=ChannelManager(),
        chat_manager=SimpleNamespace(
            get_or_create_chat=AsyncMock(return_value=chat),
        ),
        task_tracker=TaskTracker(),
        answer_turn_coordinator=coordinator,
        runner=SimpleNamespace(
            session=SimpleNamespace(mutate_session_state=AsyncMock()),
        ),
    )
    return workspace, coordinator


@pytest.mark.asyncio
async def test_sql_approval_with_mismatched_carrier_does_not_create_run(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    database = conversation_test_database
    (
        storage,
        output,
        emitter,
        root_context,
        _waiting_attempt,
        service,
        pending,
        effective_tenant_id,
    ) = await _create_waiting_approval(database, tmp_path, monkeypatch)
    pending.extra["agent_observability_context"]["scope"][
        "agent_id"
    ] = "another-agent"
    runner = _runner_for_approval(service, effective_tenant_id, monkeypatch)
    question = Msg("user", "/deny", "user")
    question.id = "approval-command-" + uuid4().hex
    request = SimpleNamespace(
        channel="console",
        session_id="session",
        user_id="alice",
        source_id="source",
        channel_meta={"source_id": "source", "chat_id": "one"},
    )
    with tenant_context(tenant_id="tenant", source_id="source"):
        _ = [
            frame
            async for frame in stream_indexed_query(
                runner,
                storage,
                [question],
                request=request,
                query="/deny",
            )
        ]
    assert pending.status == "denied"
    assert emitter.close(timeout=1) == 0
    records = [json.loads(line) for line in output.getvalue().splitlines()]
    assert {event["obs_run_id"] for event in records} == {
        root_context.obs_run_id,
    }
    assert not any(event["event_name"] == "run.ended" for event in records)
