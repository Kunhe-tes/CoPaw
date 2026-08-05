# -*- coding: utf-8 -*-
"""Regression tests for tenant-aware daemon restart reload."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest
from agentscope.message import Msg, TextBlock

from swe.app.runner import command_dispatch, daemon_commands


@pytest.mark.asyncio
async def test_resolve_command_context_finds_chat_from_session() -> None:
    class ChatManagerWithLookupContract:
        async def get_chat_id_by_session(
            self,
            session_id: str,
            channel: str,
        ) -> str:
            assert (session_id, channel) == ("session-1", "console")
            return "chat-1"

    chat_manager = ChatManagerWithLookupContract()
    runner = SimpleNamespace(_chat_manager=chat_manager)
    request = SimpleNamespace(
        session_id="session-1",
        user_id="user-1",
        channel="console",
        channel_meta={},
    )

    context = await command_dispatch._resolve_command_context(request, runner)

    assert context.chat_id == "chat-1"
    assert context.session_id == "session-1"
    assert context.channel == "console"


@pytest.mark.asyncio
async def test_resolve_command_context_preserves_missing_request_channel() -> (
    None
):
    context = await command_dispatch._resolve_command_context(
        SimpleNamespace(session_id="", user_id="", channel_meta={}),
        SimpleNamespace(_chat_manager=None),
    )

    assert context.channel == ""


@pytest.mark.asyncio
async def test_run_daemon_restart_passes_tenant_id() -> None:
    reload_calls: list[tuple[str, str | None]] = []

    class FakeManager:
        async def reload_agent(
            self,
            agent_id: str,
            tenant_id: str | None = None,
        ) -> bool:
            reload_calls.append((agent_id, tenant_id))
            return True

    message = await daemon_commands.run_daemon_restart(
        daemon_commands.DaemonContext(
            manager=FakeManager(),
            agent_id="default",
            tenant_id="tenant-a",
        ),
    )

    assert "Restart completed" in message
    assert reload_calls == [("default", "tenant-a")]


@pytest.mark.asyncio
async def test_run_command_path_builds_tenant_aware_daemon_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, str | None] = {}

    async def fake_handle_daemon_command(self, query, context):
        del self
        observed["query"] = query
        observed["tenant_id"] = context.tenant_id
        return Msg(
            name="Friday",
            role="assistant",
            content=[TextBlock(type="text", text="ok")],
        )

    monkeypatch.setattr(
        command_dispatch.DaemonCommandHandlerMixin,
        "handle_daemon_command",
        fake_handle_daemon_command,
    )

    runner = SimpleNamespace(
        agent_id="default",
        memory_manager=None,
        _manager=SimpleNamespace(),
        _workspace=SimpleNamespace(tenant_id="tenant-a"),
    )
    request = SimpleNamespace(session_id="session-1", user_id="user-1")
    msgs = [SimpleNamespace(get_text_content=lambda: "/daemon restart")]

    results = []
    async for item in command_dispatch.run_command_path(
        request,
        msgs,
        runner,
    ):
        results.append(item)

    assert len(results) == 2
    assert observed == {
        "query": "/daemon restart",
        "tenant_id": "tenant-a",
    }


@pytest.mark.asyncio
async def test_run_command_path_passes_chat_id_to_compaction_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    class FakeCommandHandler:
        SYSTEM_COMMANDS = {"compact"}

        def __init__(self, *, memory, request_context, **_kwargs) -> None:
            observed["memory"] = memory
            observed["request_context"] = request_context

        async def handle_conversation_command(self, query: str) -> Msg:
            observed["query"] = query
            return Msg(
                name="Friday",
                role="assistant",
                content=[TextBlock(type="text", text="compacted")],
            )

    class FakeMemory:
        def load_state_dict(self, *_args, **_kwargs) -> None:
            return None

        def state_dict(self) -> dict[str, object]:
            return {}

    class FakeMemoryManager:
        def get_in_memory_memory(self, *, chat_id=None):
            observed["memory_chat_id"] = chat_id
            return FakeMemory()

    class FakeSession:
        async def get_session_state_dict(self, **_kwargs):
            return {}

        async def update_session_state(self, **_kwargs) -> None:
            return None

    monkeypatch.setattr(command_dispatch, "CommandHandler", FakeCommandHandler)
    chat_id = str(uuid.uuid4())
    runner = SimpleNamespace(
        memory_manager=FakeMemoryManager(),
        session=FakeSession(),
    )
    request = SimpleNamespace(
        session_id="session-1",
        user_id="user-1",
        chat_id=chat_id,
        channel="console",
    )
    msgs = [SimpleNamespace(get_text_content=lambda: "/compact")]

    results = [
        item
        async for item in command_dispatch.run_command_path(
            request,
            msgs,
            runner,
        )
    ]

    assert len(results) == 1
    assert observed["memory_chat_id"] == chat_id
    assert observed["request_context"] == {
        "session_id": "session-1",
        "user_id": "user-1",
        "channel": "console",
        "chat_id": chat_id,
        "trace_id": None,
    }
