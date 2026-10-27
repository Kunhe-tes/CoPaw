# -*- coding: utf-8 -*-
"""Expert commands retain Chat compaction without Profile memory writes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from agentscope.message import Msg

from swe.app.runner.command_dispatch import (
    _CommandRequestContext,
    _run_conversation_command,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("expert", [True, False])
async def test_compact_preserves_summary_and_respects_expert_memory_boundary(
    expert,
):
    messages = [Msg("user", "existing Chat context", "user")]
    memory = SimpleNamespace(
        load_state_dict=Mock(),
        get_memory=AsyncMock(return_value=messages),
        get_compressed_summary=Mock(return_value="old Chat summary"),
        update_compressed_summary=AsyncMock(),
        clear_content=Mock(),
        state_dict=Mock(return_value={}),
    )
    manager = SimpleNamespace(
        agent_id="profile",
        tenant_id="user",
        get_in_memory_memory=Mock(return_value=memory),
        add_async_summary_task=Mock(),
        compact_memory=AsyncMock(return_value="new Chat summary"),
    )
    runner = SimpleNamespace(
        memory_manager=manager,
        session=SimpleNamespace(
            get_session_state_dict=AsyncMock(return_value={}),
            update_session_state=AsyncMock(),
        ),
        _get_expert_main_execution=Mock(
            return_value=object() if expert else None,
        ),
    )
    context = _CommandRequestContext("session", "user", "chat", "console")
    output = [
        item
        async for item in _run_conversation_command(
            "/compact",
            SimpleNamespace(),
            context,
            runner,
        )
    ]
    assert output
    manager.compact_memory.assert_awaited_once_with(
        messages=messages,
        previous_summary="old Chat summary",
    )
    memory.update_compressed_summary.assert_awaited_once_with(
        "new Chat summary",
    )
    if expert:
        manager.add_async_summary_task.assert_not_called()
    else:
        manager.add_async_summary_task.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["/long_term_memory", "/await_summary"])
async def test_expert_commands_do_not_read_profile_long_term_memory(command):
    memory = SimpleNamespace(
        load_state_dict=Mock(),
        _long_term_memory="secret",
    )
    runner = SimpleNamespace(
        memory_manager=SimpleNamespace(
            get_in_memory_memory=Mock(return_value=memory),
        ),
        session=SimpleNamespace(
            get_session_state_dict=AsyncMock(return_value={}),
        ),
        _get_expert_main_execution=Mock(return_value=object()),
    )
    context = _CommandRequestContext("session", "user", "chat", "console")
    output = [
        item
        async for item in _run_conversation_command(
            command,
            SimpleNamespace(),
            context,
            runner,
        )
    ]
    assert "secret" not in str(output)
    assert "Profile" in str(output)


@pytest.mark.asyncio
async def test_expert_reset_does_not_summarize_into_profile():
    messages = [Msg("user", "expert conversation", "user")]
    memory = SimpleNamespace(
        load_state_dict=Mock(),
        get_memory=AsyncMock(return_value=messages),
        clear_content=Mock(),
        clear_compressed_summary=Mock(),
        state_dict=Mock(return_value={}),
    )
    manager = SimpleNamespace(
        agent_id="profile",
        get_in_memory_memory=Mock(return_value=memory),
        add_async_summary_task=Mock(),
        reset_context_epoch=AsyncMock(),
    )
    runner = SimpleNamespace(
        memory_manager=manager,
        _get_expert_main_execution=Mock(return_value=None),
        session=SimpleNamespace(
            get_session_state_dict=AsyncMock(return_value={}),
            update_session_state=AsyncMock(),
        ),
    )
    request = SimpleNamespace(channel_meta={"_expert_main_reset": True})
    context = _CommandRequestContext("session", "user", "chat", "console")
    output = [
        item
        async for item in _run_conversation_command(
            "/new",
            request,
            context,
            runner,
        )
    ]
    assert output
    manager.add_async_summary_task.assert_not_called()
    memory.clear_content.assert_called_once()
