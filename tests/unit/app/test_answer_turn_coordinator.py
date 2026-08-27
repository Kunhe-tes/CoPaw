# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio

import pytest

from swe.app.answer_turn.coordinator import AnswerTurnCoordinator
from swe.app.answer_turn.in_memory import (
    InMemoryApproval,
    InMemoryExecution,
    InMemoryGoal,
    InMemorySession,
    InMemoryStream,
    InMemorySubagent,
)
from swe.app.answer_turn.models import (
    TERMINAL_STATUSES,
    TurnIdentity,
    TurnOutcome,
    TurnStatus,
)


def _coordinator(*, hard_cancel_delay: float = 5.0):
    adapters = {
        "stream": InMemoryStream(),
        "execution": InMemoryExecution(),
        "session": InMemorySession(),
        "goal": InMemoryGoal(),
        "subagent": InMemorySubagent(),
        "approval": InMemoryApproval(),
    }
    return (
        AnswerTurnCoordinator(**adapters, hard_cancel_delay=hard_cancel_delay),
        adapters,
    )


def test_turn_value_objects_are_immutable_and_terminal_statuses_are_explicit():
    identity = TurnIdentity.create(chat_id="chat-1", msgid="msg-1")
    outcome = TurnOutcome.completed(identity, assistant_text="ok")
    assert identity.chat_id == "chat-1"
    assert outcome.status in TERMINAL_STATUSES
    with pytest.raises((AttributeError, TypeError)):
        outcome.status = TurnStatus.CANCELLED  # type: ignore[misc]


@pytest.mark.asyncio
async def test_start_or_attach_creates_one_identity_and_one_producer_per_chat():
    coordinator, adapters = _coordinator()

    async def producer(_identity, _payload):
        return None

    first = await coordinator.start_or_attach(
        "chat-1",
        {"q": 1},
        producer,
        msgid="msg-1",
    )
    second = await coordinator.start_or_attach("chat-1", {"q": 1}, producer)
    assert first.is_new_run is True
    assert second.is_new_run is False
    assert second.identity == first.identity
    assert len(adapters["stream"].start_calls) == 1
    await coordinator.settle(
        TurnOutcome.completed(first.identity, assistant_text="ok"),
    )


@pytest.mark.asyncio
async def test_claim_stop_orders_effects_and_is_idempotent():
    coordinator, adapters = _coordinator(hard_cancel_delay=0.01)

    async def producer(_identity, _payload):
        await asyncio.Event().wait()

    lease = await coordinator.start_or_attach(
        "chat-1",
        {},
        producer,
        msgid="turn-1",
    )
    claim = await coordinator.claim_stop(lease.identity, msgid="turn-1")
    assert claim.accepted is True
    assert await coordinator.status(lease.identity) == TurnStatus.STOPPING
    assert adapters["approval"].calls == [lease.identity]
    assert adapters["goal"].calls == [lease.identity]
    assert adapters["subagent"].calls == [lease.identity]

    duplicate = await coordinator.claim_stop(lease.identity, msgid="turn-1")
    assert duplicate.accepted is True
    assert adapters["approval"].calls == [lease.identity]
    await coordinator.settle(
        TurnOutcome.cancelled(lease.identity, result="stopped"),
    )


@pytest.mark.asyncio
async def test_claim_stop_rejects_stale_msgid_and_hard_cancels_only_live_turn():
    coordinator, adapters = _coordinator(hard_cancel_delay=0.01)

    async def producer(_identity, _payload):
        await asyncio.Event().wait()

    lease = await coordinator.start_or_attach(
        "chat-1",
        {},
        producer,
        msgid="turn-1",
    )
    rejected = await coordinator.claim_stop(lease.identity, msgid="stale")
    assert rejected.accepted is False
    assert await coordinator.status(lease.identity) == TurnStatus.RUNNING
    await coordinator.claim_stop(lease.identity, msgid="turn-1")
    await asyncio.sleep(0.03)
    assert adapters["execution"].hard_cancel_calls == [lease.identity]
    await coordinator.settle(TurnOutcome.cancelled(lease.identity))


@pytest.mark.asyncio
async def test_settle_persists_once_closes_stream_and_removes_active_turn():
    coordinator, adapters = _coordinator()

    async def producer(_identity, _payload):
        return None

    lease = await coordinator.start_or_attach(
        "chat-1",
        {},
        producer,
        msgid="turn-1",
    )
    outcome = TurnOutcome.completed(lease.identity, result={"answer": 1})
    assert await coordinator.settle(outcome) is True
    assert await coordinator.settle(outcome) is False
    assert adapters["session"].calls == [(lease.identity, outcome)]
    assert adapters["stream"].close_calls == [lease.identity]
    assert await coordinator.status(lease.identity) is None
