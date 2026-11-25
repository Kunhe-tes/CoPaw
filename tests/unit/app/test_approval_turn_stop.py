# -*- coding: utf-8 -*-
from types import SimpleNamespace
import json

import pytest

from swe.app.approvals.service import ApprovalService
from swe.app.answer_turn.coordinator import AnswerTurnCoordinator
from swe.app.answer_turn.models import TurnOutcome
from swe.observability import Observability, Scope, bind_context
from swe.observability.emitter import JsonlEmitter
from swe.observability import runner_lifecycle
from swe.config.context import tenant_context
from swe.security.tool_guard.approval import ApprovalDecision


def _result():
    return SimpleNamespace(findings=[], findings_count=0)


@pytest.mark.asyncio
async def test_supersede_pending_for_turn_only_affects_that_chat_turn() -> (
    None
):
    service = ApprovalService()
    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        target = await service.create_pending(
            session_id="session-1",
            user_id="user-1",
            channel="console",
            tool_name="read_file",
            result=_result(),
            extra={"chat_id": "chat-a", "msgid": "turn-a"},
        )
        same_chat_other_turn = await service.create_pending(
            session_id="session-1",
            user_id="user-1",
            channel="console",
            tool_name="read_file",
            result=_result(),
            extra={"chat_id": "chat-a", "msgid": "turn-b"},
        )
        other_chat_same_turn = await service.create_pending(
            session_id="session-1",
            user_id="user-1",
            channel="console",
            tool_name="read_file",
            result=_result(),
            extra={"chat_id": "chat-b", "msgid": "turn-a"},
        )

        count = await service.supersede_pending_for_turn("chat-a", "turn-a")

    assert count == 1
    assert target.status == "superseded"
    assert target.future.result() == ApprovalDecision.TIMEOUT
    assert same_chat_other_turn.status == "pending"
    assert other_chat_same_turn.status == "pending"


@pytest.mark.asyncio
async def test_superseding_waiting_turn_emits_approval_terminal(monkeypatch):
    from io import StringIO

    sink = StringIO()
    emitter = JsonlEmitter(stream=sink)
    observer = Observability(emitter)
    monkeypatch.setattr(runner_lifecycle, "_OBSERVABILITY", observer)
    service = ApprovalService()
    context = observer.admit_run(
        scope=Scope("swe", "source-a", "tenant-a", "agent-a"),
        business_ref={
            "chat_id": "chat-a",
            "root_question_msgid": "turn-a",
            "session_id": "session-1",
        },
        enabled=True,
    )
    attempt = observer.start_attempt(context)
    owner = SimpleNamespace(_agent_observability_contexts={})

    class Stream:
        async def attach_or_start(self, *_args, **_kwargs):
            return object(), True

        async def close(self, _identity):
            return None

    class Execution:
        async def persist_stop(self, _identity):
            return None

        async def request_cooperative_stop(self, _identity):
            return None

        async def hard_cancel(self, _identity):
            return None

    class Session:
        async def persist_outcome(self, outcome):
            runner_lifecycle.finish_deferred_query_run(
                owner,
                outcome.identity,
                outcome.status.value,
            )

    class Goal:
        async def interrupt_if_matches(self, *_args):
            return None

    class SubAgent:
        async def cancel_for_turn(self, _identity):
            return None

    from swe.app.workspace.workspace import _WorkspaceApprovalPort

    monkeypatch.setattr(
        "swe.app.approvals.get_approval_service",
        lambda: service,
    )
    coordinator = AnswerTurnCoordinator(
        stream=Stream(),
        execution=Execution(),
        session=Session(),
        goal=Goal(),
        subagent=SubAgent(),
        approval=_WorkspaceApprovalPort(owner),
        hard_cancel_delay=0.01,
    )

    async def producer(_identity, _payload):
        yield ""

    lease = await coordinator.start_or_attach(
        "chat-a",
        {},
        producer,
        msgid="turn-a",
    )
    identity = lease.identity
    owner._agent_observability_contexts[identity] = (
        context,
        attempt,
        True,
    )
    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        with bind_context(attempt):
            carrier = runner_lifecycle.approval_context_carrier()
            pending = await service.create_pending(
                session_id="session-1",
                user_id="user-1",
                channel="console",
                tool_name="read_file",
                result=_result(),
                extra={
                    "chat_id": "chat-a",
                    "msgid": "turn-a",
                    "source_id": "source-a",
                    "tenant_id": "tenant-a",
                    "agent_id": "agent-a",
                    "agent_observability_context": carrier,
                },
            )
            runner_lifecycle.record_approval_requested(
                attempt,
                pending.request_id,
                started_at=pending.created_at,
            )
        runner_lifecycle.finish_query_run(
            context,
            attempt,
            "completed",
            waiting_for_approval=True,
        )
        runner_lifecycle.defer_query_run_settlement(
            owner,
            identity,
            context,
            attempt,
            waiting_for_approval=True,
        )
        stop = await coordinator.claim_stop(identity, msgid="turn-a")
        assert stop.accepted
        assert await coordinator.settle(
            TurnOutcome.cancelled(identity),
        )
    assert emitter.close(timeout=1) == 0
    events = [json.loads(line) for line in sink.getvalue().splitlines()]
    resolved = [
        event for event in events if event["event_name"] == "approval.resolved"
    ]
    assert len(resolved) == 1
    assert resolved[0]["decision"] == "superseded"
    assert resolved[0]["obs_run_id"] == context.obs_run_id
    assert resolved[0]["obs_attempt_id"] == attempt.obs_attempt_id
    attempt_terminals = [
        event for event in events if event["event_name"] == "attempt.ended"
    ]
    assert len(attempt_terminals) == 1
    assert attempt_terminals[0]["status"] == "waiting_approval"
    assert events[-1]["event_name"] == "run.ended"
    assert events[-1]["status"] == "cancelled"
    event_names = [event["event_name"] for event in events]
    assert event_names.index("approval.resolved") < event_names.index(
        "run.ended",
    )
