# -*- coding: utf-8 -*-
"""Request-owned ReMe memory lease coverage."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from agentscope.message import Msg

from swe.agents.memory.reme_light_memory_manager import ReMeLightMemoryManager


def _request_memory() -> SimpleNamespace:
    memory = SimpleNamespace(content=[], _compressed_summary="")

    async def add(message: Msg) -> None:
        memory.content.append((message, []))

    async def get_memory(*, prepend_summary: bool = True) -> list[Msg]:
        del prepend_summary
        return [message for message, _marks in memory.content]

    memory.add = add
    memory.get_memory = get_memory
    memory.clear_content = memory.content.clear
    memory.clear_compressed_summary = lambda: setattr(
        memory,
        "_compressed_summary",
        "",
    )
    return memory


@pytest.mark.asyncio
async def test_same_chat_receives_fresh_blank_request_memory(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A backend singleton cannot leak live state into a later request."""
    backend_memory = _request_memory()
    manager = object.__new__(ReMeLightMemoryManager)
    manager.agent_id = "default"
    manager.tenant_id = None
    manager.working_dir = str(tmp_path)
    manager._warn_if_version_mismatch = lambda: None
    manager._reme = SimpleNamespace(
        get_in_memory_memory=lambda **_kwargs: backend_memory,
    )
    monkeypatch.setattr(
        "swe.agents.memory.reme_light_memory_manager.load_agent_config",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "swe.agents.memory.reme_light_memory_manager.get_swe_token_counter",
        lambda _config: object(),
    )
    chat_id = str(uuid4())

    first = manager.create_request_memory(chat_id)
    message = Msg(name="user", role="user", content="old request")
    message.id = "old-request"
    await first.add(message)
    first._compressed_summary = "old summary"

    second = manager.create_request_memory(chat_id)

    assert second is not first
    assert second.content == []
    assert second._compressed_summary == ""
    assert second._chat_checkpoint_chat_id == chat_id


def test_legacy_memory_lookup_without_chat_id_returns_isolated_clone(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend_memory = _request_memory()
    manager = object.__new__(ReMeLightMemoryManager)
    manager.agent_id = "default"
    manager.tenant_id = None
    manager.working_dir = str(tmp_path)
    manager._warn_if_version_mismatch = lambda: None
    manager._reme = SimpleNamespace(
        get_in_memory_memory=lambda **_kwargs: backend_memory,
    )
    monkeypatch.setattr(
        "swe.agents.memory.reme_light_memory_manager.load_agent_config",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "swe.agents.memory.reme_light_memory_manager.get_swe_token_counter",
        lambda _config: object(),
    )

    first = manager.get_in_memory_memory()
    second = manager.get_in_memory_memory()

    assert first is not backend_memory
    assert second is not backend_memory
    assert second is not first
    assert first.content == second.content == []


@pytest.mark.asyncio
async def test_checkpoint_install_uses_callers_active_memory(
    tmp_path,
) -> None:
    """Checkpoint install must never reacquire online memory by Chat ID."""
    manager = object.__new__(ReMeLightMemoryManager)
    manager.get_in_memory_memory = lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("online memory lookup is forbidden"),
    )
    memory = SimpleNamespace(
        commit_ready_precompaction=AsyncMock(return_value=True),
    )
    message = Msg(name="user", role="user", content="m1")
    message.id = "m1"

    assert await manager.install_ready_precompaction(
        chat_id=str(uuid4()),
        memory=memory,
        messages=[message],
    )
    memory.commit_ready_precompaction.assert_awaited_once_with([message])


@pytest.mark.asyncio
async def test_missing_session_does_not_resurrect_old_request_memory(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Removing a session file cannot make a later request reuse old memory."""
    backend_memory = _request_memory()
    manager = object.__new__(ReMeLightMemoryManager)
    manager.agent_id = "default"
    manager.tenant_id = None
    manager.working_dir = str(tmp_path)
    manager._warn_if_version_mismatch = lambda: None
    manager._reme = SimpleNamespace(
        get_in_memory_memory=lambda **_kwargs: backend_memory,
    )
    monkeypatch.setattr(
        "swe.agents.memory.reme_light_memory_manager.load_agent_config",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "swe.agents.memory.reme_light_memory_manager.get_swe_token_counter",
        lambda _config: object(),
    )
    session_file = tmp_path / "sessions" / "session.json"
    session_file.parent.mkdir()
    session_file.write_text('{"agent": {"memory": {"content": []}}}')
    chat_id = str(uuid4())
    old = manager.create_request_memory(chat_id)
    old_message = Msg(name="user", role="user", content="old")
    old_message.id = "old"
    await old.add(old_message)
    session_file.unlink()

    new = manager.create_request_memory(chat_id)
    new_message = Msg(name="user", role="user", content="new")
    new_message.id = "new"
    await new.add(new_message)

    assert [message.id for message, _marks in old.content] == ["old"]
    assert [message.id for message, _marks in new.content] == ["new"]
