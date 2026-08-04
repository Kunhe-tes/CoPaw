# -*- coding: utf-8 -*-
"""Chat checkpoint attachment coverage for ReMe-compatible memory."""

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agentscope.message import Msg

from swe.agents.memory.chat_checkpoint import CheckpointRecord
from swe.agents.memory.conversation_archive import attach_conversation_archive


def _chat_id() -> str:
    return str(uuid4())


def _message(index: int) -> Msg:
    message = Msg(
        name="user",
        role="user",
        content=f"message-{index}",
        timestamp=f"2026-08-01 12:00:{index:02d}.000",
    )
    message.id = f"message-{index}"
    return message


def _memory() -> SimpleNamespace:
    memory = SimpleNamespace(content=[], _compressed_summary="")

    async def add(message: Msg) -> None:
        memory.content.append((message, []))

    async def get_memory(*, prepend_summary: bool = True) -> list[Msg]:
        del prepend_summary
        return [message for message, _marks in memory.content]

    memory.add = add
    memory.get_memory = get_memory

    def clear_content() -> None:
        memory.content.clear()

    memory.clear_content = clear_content

    def clear_compressed_summary() -> None:
        memory._compressed_summary = ""

    memory.clear_compressed_summary = clear_compressed_summary
    return memory


@pytest.mark.asyncio
async def test_attached_memory_appends_event_after_message_storage(
    tmp_path: Path,
) -> None:
    chat_id = _chat_id()
    memory = _memory()
    attach_conversation_archive(memory, tmp_path / "dialog", chat_id)
    message = _message(1)

    await memory.add(message)

    state = await memory.chat_checkpoint_store.read_checkpoint_state(chat_id)
    assert state.events[-1].source_refs == (f"message:{message.id}",)
    assert state.events[-1].facts == {
        "message_id": message.id,
        "role": "user",
    }


@pytest.mark.asyncio
async def test_projection_exposes_markdown_not_checkpoint_json(
    tmp_path: Path,
) -> None:
    chat_id = _chat_id()
    memory = _memory()
    attach_conversation_archive(memory, tmp_path / "dialog", chat_id)
    record = CheckpointRecord.new(chat_id=chat_id, epoch=1).with_current_task(
        "keep API stable",
        (),
        evidence_refs=("message:1",),
    )

    await memory.install_checkpoint_projection(record)

    assert "## 目标" in memory._compressed_summary
    assert '"schema_version"' not in memory._compressed_summary


@pytest.mark.asyncio
async def test_clear_wrappers_preserve_original_memory_operations(
    tmp_path: Path,
) -> None:
    chat_id = _chat_id()
    memory = _memory()
    attach_conversation_archive(memory, tmp_path / "dialog", chat_id)
    await memory.add(_message(1))

    memory.clear_content()
    memory.clear_compressed_summary()

    assert memory.content == []
    assert memory._compressed_summary == ""
    assert callable(memory._checkpoint_original_add)
    assert callable(memory._checkpoint_original_get_memory)
