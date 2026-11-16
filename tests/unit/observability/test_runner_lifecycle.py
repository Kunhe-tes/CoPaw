# -*- coding: utf-8 -*-
from types import SimpleNamespace
import json

import pytest

from swe.observability import runner_lifecycle
from swe.observability.context import bind_context, current_context
from swe.observability import instrumentation
from swe.observability.instrumentation import Observability
from swe.observability.projector import _validate_payload
from swe.observability.models import ObservabilityContext, Scope
from swe.app.runner.session_lifecycle import admit_user_turn_with_creation


class RecordingEmitter:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event.to_dict())
        return True


def _setup(monkeypatch, tenant_id="tenant-a"):
    emitter = RecordingEmitter()
    monkeypatch.setattr(runner_lifecycle, "capture_enabled", lambda: True)
    monkeypatch.setattr(instrumentation, "capture_enabled", lambda: True)
    monkeypatch.setattr(
        runner_lifecycle,
        "get_current_source_id",
        lambda: "source-a",
    )
    monkeypatch.setattr(
        runner_lifecycle,
        "get_current_effective_tenant_id",
        lambda: tenant_id,
    )
    monkeypatch.setattr(
        runner_lifecycle,
        "_OBSERVABILITY",
        Observability(emitter=emitter),
    )
    return emitter


def _request():
    return SimpleNamespace(channel_meta={"chat_id": "chat-a"})


def _message():
    class Message:
        role = "user"
        id = "question-a"
        content = "private"

        def to_dict(self):
            return {"id": self.id, "role": self.role, "content": self.content}

    return Message()


def test_query_run_uses_safe_scope_and_emits_accepted_running_and_terminal(
    monkeypatch,
):
    emitter = _setup(monkeypatch)
    context = runner_lifecycle.admit_query_run(
        SimpleNamespace(agent_id="agent-a"),
        _request(),
        [_message()],
    )

    attempt = runner_lifecycle.start_query_attempt(context)
    with runner_lifecycle.bind_query_context(attempt):
        assert current_context() == attempt
    assert current_context() is None

    runner_lifecycle.finish_query_run(context, attempt, "completed")

    names = [event["event_name"] for event in emitter.events]
    assert names == [
        "run.accepted",
        "run.state",
        "attempt.started",
        "attempt.ended",
        "run.ended",
    ]
    accepted = emitter.events[0]
    assert accepted["scope"] == {
        "service_unit_id": "swe",
        "source_id": "source-a",
        "tenant_id": "tenant-a",
        "agent_id": "agent-a",
    }
    assert accepted["business_ref"] == {
        "chat_id": "chat-a",
        "root_question_msgid": "question-a",
    }
    assert all(
        "private" not in json.dumps(event, ensure_ascii=False)
        for event in emitter.events
    )
    assert emitter.events[-1]["status"] == "succeeded"
    assert all(
        _validate_payload(json.dumps(event, ensure_ascii=False))
        for event in emitter.events
    )


def test_query_waiting_for_approval_does_not_end_run(monkeypatch):
    emitter = _setup(monkeypatch)
    context = runner_lifecycle.admit_query_run(
        SimpleNamespace(agent_id="agent-a"),
        _request(),
        [_message()],
    )
    attempt = runner_lifecycle.start_query_attempt(context)

    runner_lifecycle.finish_query_run(
        context,
        attempt,
        "completed",
        waiting_for_approval=True,
    )

    assert [event["event_name"] for event in emitter.events] == [
        "run.accepted",
        "run.state",
        "attempt.started",
        "run.state",
        "attempt.ended",
    ]
    assert emitter.events[-2]["status"] == "waiting_approval"
    assert all(
        _validate_payload(json.dumps(event, ensure_ascii=False))
        for event in emitter.events
    )


def test_unknown_business_status_leaves_run_unresolved(monkeypatch):
    emitter = _setup(monkeypatch)
    context = runner_lifecycle.admit_query_run(
        SimpleNamespace(agent_id="agent-a"),
        _request(),
        [_message()],
    )
    attempt = runner_lifecycle.start_query_attempt(context)

    runner_lifecycle.finish_query_run(context, attempt, "interrupted")

    assert not any(event["event_name"] == "run.ended" for event in emitter.events)


def test_default_tenant_is_emittable_without_tenant_context(monkeypatch):
    emitter = _setup(monkeypatch, tenant_id=None)
    context = runner_lifecycle.admit_query_run(
        SimpleNamespace(agent_id="agent-a", tenant_id=None),
        _request(),
        [_message()],
    )

    assert context is not None
    assert emitter.events[0]["scope"]["tenant_id"] == "default_source-a"
    assert _validate_payload(json.dumps(emitter.events[0], ensure_ascii=False))


@pytest.mark.asyncio
async def test_terminal_turn_reexecution_is_new_but_active_reconnect_is_not():
    message = _message()

    class Execution:
        state = {
            "turn_states": {
                message.id: {
                    "status": "completed",
                    "message": message.to_dict(),
                },
            },
        }

        async def hydrate_turn(self, _turn_id):
            return None

        def mark_state_dirty(self):
            return None

        async def commit_state(self, _state):
            self.commits += 1

        commits = 0

    execution = Execution()
    request = SimpleNamespace(channel_meta={})
    run_context = ObservabilityContext.new_run(
        capture_enabled=True,
        scope=Scope("swe", "source-a", "tenant-a", "agent-a"),
        business_ref={"root_question_msgid": message.id},
    )
    first_admission = await admit_user_turn_with_creation(
        execution,
        msgs=[message],
        request=request,
        observability_context=run_context,
    )
    assert first_admission[:2] == (message.id, True)
    assert execution.state["turn_states"][message.id]["status"] == "admitted"
    second_admission = await admit_user_turn_with_creation(
        execution,
        msgs=[message],
        request=request,
    )
    assert second_admission[:2] == (message.id, False)
    assert execution.commits == 1


def test_deferred_runner_settlement_emits_terminal_after_business_commit(
    monkeypatch,
):
    emitter = _setup(monkeypatch)
    owner = SimpleNamespace(_agent_observability_contexts={})
    identity = object()
    context = runner_lifecycle.admit_query_run(
        SimpleNamespace(agent_id="agent-a"),
        _request(),
        [_message()],
    )
    attempt = runner_lifecycle.start_query_attempt(context)
    runner_lifecycle.defer_query_run_settlement(
        owner,
        identity,
        context,
        attempt,
        waiting_for_approval=False,
    )

    assert not any(event["event_name"] == "run.ended" for event in emitter.events)
    runner_lifecycle.finish_deferred_query_run(owner, identity, "completed")

    assert emitter.events[-1]["event_name"] == "run.ended"
    assert emitter.events[-1]["status"] == "succeeded"


def test_early_stop_settlement_is_not_reopened_by_stream_finally(monkeypatch):
    emitter = _setup(monkeypatch)
    owner = SimpleNamespace(_agent_observability_contexts={})
    identity = object()
    context = runner_lifecycle.admit_query_run(
        SimpleNamespace(agent_id="agent-a"),
        _request(),
        [_message()],
    )
    attempt = runner_lifecycle.start_query_attempt(context)
    runner_lifecycle.defer_query_run_settlement(
        owner,
        identity,
        context,
        attempt,
        waiting_for_approval=False,
    )

    runner_lifecycle.finish_deferred_query_run(owner, identity, "cancelled")
    runner_lifecycle.update_deferred_query_run_approval(
        owner,
        identity,
        waiting_for_approval=False,
    )

    assert owner._agent_observability_contexts == {}
    assert emitter.events[-1]["status"] == "cancelled"
