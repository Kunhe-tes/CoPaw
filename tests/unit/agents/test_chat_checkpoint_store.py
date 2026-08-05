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
    source_message_ids: tuple[str, ...] = (),
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
        source_message_ids=source_message_ids,
    )


def test_evidence_query_matches_exact_reference_before_filters(
    tmp_path: Path,
) -> None:
    store = ConversationArchiveStore(tmp_path / "dialog")
    message = _message(1)

    assert store._matches_evidence_query(
        message,
        requested={"message:1"},
        semantic_query="does not match",
        kind_filter={"assistant"},
        time_bounds=None,
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
        source_message_ids=("message:1",),
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
async def test_commit_checkpoint_rejects_messages_outside_candidate_prefix(
    tmp_path: Path,
) -> None:
    chat_id = _chat_id()
    store = ConversationArchiveStore(tmp_path / "dialog")
    candidate = replace(
        _candidate(chat_id, base_revision=0, applied_event_sequence=0),
        source_message_ids=("message:1",),
    )
    await store.write_pending_candidate(chat_id, candidate)

    with pytest.raises(ValueError, match="source message prefix"):
        await store.commit_checkpoint(chat_id, [_message(2)], candidate.id)


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


@pytest.mark.asyncio
async def test_new_epoch_closes_current_task_into_completed_index(
    tmp_path: Path,
) -> None:
    chat_id = _chat_id()
    store = ConversationArchiveStore(tmp_path / "dialog")
    record = CheckpointRecord.new(chat_id=chat_id, epoch=1).with_current_task(
        "finish compaction",
        (),
        evidence_refs=("message:1",),
    )
    await store.write_active_checkpoint(chat_id, record)

    state = await store.reset_checkpoint_epoch(chat_id, reason="new")

    assert state.record.completed_task_index[0].title == "finish compaction"
    assert state.record.completed_task_index[0].evidence_refs == ("message:1",)


@pytest.mark.asyncio
async def test_checkpoint_commit_rolls_back_activation_when_manifest_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id = _chat_id()
    store = ConversationArchiveStore(tmp_path / "dialog")
    candidate = _candidate(
        chat_id,
        base_revision=0,
        applied_event_sequence=0,
        source_message_ids=("message:1",),
    )
    await store.write_pending_candidate(chat_id, candidate)
    original_replace_manifest = store._replace_manifest
    failed = False

    def fail_once(*args: object, **kwargs: object) -> None:
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("injected manifest failure")
        original_replace_manifest(*args, **kwargs)

    monkeypatch.setattr(store, "_replace_manifest", fail_once)

    with pytest.raises(OSError, match="injected manifest failure"):
        await store.commit_checkpoint(chat_id, [_message(1)], candidate.id)

    assert (await store.read_checkpoint_state(chat_id)).record.revision == 0
    result = await store.commit_checkpoint(
        chat_id,
        [_message(1)],
        candidate.id,
    )
    assert result.record.revision == 1


@pytest.mark.asyncio
async def test_reset_rolls_back_epoch_metadata_when_checkpoint_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id = _chat_id()
    store = ConversationArchiveStore(tmp_path / "dialog")
    await store.write_active_checkpoint(
        chat_id,
        CheckpointRecord.new(chat_id=chat_id, epoch=1),
    )
    original_write_checkpoint = store._write_checkpoint_locked

    def fail_new_epoch(chat: str, record: CheckpointRecord) -> None:
        if record.epoch == 2:
            raise OSError("injected checkpoint failure")
        original_write_checkpoint(chat, record)

    monkeypatch.setattr(store, "_write_checkpoint_locked", fail_new_epoch)

    with pytest.raises(OSError, match="injected checkpoint failure"):
        await store.reset_checkpoint_epoch(chat_id, reason="clear")

    state = await store.read_checkpoint_state(chat_id)
    assert state.current_epoch == 1
    assert state.record.epoch == 1


@pytest.mark.asyncio
async def test_recovery_uses_archive_location_not_reused_message_id(
    tmp_path: Path,
) -> None:
    chat_id = _chat_id()
    store = ConversationArchiveStore(tmp_path / "dialog")
    await store.commit(chat_id, [_message(7)])
    await store.reset_checkpoint_epoch(chat_id, reason="new")
    await store.commit(chat_id, [_message(7)])

    recovered = await store.recover_evidence(
        chat_id,
        epoch=2,
        refs=["message:7"],
    )

    assert [message.id for message in recovered] == ["message:7"]
    assert len(recovered) == 1


@pytest.mark.asyncio
async def test_legacy_epoch_one_archive_remains_recoverable(
    tmp_path: Path,
) -> None:
    chat_id = _chat_id()
    store = ConversationArchiveStore(tmp_path / "dialog")
    await store.commit(chat_id, [_message(3)])
    (store.path_for(chat_id) / "evidence-epochs.json").unlink()

    recovered = await store.recover_evidence(
        chat_id,
        epoch=1,
        refs=["message:3"],
    )

    assert [message.id for message in recovered] == ["message:3"]


@pytest.mark.asyncio
async def test_recovery_filters_current_epoch_evidence_by_query_kind_and_time(
    tmp_path: Path,
) -> None:
    chat_id = _chat_id()
    store = ConversationArchiveStore(tmp_path / "dialog")
    matching = _message(1)
    matching.role = "assistant"
    matching.content = "Needle: retained deployment failure"
    matching.timestamp = "2026-08-01T12:00:00+00:00"
    other = _message(2)
    other.role = "user"
    other.content = "needle but not assistant"
    other.timestamp = "2026-08-02T12:00:00+00:00"
    await store.commit(chat_id, [matching, other])

    recovered = await store.recover_evidence(
        chat_id,
        epoch=1,
        refs=[],
        query="NEEDLE",
        kinds=["assistant"],
        time_range="2026-08-01T00:00:00+00:00/2026-08-01T23:59:59+00:00",
        limit=1,
    )

    assert [message.id for message in recovered] == ["message:1"]


@pytest.mark.asyncio
async def test_exact_reference_takes_precedence_over_semantic_query(
    tmp_path: Path,
) -> None:
    chat_id = _chat_id()
    store = ConversationArchiveStore(tmp_path / "dialog")
    message = _message(1)
    message.content = "retained failure evidence"
    await store.commit(chat_id, [message])

    recovered = await store.recover_evidence(
        chat_id,
        epoch=1,
        refs=["message:1"],
        query="does not match",
        kinds=["assistant"],
        limit=1,
    )

    assert [item.id for item in recovered] == ["message:1"]
