# -*- coding: utf-8 -*-
"""Characterize the Console answer-turn contract before coordinator extraction."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from swe.app.routers import console as console_router
from swe.app.runner.task_tracker import StopClaimResult, TaskTracker


class _ChatManager:
    def __init__(self, chat_id: str = "chat-1") -> None:
        self.chat = SimpleNamespace(
            id=chat_id,
            channel="console",
            user_id="user-1",
            meta={"source_id": "source-1"},
        )

    async def get_or_create_chat(self, *_args, **_kwargs):
        return self.chat

    async def get_chat(self, chat_id: str):
        return self.chat if chat_id == self.chat.id else None


class _BlockingConsoleChannel:
    def __init__(self) -> None:
        self.producer_calls = 0
        self.release = asyncio.Event()

    async def stream_one(self, _payload):
        self.producer_calls += 1
        yield 'data: {"started": true}\n\n'
        await self.release.wait()


def _payload() -> dict:
    return {
        "sender_id": "user-1",
        "channel_id": "console",
        "content_parts": [],
        "meta": {"session_id": "session-1"},
    }


@pytest.mark.asyncio
async def test_console_duplicate_submission_attaches_to_one_server_owned_turn():
    tracker = TaskTracker()
    channel = _BlockingConsoleChannel()
    workspace = SimpleNamespace(
        agent_id="agent-1",
        chat_manager=_ChatManager(),
    )

    first_queue, chat_id, first_msgid, first_is_new = (
        await console_router._start_new_chat(
            workspace,
            tracker,
            channel,
            "session-1",
            _payload(),
            include_run_status=True,
        )
    )
    await asyncio.wait_for(first_queue.get(), timeout=1)

    second_queue, second_chat_id, second_msgid, second_is_new = (
        await console_router._start_new_chat(
            workspace,
            tracker,
            channel,
            "session-1",
            _payload(),
            include_run_status=True,
        )
    )

    assert chat_id == second_chat_id == "chat-1"
    assert first_is_new is True
    assert second_is_new is False
    assert first_msgid is not None
    assert second_msgid == first_msgid
    assert await tracker.get_run_identity(chat_id) == (chat_id, first_msgid)
    assert channel.producer_calls == 1
    assert await asyncio.wait_for(second_queue.get(), timeout=1) == (
        'data: {"started": true}\n\n'
    )

    channel.release.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)


@pytest.mark.asyncio
async def test_cooperative_stop_enters_stopping_before_the_hard_cancel_settlement():
    tracker = TaskTracker()
    channel = _BlockingConsoleChannel()
    hard_cancel = asyncio.Event()

    async def settle(task, _run_key):
        await hard_cancel.wait()
        task.cancel()

    tracker._settle_stop = settle  # type: ignore[method-assign]
    queue, is_new = await tracker.attach_or_start(
        "chat-stop",
        {},
        channel.stream_one,
        msgid="turn-1",
    )
    assert is_new is True
    await asyncio.wait_for(queue.get(), timeout=1)

    claim = await tracker.claim_stop(
        "chat-stop",
        msgid="turn-1",
        cooperative=True,
    )

    assert claim == StopClaimResult(
        accepted=True,
        chat_id="chat-stop",
        msgid="turn-1",
        status="stopping",
    )
    assert await tracker.get_status("chat-stop") == "stopping"
    assert await tracker.get_run_identity("chat-stop") == (
        "chat-stop",
        "turn-1",
    )

    hard_cancel.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)
    assert await tracker.get_status("chat-stop") == "idle"


@pytest.mark.asyncio
async def test_stop_with_mismatched_msgid_leaves_the_active_turn_running():
    tracker = TaskTracker()
    channel = _BlockingConsoleChannel()
    queue, is_new = await tracker.attach_or_start(
        "chat-mismatch",
        {},
        channel.stream_one,
        msgid="turn-active",
    )
    assert is_new is True
    await asyncio.wait_for(queue.get(), timeout=1)

    claim = await tracker.claim_stop(
        "chat-mismatch",
        msgid="turn-stale",
        cooperative=True,
    )

    assert claim == StopClaimResult(accepted=False, status="running")
    assert await tracker.get_status("chat-mismatch") == "running"
    assert await tracker.get_run_identity("chat-mismatch") == (
        "chat-mismatch",
        "turn-active",
    )

    channel.release.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)


def test_accepted_console_stop_supersedes_approvals_then_interrupts_goal_and_subagents(
    monkeypatch,
) -> None:
    effects: list[tuple[str, str, str]] = []

    class _Tracker:
        async def claim_stop(self, chat_id, *, msgid, cooperative):
            assert cooperative is True
            assert (chat_id, msgid) == ("chat-1", "turn-1")
            return StopClaimResult(
                accepted=True,
                chat_id=chat_id,
                msgid=msgid,
                status="stopping",
            )

    class _ApprovalService:
        async def supersede_pending_for_turn(self, chat_id, msgid):
            effects.append(("approval", chat_id, msgid))

    async def interrupt_goal(_workspace, chat_id, msgid):
        effects.append(("goal", chat_id, msgid))

    async def cancel_subagents(_workspace, chat_id, msgid):
        effects.append(("subagent", chat_id, msgid))

    workspace = SimpleNamespace(
        task_tracker=_Tracker(),
        chat_manager=_ChatManager(),
    )
    approval_service = _ApprovalService()

    async def get_workspace(_request):
        return workspace

    monkeypatch.setattr(console_router, "get_agent_for_request", get_workspace)
    monkeypatch.setattr(
        "swe.app.approvals.get_approval_service",
        lambda: approval_service,
    )
    monkeypatch.setattr(
        console_router,
        "_interrupt_console_goal",
        interrupt_goal,
    )
    monkeypatch.setattr(
        console_router,
        "_cancel_console_turn_subagents",
        cancel_subagents,
    )

    app = FastAPI()
    app.include_router(console_router.router)
    response = TestClient(app).post(
        "/console/chat/stop?chat_id=chat-1&msgid=turn-1",
        headers={"X-User-Id": "user-1", "X-Source-Id": "source-1"},
    )

    assert response.json() == {
        "stopped": True,
        "accepted": True,
        "status": "stopping",
        "chat_id": "chat-1",
        "msgid": "turn-1",
    }
    assert effects == [
        ("approval", "chat-1", "turn-1"),
        ("goal", "chat-1", "turn-1"),
        ("subagent", "chat-1", "turn-1"),
    ]


@pytest.mark.asyncio
async def test_reconnect_replays_buffered_events_without_restarting_execution():
    tracker = TaskTracker()
    channel = _BlockingConsoleChannel()
    queue, is_new = await tracker.attach_or_start(
        "chat-reconnect",
        {},
        channel.stream_one,
        msgid="turn-1",
    )
    assert is_new is True
    first_event = await asyncio.wait_for(queue.get(), timeout=1)

    reconnect_queue = await tracker.attach("chat-reconnect")

    assert reconnect_queue is not None
    assert (
        await asyncio.wait_for(reconnect_queue.get(), timeout=1) == first_event
    )
    assert channel.producer_calls == 1
    assert await tracker.get_run_identity("chat-reconnect") == (
        "chat-reconnect",
        "turn-1",
    )

    channel.release.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)
