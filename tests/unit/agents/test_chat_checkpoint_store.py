# -*- coding: utf-8 -*-
"""Transactional persistence coverage for Chat Checkpoints."""

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from agentscope.message import Msg

from swe.agents.memory.chat_checkpoint import (
    CheckpointEvent,
    CheckpointRecord,
    PrecompactionCandidate,
)
from swe.agents.memory.conversation_archive import ConversationArchiveStore


def _chat_id() -> str:
    return str(uuid4())


def _message(index: int) -> Msg:
    message = Msg(
        name="user",
        role="user",
        content=f"message-{index}",
        timestamp=f"2026-08-01 12:00:{index:02d}.000",
    )
    message.id = f"message:{index}"
    return message


def _event(sequence: int, *, epoch: int = 1) -> CheckpointEvent:
    return CheckpointEvent.new(
        sequence=sequence,
        epoch=epoch,
        type="message_added",
        facts={"message_id": f"message:{sequence}", "role": "user"},
        source_refs=(f"message:{sequence}",),
    )


def _candidate(
    chat_id: str,
    *,
    base_revision: int,
    applied_event_sequence: int,
    epoch: int = 1,
) -> PrecompactionCandidate:
    base = replace(
        CheckpointRecord.new(chat_id=chat_id, epoch=epoch),
        revision=base_revision,
        source_revision=max(base_revision - 1, 0),
    )
    record = replace(
        base,
        revision=base_revision + 1,
        source_revision=base_revision,
        applied_event_sequence=applied_event_sequence,
    )
    return PrecompactionCandidate.new(
        record=record,
        base_revision=base_revision,
        applied_event_sequence=applied_event_sequence,
    )


@pytest.mark.asyncio
async def test_commit_checkpoint_archives_messages_and_activates_candidate(
    tmp_path: Path,
) -> None:
    chat_id = _chat_id()
    store = ConversationArchiveStore(tmp_path / "dialog")
    await store.append_checkpoint_event(chat_id, _event(1))
    candidate = _candidate(
        chat_id,
        base_revision=0,
        applied_event_sequence=1,
    )
    await store.write_pending_candidate(chat_id, candidate)

    result = await store.commit_checkpoint(
        chat_id,
        [_message(1)],
        candidate.id,
    )

    assert result.record.revision == 1
    assert result.boundary.last_message_id == "message:1"
    assert (tmp_path / "dialog" / chat_id / "checkpoint.json").is_file()
    assert (await store.read_checkpoint_state(chat_id)).events == ()


@pytest.mark.asyncio
async def test_old_revision_candidate_is_not_activated(tmp_path: Path) -> None:
    chat_id = _chat_id()
    store = ConversationArchiveStore(tmp_path / "dialog")
    await store.write_active_checkpoint(
        chat_id,
        replace(
            CheckpointRecord.new(chat_id=chat_id, epoch=1),
            revision=2,
            source_revision=1,
        ),
    )
    await store.write_pending_candidate(
        chat_id,
        _candidate(chat_id, base_revision=1, applied_event_sequence=0),
    )

    assert await store.install_ready_candidate(chat_id) is None


@pytest.mark.asyncio
async def test_reset_blocks_default_recovery_and_delete_removes_checkpoint_files(
    tmp_path: Path,
) -> None:
    chat_id = _chat_id()
    store = ConversationArchiveStore(tmp_path / "dialog")
    await store.commit(chat_id, [_message(1)])
    await store.append_checkpoint_event(chat_id, _event(1))

    state = await store.reset_checkpoint_epoch(chat_id, reason="clear")

    assert state.current_epoch == 2
    assert (
        await store.recover_evidence(
            chat_id,
            epoch=2,
            refs=["message:1"],
        )
        == []
    )
    await store.delete_chat(chat_id)
    assert not store.path_for(chat_id).exists()
