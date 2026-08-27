# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.swe.app.routers import console as console_router
from src.swe.app.runner.task_tracker import StopClaimResult


class _FakeConsoleChannel:
    def resolve_session_id(self, sender_id: str, channel_meta: dict) -> str:
        return channel_meta.get("session_id") or f"console:{sender_id}"

    async def stream_one(self, payload):
        yield payload


class _FakeChannelManager:
    async def get_channel(self, name: str):
        assert name == "console"
        return _FakeConsoleChannel()


class _FakeChatManager:
    def __init__(self) -> None:
        self.get_or_create_calls: list[tuple[str, str, str, str]] = []
        self.get_chat_id_by_session_calls: list[tuple[str, str]] = []

    async def get_chat(self, chat_id: str):
        if chat_id == "chat-existing":
            return SimpleNamespace(
                id="chat-existing",
                session_id="session-existing",
                user_id="user-1",
                channel="console",
                name="Existing Chat",
            )
        return None

    async def get_chat_id_by_session(self, session_id: str, channel: str):
        self.get_chat_id_by_session_calls.append((session_id, channel))
        if session_id == "session-existing" and channel == "console":
            return "chat-existing"
        return None

    async def get_or_create_chat(
        self,
        session_id: str,
        user_id: str,
        channel_id: str,
        name: str,
        _meta=None,
    ):
        self.get_or_create_calls.append(
            (session_id, user_id, channel_id, name),
        )
        return SimpleNamespace(
            id=f"chat:{session_id}",
            session_id=session_id,
            user_id=user_id,
            channel=channel_id,
            name=name,
        )


class _FakeTaskTracker:
    async def attach_or_start(self, run_key, payload, stream_fn):
        raise AssertionError("attach_or_start should not run during reconnect")

    async def attach(self, run_key):
        if run_key == "chat-existing":
            return object()
        return None

    async def stream_from_queue(self, _queue, _run_key):
        await asyncio.sleep(0)
        yield 'data: {"done": true}\n\n'


def test_console_chat_reconnect_waits_for_recently_started_run() -> None:
    class _EventuallyAvailableChatManager:
        def __init__(self) -> None:
            self.lookup_count = 0

        async def get_chat(self, _chat_id: str):
            return None

        async def get_chat_id_by_session(self, session_id: str, channel: str):
            assert session_id == "1777001065201000"
            assert channel == "console"
            self.lookup_count += 1
            if self.lookup_count == 1:
                return None
            return "chat-real-1"

    class _EventuallyAvailableTaskTracker:
        async def attach(self, run_key: str):
            if run_key == "chat-real-1":
                return object()
            return None

    async def _run() -> tuple[object, str, int]:
        chat_manager = _EventuallyAvailableChatManager()
        # pylint: disable=protected-access
        queue, run_key = await console_router._attach_reconnect_queue(
            SimpleNamespace(chat_manager=chat_manager),
            _EventuallyAvailableTaskTracker(),
            "1777001065201000",
            "console",
        )
        return queue, run_key, chat_manager.lookup_count

    queue, run_key, lookup_count = asyncio.run(_run())

    assert queue is not None
    assert run_key == "chat-real-1"
    assert lookup_count == 2


def test_console_chat_reconnect_accepts_chat_id_without_creating_new_chat(
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    chat_manager = _FakeChatManager()
    workspace = SimpleNamespace(
        channel_manager=_FakeChannelManager(),
        chat_manager=chat_manager,
        task_tracker=_FakeTaskTracker(),
    )

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    client = TestClient(app)

    with client.stream(
        "POST",
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json={
            "reconnect": True,
            "session_id": "chat-existing",
            "user_id": "user-1",
            "channel": "console",
        },
    ) as response:
        assert response.status_code == 200
        assert "X-Swe-Msgid" not in response.headers
        assert list(response.iter_lines()) == [
            ": keep-alive",
            "",
            'data: {"done": true}',
            "",
        ]

    assert not chat_manager.get_or_create_calls


def test_console_chat_reconnect_with_agent_request_shape_does_not_start_run(
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    chat_manager = _FakeChatManager()
    workspace = SimpleNamespace(
        channel_manager=_FakeChannelManager(),
        chat_manager=chat_manager,
        task_tracker=_FakeTaskTracker(),
    )

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    client = TestClient(app)

    with client.stream(
        "POST",
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json={
            "reconnect": True,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "ignored"}],
                },
            ],
            "session_id": "chat-existing",
            "user_id": "user-1",
            "channel": "console",
        },
    ) as response:
        assert response.status_code == 200
        assert "X-Swe-Msgid" not in response.headers
        assert list(response.iter_lines()) == [
            ": keep-alive",
            "",
            'data: {"done": true}',
            "",
        ]

    assert not chat_manager.get_or_create_calls


def test_console_chat_reconnect_accepts_logical_session_id(
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    chat_manager = _FakeChatManager()
    workspace = SimpleNamespace(
        channel_manager=_FakeChannelManager(),
        chat_manager=chat_manager,
        task_tracker=_FakeTaskTracker(),
    )

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    client = TestClient(app)

    with client.stream(
        "POST",
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json={
            "reconnect": True,
            "session_id": "session-existing",
            "user_id": "user-1",
            "channel": "console",
        },
    ) as response:
        assert response.status_code == 200
        assert "X-Swe-Msgid" not in response.headers
        assert list(response.iter_lines()) == [
            ": keep-alive",
            "",
            'data: {"done": true}',
            "",
        ]

    assert chat_manager.get_chat_id_by_session_calls == [
        ("session-existing", "console"),
    ]
    assert not chat_manager.get_or_create_calls


def test_console_chat_stop_returns_turn_bound_claim(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    class _StopChatManager:
        async def get_chat(self, chat_id: str):
            if chat_id == "chat-1":
                return SimpleNamespace(
                    id=chat_id,
                    user_id="user-1",
                    channel="console",
                )
            return None

    class _StopTracker:
        async def claim_stop(self, chat_id: str, msgid: str | None = None):
            assert chat_id == "chat-1"
            assert msgid == "msg-1"
            return StopClaimResult(
                True,
                chat_id=chat_id,
                msgid=msgid,
                status="stopping",
            )

    workspace = SimpleNamespace(
        chat_manager=_StopChatManager(),
        task_tracker=_StopTracker(),
    )

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    response = TestClient(app).post(
        "/console/chat/stop",
        params={"chat_id": "chat-1", "msgid": "msg-1"},
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "stopped": True,
        "accepted": True,
        "status": "stopping",
        "chat_id": "chat-1",
        "msgid": "msg-1",
    }
