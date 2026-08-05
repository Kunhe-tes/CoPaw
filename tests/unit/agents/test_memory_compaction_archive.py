# -*- coding: utf-8 -*-
"""Regression coverage for chat-scoped compaction archive integration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest
from agentscope.message import Msg

from swe.agents.command_handler import CommandHandler
from swe.agents.hooks.memory_compaction import MemoryCompactionHook
from swe.agents.memory.conversation_archive import (
    attach_conversation_archive,
)
from swe.agents.memory.reme_light_memory_manager import ReMeLightMemoryManager
from swe.config.config import ToolResultCompactConfig


def _chat_id() -> str:
    return str(uuid.uuid4())


def _message(index: int) -> Msg:
    message = Msg(
        name="user",
        role="user",
        content=f"message-{index}",
        timestamp=f"2026-08-01 12:00:{index:02d}.000",
    )
    message.id = f"message-{index}"
    return message


@pytest.mark.asyncio
async def test_chat_memory_commits_archive_before_removing_online_messages(
    tmp_path,
) -> None:
    first, second = _message(1), _message(2)
    memory = SimpleNamespace(content=[(first, []), (second, [])])
    attach_conversation_archive(memory, tmp_path / "dialog", _chat_id())

    boundary = await memory.archive_compacted_messages([first])

    assert [message.id for message, _marks in memory.content] == ["message-2"]
    page = await memory.conversation_archive_store.read_page(boundary.chat_id)
    assert [message.id for message in page.messages] == ["message-1"]


@pytest.mark.asyncio
async def test_chat_memory_clear_does_not_create_a_recoverable_boundary(
    tmp_path,
) -> None:
    memory = SimpleNamespace(content=[(_message(1), [])])
    chat_id = _chat_id()
    attach_conversation_archive(memory, tmp_path / "dialog", chat_id)

    memory.clear_content()

    assert memory.content == []
    assert (
        await memory.conversation_archive_store.read_page(chat_id)
    ).messages == []


@pytest.mark.asyncio
async def test_reme_memory_factory_attaches_archive_only_for_a_chat_id(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_memory = SimpleNamespace(content=[], _compressed_summary="")

    async def add(message: Msg) -> None:
        raw_memory.content.append((message, []))

    raw_memory.add = add
    factory_calls = 0

    def get_memory(**_kwargs):
        nonlocal factory_calls
        factory_calls += 1
        return raw_memory

    manager = object.__new__(ReMeLightMemoryManager)
    manager.agent_id = "default"
    manager.tenant_id = None
    manager.working_dir = str(tmp_path)
    manager._warn_if_version_mismatch = lambda: None
    manager._reme = SimpleNamespace(
        get_in_memory_memory=get_memory,
    )
    monkeypatch.setattr(
        "swe.agents.memory.reme_light_memory_manager.load_agent_config",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "swe.agents.memory.reme_light_memory_manager.get_swe_token_counter",
        lambda _config: object(),
    )

    assert manager.get_in_memory_memory() is raw_memory
    chat_id = _chat_id()
    assert manager.get_in_memory_memory(chat_id=chat_id) is raw_memory
    assert manager.get_in_memory_memory(chat_id=chat_id) is raw_memory
    assert factory_calls == 2
    assert hasattr(raw_memory, "archive_compacted_messages")

    other_chat = _chat_id()
    other_memory = manager.get_in_memory_memory(chat_id=other_chat)
    assert other_memory is not raw_memory
    assert manager.get_in_memory_memory(chat_id=chat_id) is raw_memory
    await raw_memory.add(_message(1))
    await other_memory.add(_message(2))
    await manager.get_in_memory_memory(chat_id=chat_id).add(_message(3))
    first_state = await raw_memory.chat_checkpoint_store.read_checkpoint_state(
        chat_id,
    )
    second_state = (
        await other_memory.chat_checkpoint_store.read_checkpoint_state(
            other_chat,
        )
    )
    assert [event.source_refs for event in first_state.events] == [
        ("message:message-1",),
        ("message:message-3",),
    ]
    assert [event.source_refs for event in second_state.events] == [
        ("message:message-2",),
    ]


@pytest.mark.asyncio
async def test_automatic_compaction_persists_before_summary_and_returns_boundary() -> (
    None
):
    boundary = SimpleNamespace(id="boundary-1")
    memory = SimpleNamespace(
        archive_compacted_messages=AsyncMock(return_value=boundary),
        update_compressed_summary=AsyncMock(),
    )
    hook = MemoryCompactionHook(SimpleNamespace())

    result = await hook._persist_compaction_result(
        memory,
        [_message(1)],
        "summary",
    )

    assert result is boundary
    memory.archive_compacted_messages.assert_awaited_once()
    memory.update_compressed_summary.assert_awaited_once_with("summary")


@pytest.mark.asyncio
async def test_automatic_compaction_emits_only_one_boundary_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = _message(1)
    boundary = SimpleNamespace(
        to_dict=lambda: {"id": "boundary-1", "archived_message_count": 1},
    )
    memory = SimpleNamespace(
        get_compressed_summary=lambda: "",
        get_memory=AsyncMock(return_value=[message]),
        archive_compacted_messages=AsyncMock(return_value=boundary),
        update_compressed_summary=AsyncMock(),
    )
    manager = SimpleNamespace(
        agent_id="default",
        tenant_id=None,
        compact_tool_result=AsyncMock(),
        check_context=AsyncMock(return_value=([message], [], True)),
        compact_memory=AsyncMock(return_value="summary"),
    )
    running = SimpleNamespace(
        memory_compact_threshold=1,
        memory_compact_reserve=0,
        tool_result_compact=ToolResultCompactConfig(enabled=False),
        memory_summary=SimpleNamespace(memory_summary_enabled=False),
        context_compact=SimpleNamespace(context_compact_enabled=True),
    )
    monkeypatch.setattr(
        "swe.agents.hooks.memory_compaction.load_agent_config",
        lambda *_args, **_kwargs: SimpleNamespace(running=running),
    )
    monkeypatch.setattr(
        "swe.agents.hooks.memory_compaction.get_swe_token_counter",
        lambda _config: SimpleNamespace(count=AsyncMock(return_value=0)),
    )
    agent = SimpleNamespace(
        name="agent",
        sys_prompt="",
        memory=memory,
        model=object(),
        formatter=object(),
        print=AsyncMock(),
        _request_context={"chat_id": _chat_id()},
    )

    await MemoryCompactionHook(manager)(agent, {})

    printed = agent.print.await_args.args[0]
    assert printed.content == [{"type": "text", "text": ""}]
    assert (
        printed.metadata["conversation_compaction_boundary"]["id"]
        == "boundary-1"
    )
    assert agent.print.await_count == 1


@pytest.mark.asyncio
async def test_manual_compact_emits_only_boundary_metadata_for_chat_memory() -> (
    None
):
    boundary = SimpleNamespace(
        to_dict=lambda: {
            "id": "boundary-1",
            "archived_message_count": 1,
        },
    )
    memory = SimpleNamespace(
        get_compressed_summary=lambda: "",
        archive_compacted_messages=AsyncMock(return_value=boundary),
        update_compressed_summary=AsyncMock(),
        clear_content=AsyncMock(),
    )
    manager = SimpleNamespace(
        add_async_summary_task=lambda **_kwargs: None,
        compact_memory=AsyncMock(return_value="summary"),
    )
    handler = CommandHandler(
        agent_name="agent",
        memory=memory,
        memory_manager=manager,
        request_context={"chat_id": _chat_id()},
    )

    result = await handler._process_compact([_message(1)])

    assert result.content == [
        {"type": "text", "text": ""},
    ]
    assert (
        result.metadata["conversation_compaction_boundary"]["id"]
        == "boundary-1"
    )
    memory.archive_compacted_messages.assert_awaited_once()
    memory.update_compressed_summary.assert_awaited_once_with("summary")
    memory.clear_content.assert_not_called()


@pytest.mark.asyncio
async def test_new_and_clear_do_not_call_the_archive_method() -> None:
    memory = SimpleNamespace(
        clear_compressed_summary=lambda: None,
        clear_content=lambda: None,
        archive_compacted_messages=AsyncMock(),
    )
    handler = CommandHandler(
        agent_name="agent",
        memory=memory,
        memory_manager=SimpleNamespace(),
    )

    await handler._process_new([])
    await handler._process_clear([])

    memory.archive_compacted_messages.assert_not_awaited()
