# -*- coding: utf-8 -*-
"""Tests for the pure, recoverable Chat Checkpoint model."""

from dataclasses import replace
from uuid import uuid4

from swe.agents.memory.chat_checkpoint import (
    CheckpointEvent,
    CheckpointRecord,
    PrecompactionCandidate,
    render_checkpoint_projection,
    validate_precompaction_candidate,
    validate_checkpoint_record,
    validate_checkpoint_update,
)

CHAT_ID = str(uuid4())


def _event(
    sequence: int,
    event_type: str = "tool_completed",
    **facts: object,
) -> CheckpointEvent:
    return CheckpointEvent.new(
        sequence=sequence,
        epoch=1,
        type=event_type,
        facts=facts,
        source_refs=(f"message:{sequence}",),
    )


def test_projection_keeps_six_reme_sections_and_recent_delta() -> None:
    record = CheckpointRecord.new(chat_id=CHAT_ID, epoch=1).with_current_task(
        "Refactor compaction",
        ["Focused tests pass"],
        evidence_refs=("message:1",),
    )

    text = render_checkpoint_projection(
        record,
        [_event(2, exit_code=1)],
    )

    for heading in (
        "## 目标",
        "## 约束和偏好",
        "## 进展",
        "## 关键决策",
        "## 下一步",
        "## 关键上下文",
    ):
        assert heading in text
    assert "## Recent Event Delta" in text
    assert "tool_completed" in text
    assert "message:2" in text


def test_validator_rejects_done_progress_without_evidence() -> None:
    invalid = CheckpointRecord.new(chat_id=CHAT_ID, epoch=1).with_progress(
        "done",
        "changed config",
        (),
    )

    assert validate_checkpoint_record(invalid).errors == [
        "progress.done[0] requires evidence",
    ]


def test_candidate_cannot_mark_work_done_without_new_evidence() -> None:
    previous = CheckpointRecord.new(chat_id=CHAT_ID, epoch=1).with_progress(
        "in_progress",
        "run regression",
        ("message:1",),
    )
    candidate = replace(
        previous,
        progress=replace(
            previous.progress,
            done=(previous.progress.in_progress[0].with_status("done"),),
            in_progress=(),
        ),
    )

    assert (
        "unsupported progress transition"
        in validate_checkpoint_update(
            previous,
            candidate,
        ).errors
    )


def test_checkpoint_json_is_canonical_and_events_cannot_embed_raw_tool_output() -> (
    None
):
    record = CheckpointRecord.new(chat_id=CHAT_ID, epoch=1).with_current_task(
        "Keep evidence recoverable",
        (),
        evidence_refs=("message:1",),
    )

    assert record.to_json() == record.to_json()
    invalid_event = _event(2, raw_tool_output="secret")
    assert validate_checkpoint_record(record, [invalid_event]).errors == [
        "event[0].facts must not contain raw_tool_output",
    ]


def test_candidate_requires_the_current_record_revision() -> None:
    active = CheckpointRecord.new(chat_id=CHAT_ID, epoch=1)
    candidate_record = replace(active, revision=1)
    candidate = PrecompactionCandidate.new(
        record=candidate_record,
        base_revision=active.revision + 1,
        applied_event_sequence=active.applied_event_sequence,
    )

    assert (
        "candidate base revision is stale"
        in validate_precompaction_candidate(
            candidate,
            active,
            current_event_sequence=active.applied_event_sequence,
        ).errors
    )
