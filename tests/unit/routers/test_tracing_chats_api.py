# -*- coding: utf-8 -*-
"""SWE 侧运营看板聊天映射接口测试。"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from swe.app.routers.tracing import router
from swe.app.runner.models import ChatSpec
from swe.config.context import resolve_scope_id


class _FakeChatManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str | None, str | None]] = []
        self.get_calls: list[str] = []

    async def list_chats(
        self,
        user_id: str | None = None,
        channel: str | None = None,
    ) -> list[ChatSpec]:
        self.calls.append((user_id, channel))
        return [
            ChatSpec(
                id="chat-1",
                session_id="cron-task:job-1",
                user_id=user_id or "",
                channel=channel or "console",
                name="任务会话",
            ),
        ]

    async def get_chat(self, chat_id: str) -> ChatSpec | None:
        self.get_calls.append(chat_id)
        if chat_id != "chat-1":
            return None
        return ChatSpec(
            id="chat-1",
            session_id="cron-task:job-1",
            user_id="target-user",
            channel="console",
            name="任务会话",
        )


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def get_session_state_dict(
        self,
        session_id: str,
        user_id: str,
    ) -> dict:
        self.calls.append((session_id, user_id))
        return {
            "task_messages": [
                {
                    "id": "message-1",
                    "role": "assistant",
                    "content": "任务执行完成",
                    "timestamp": "2026-05-25T10:00:00Z",
                },
            ],
        }


class _FakeTaskTracker:
    async def get_status(self, chat_id: str) -> str:
        return "idle"


class _FakeManager:
    def __init__(self, chat_manager: _FakeChatManager) -> None:
        self.chat_manager = chat_manager
        self.calls: list[tuple[str, str | None]] = []
        self.session = _FakeSession()

    async def get_agent(self, agent_id: str, tenant_id: str | None = None):
        self.calls.append((agent_id, tenant_id))
        return SimpleNamespace(
            chat_manager=self.chat_manager,
            runner=SimpleNamespace(session=self.session),
            task_tracker=_FakeTaskTracker(),
        )


class _FakePool:
    def __init__(self) -> None:
        self.calls: list[dict[str, str | None]] = []

    async def ensure_bootstrap(
        self,
        tenant_id: str,
        *,
        source_id: str | None = None,
        tenant_name: str | None = None,
        bbk_id: str | None = None,
        scope_id: str | None = None,
    ) -> None:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "source_id": source_id,
                "tenant_name": tenant_name,
                "bbk_id": bbk_id,
                "scope_id": scope_id,
            },
        )


def _client() -> tuple[TestClient, _FakeManager, _FakeChatManager, _FakePool]:
    app = FastAPI()
    app.include_router(router)
    chat_manager = _FakeChatManager()
    manager = _FakeManager(chat_manager)
    pool = _FakePool()
    app.state.multi_agent_manager = manager
    app.state.tenant_workspace_pool = pool
    return TestClient(app), manager, chat_manager, pool


def test_get_user_chats_requires_user_id() -> None:
    client, _, _, _ = _client()

    response = client.get("/tracing/chats")

    assert response.status_code == 422


def test_get_user_chats_reads_target_user_workspace() -> None:
    client, manager, chat_manager, pool = _client()

    response = client.get(
        "/tracing/chats",
        params={"user_id": "target-user", "channel": "console"},
        headers={
            "X-Agent-Id": "agent-a",
            "X-Source-Id": "CMSJY",
            "X-Bbk-Id": "100",
        },
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == "chat-1"
    assert response.json()[0]["session_id"] == "cron-task:job-1"
    assert chat_manager.calls == [("target-user", "console")]
    assert manager.calls == [
        ("agent-a", resolve_scope_id("target-user", "CMSJY")),
    ]
    assert pool.calls == [
        {
            "tenant_id": "target-user",
            "source_id": "CMSJY",
            "tenant_name": None,
            "bbk_id": "100",
            "scope_id": None,
        },
    ]


def test_get_user_chat_reads_target_user_workspace() -> None:
    client, manager, chat_manager, _ = _client()

    response = client.get(
        "/tracing/chats/chat-1",
        params={"user_id": "target-user"},
        headers={
            "X-Agent-Id": "agent-a",
            "X-Source-Id": "CMSJY",
        },
    )

    assert response.status_code == 200
    assert response.json()["messages"][0]["id"] == "message-1"
    assert chat_manager.get_calls == ["chat-1"]
    assert manager.session.calls == [("cron-task:job-1", "target-user")]
    assert manager.calls == [
        ("agent-a", resolve_scope_id("target-user", "CMSJY")),
    ]
