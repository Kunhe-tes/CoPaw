# -*- coding: utf-8 -*-
"""Expert main retains Chat compaction without Profile memory access."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from agentscope.message import Msg
from reme.memory.file_based.reme_in_memory_memory import ReMeInMemoryMemory

from swe.agents.hooks.memory_compaction import MemoryCompactionHook
from swe.agents.memory.expert_main_memory import ExpertMainMemoryManager
from swe.agents.memory.reme_light_memory_manager import ReMeLightMemoryManager
from swe.config.config import AgentProfileConfig, ToolResultCompactConfig


def chat_only_manager(tmp_path):
    manager = object.__new__(ReMeLightMemoryManager)
    manager.agent_id = "profile"
    manager.tenant_id = "tenant"
    manager.working_dir = str(tmp_path)
    manager._warn_if_version_mismatch = Mock()
    manager._load_agent_config = Mock(
        return_value=AgentProfileConfig(id="profile", name="Profile"),
    )
    raw_memory = ReMeInMemoryMemory(token_counter=Mock())
    raw_memory._long_term_memory = "PRIVATE PROFILE MEMORY"
    manager._reme = SimpleNamespace(
        get_in_memory_memory=Mock(return_value=raw_memory),
        memory_search=AsyncMock(),
    )
    manager.add_async_summary_task = Mock()
    return manager, ExpertMainMemoryManager(manager)


@pytest.mark.asyncio
async def test_expert_chat_memory_restores_summary_and_commits_checkpoint(
    tmp_path,
):
    manager, facade = chat_only_manager(tmp_path)
    chat_id = str(uuid4())
    memory = facade.create_request_memory(chat_id)
    memory.load_state_dict(
        {"content": [], "_compressed_summary": "previous Chat summary"},
    )
    assert memory.get_compressed_summary() == "previous Chat summary"
    messages = [Msg("user", "old Chat turn", "user")]
    await memory.add(messages[0])
    assert await facade.schedule_precompaction(
        chat_id=chat_id,
        watermark=0,
        messages=messages,
        memory=memory,
    )
    assert await facade.install_ready_precompaction(
        chat_id=chat_id,
        messages=messages,
        memory=memory,
    )
    page = await memory.conversation_archive_store.read_page(chat_id)
    assert page.boundaries[0].archived_message_count == 1
    assert await memory.get_memory(prepend_summary=False) == []
    assert memory.get_compressed_summary()
    assert "PRIVATE PROFILE MEMORY" not in str(await memory.get_memory())
    assert not hasattr(facade, "memory_search")
    manager._reme.memory_search.assert_not_awaited()
    manager.add_async_summary_task.assert_not_called()


@pytest.mark.asyncio
async def test_expert_automatic_compaction_archives_without_profile_summary(
    tmp_path,
    monkeypatch,
):
    manager, facade = chat_only_manager(tmp_path)
    chat_id = str(uuid4())
    memory = facade.create_request_memory(chat_id)
    message = Msg("user", "compact this Chat turn", "user")
    await memory.add(message)
    manager.check_context = AsyncMock(return_value=([message], [], True))
    manager.compact_memory = AsyncMock(return_value="new Chat summary")
    running = SimpleNamespace(
        memory_compact_threshold=1,
        memory_compact_reserve=0,
        tool_result_compact=ToolResultCompactConfig(enabled=False),
        memory_summary=SimpleNamespace(memory_summary_enabled=True),
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
        name="expert",
        sys_prompt="",
        memory=memory,
        model=object(),
        formatter=object(),
        print=AsyncMock(),
        _request_context={"chat_id": chat_id},
    )
    await MemoryCompactionHook(facade)(agent, {})
    assert await memory.get_memory(prepend_summary=False) == []
    assert memory.get_compressed_summary() == "new Chat summary"
    page = await memory.conversation_archive_store.read_page(chat_id)
    assert page.boundaries[0].archived_message_count == 1
    manager.compact_memory.assert_awaited_once_with(
        messages=[message],
        previous_summary="",
        _bound_chat_model=agent.model,
        _bound_formatter=agent.formatter,
    )
    manager.add_async_summary_task.assert_not_called()
    manager._reme.memory_search.assert_not_awaited()
    assert (
        agent.print.await_args.args[0].metadata[
            "conversation_compaction_boundary"
        ]["archived_message_count"]
        == 1
    )
