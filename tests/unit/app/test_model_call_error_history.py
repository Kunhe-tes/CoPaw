# -*- coding: utf-8 -*-

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.swe.app.runner.api import (
    get_chat_manager,
    get_session,
    get_workspace,
    router,
)
from src.swe.app.runner.manager import ChatManager
from src.swe.app.runner.models import ChatSpec, ChatsFile
from src.swe.app.runner.repo import BaseChatRepository
from src.swe.app.runner.model_call_error_detail import (
    MODEL_CALL_FAILED_CODE,
)


class _InMemoryChatRepository(BaseChatRepository):
    def __init__(self, chats: list[ChatSpec]) -> None:
        self.path = "<memory>"
        self._state = ChatsFile(chats=chats)

    async def load(self) -> ChatsFile:
        return self._state.model_copy(deep=True)

    async def save(self, chats_file: ChatsFile) -> None:
        self._state = chats_file.model_copy(deep=True)


class _FakeTaskTracker:
    async def get_status(self, _chat_id: str) -> str:
        return "idle"


class _FakeSession:
    async def get_session_state_dict(self, _session_id: str, _user_id: str):
        return {
            "model_call_failed_messages": [
                {
                    "id": "model-call-error-1",
                    "type": "error",
                    "role": "assistant",
                    "status": "failed",
                    "code": MODEL_CALL_FAILED_CODE,
                    "message": "provider diagnostic for replay",
                    "content": [],
                    "timestamp": "2026-06-27T00:00:00+00:00",
                    "metadata": {"model_call_failed": True},
                },
            ],
        }


def _client() -> TestClient:
    chat = ChatSpec(
        id="chat-1",
        session_id="session-1",
        user_id="user-1",
        channel="console",
        name="chat",
    )
    manager = ChatManager(repo=_InMemoryChatRepository([chat]))
    session = _FakeSession()
    workspace = SimpleNamespace(
        chat_manager=manager,
        task_tracker=_FakeTaskTracker(),
        runner=SimpleNamespace(session=session),
    )
    app = FastAPI()
    app.include_router(router)

    async def _get_workspace():
        return workspace

    async def _get_chat_manager():
        return manager

    async def _get_session():
        return session

    app.dependency_overrides[get_workspace] = _get_workspace
    app.dependency_overrides[get_chat_manager] = _get_chat_manager
    app.dependency_overrides[get_session] = _get_session
    return TestClient(app)


def test_chat_history_replays_model_call_failed_detail() -> None:
    response = _client().get("/chats/chat-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["messages"] == [
        {
            "sequence_number": None,
            "object": "message",
            "status": "failed",
            "error": None,
            "id": "model-call-error-1",
            "type": "error",
            "role": "assistant",
            "content": [],
            "code": MODEL_CALL_FAILED_CODE,
            "message": "provider diagnostic for replay",
            "usage": None,
            "metadata": {"model_call_failed": True},
            "timestamp": "2026-06-27T00:00:00+00:00",
        },
    ]
