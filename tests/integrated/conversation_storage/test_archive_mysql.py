# -*- coding: utf-8 -*-
"""Archive transactions verified against disposable real MySQL schemas."""

from dataclasses import replace
from datetime import datetime, timezone
import json

from agentscope.message import Msg
import pytest

from swe.agents.memory.chat_checkpoint import CheckpointEvent, CheckpointRecord
from swe.app.conversation_storage.archive import (
    ArchiveInstall,
    CheckpointInstall,
    EventInstall,
    ContextReset,
)
from swe.app.conversation_storage.bundle import (
    BundleStore,
    BundleBlock,
    new_operation_key,
)
from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.conversation_storage.publications import (
    CommitPlan,
    PublicationRequest,
    PublicationStore,
)
from swe.app.conversation_storage.errors import (
    ConflictError,
    IntegrityError,
    UnknownCommit,
)
from tests.integrated.conversation_storage.test_schema import (
    insert_session,
    insert_chat,
    insert_row,
)
from tests.integrated.conversation_storage.test_publications_mysql import (
    InstallFailureDatabase,
)

STAMP = "2026-10-30T00:00:01Z"


def payload(key, role, content):
    value = Msg(role, content, role, timestamp=STAMP).to_dict()
    value["id"] = key
    value["metadata"]["unknown_original_field"] = {"preserve": True}
    return value


def block(name, kind, value):
    return BundleBlock(name, kind, json.dumps(value).encode())


async def seed(db, root):
    session = await insert_session(db)
    first = await insert_chat(db, session, b"first", epoch=1)
    second = await insert_chat(
        db,
        session,
        b"second",
        registry_order=2,
        epoch=1,
    )
    return (
        session,
        first,
        second,
        PublicationStore(
            db,
            BundleStore(root),
            service_unit_id="schema-test-service",
        ),
    )


async def operation(db, session, chat, kind="state"):
    s = await db.fetch_one(
        "SELECT * FROM swe_conversation_sessions WHERE id=%s",
        (session,),
    )
    c = await db.fetch_one(
        "SELECT * FROM swe_conversation_chats WHERE id=%s",
        (chat,),
    )
    return PublicationRequest(
        new_operation_key(),
        WorkspaceScope(
            "tenant",
            "source",
            "agent",
            service_unit_id="schema-test-service",
        ),
        kind,
        "owner",
        s["generation"],
        session_id=session,
        chat_id=chat,
        base_state_revision=s["state_revision"],
        base_history_revision=c["history_revision"],
        epoch=c["epoch"],
    )


async def append_sources(db, root):
    from tests.integrated.conversation_storage.test_archive_runtime_mysql import (
        setup,
        source,
    )

    session, chat, second_chat, store = await setup(db, root)
    state = {"revision": 0, "unknown": {"keep": True}}
    messages = [source("q", "question"), source("a", "answer")]
    for message in messages:
        state = (
            await store.append_message(
                "first",
                message,
                recovery_state=state,
                authority=None,
            )
        ).recovery_state
    rows = await store.reader.session_messages(session, layers=("memory",))
    return session, chat, second_chat, store, messages, rows, state


async def archive_sources(db, root):
    from tests.integrated.conversation_storage.test_archive_runtime_mysql import (
        setup,
        source,
    )

    session, chat, second_chat, store = await setup(db, root)
    state = {"revision": 0}
    messages = [source("q", "question"), source("a", "answer")]
    for message in messages:
        state = (
            await store.append_message(
                "first",
                message,
                recovery_state=state,
                authority=None,
            )
        ).recovery_state
    rows = await store.reader.session_messages(session, layers=("memory",))
    return session, chat, second_chat, store, messages, rows, state


def compact_plan(
    chat,
    rows,
    *,
    turn_id=None,
    reuse=True,
    event_sequence=1,
    event_watermark=1,
):
    from swe.app.conversation_storage.message_installs import MessageInstall

    messages = tuple(
        MessageInstall(
            name,
            "archive",
            _text(row["role_key"]),
            source_msg_key=_text(row["source_msg_key"]),
            archive_chat_id=chat,
            origin_chat_id=row["origin_chat_id"],
            turn_id=row.get("turn_id") if turn_id is None else turn_id,
            context_epoch=row["context_epoch"],
            message_timestamp=(
                row["message_timestamp"]
                .replace(tzinfo=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
                if row["message_timestamp"]
                else None
            ),
            source_message_id=row["id"] if reuse else None,
        )
        for name, row in zip(("old-q", "old-a"), rows)
    )
    return CommitPlan(
        recovery_block="root",
        messages=messages,
        archive=ArchiveInstall(
            "boundary",
            "archive_manifest",
            2,
            2,
            rows[0]["source_msg_key"].decode(),
            rows[-1]["source_msg_key"].decode(),
            messages[0].message_timestamp,
            messages[-1].message_timestamp,
        ),
        checkpoint=CheckpointInstall(
            "checkpoint",
            0,
            1,
            event_watermark,
            len(rows),
        ),
        events=EventInstall(
            "events",
            event_sequence,
            event_sequence,
        ),
        prune_ids=tuple(row["id"] for row in rows),
    )


def _text(value):
    return value.decode() if isinstance(value, (bytes, bytearray)) else value


def compact_blocks(*, checkpoint=None, events=None):
    record = replace(
        CheckpointRecord.new(chat_id="first", epoch=1),
        revision=1,
        applied_event_sequence=2,
        archived_through="a",
    )
    event = CheckpointEvent.new(
        sequence=3,
        epoch=1,
        type="messages_archived",
        source_refs=("message:q", "message:a"),
    )
    return [
        block(
            "root",
            "recovery",
            {"all_modules": {"keep": True}, "compacted": True},
        ),
        block("archive_manifest", "archive_manifest", {}),
        block(
            "checkpoint",
            "checkpoint",
            record.to_dict() if checkpoint is None else checkpoint,
        ),
        block(
            "events",
            "events",
            [event.to_dict()] if events is None else events,
        ),
    ]


async def test_compact_checkpoint_events_root_and_visibility_commit_together(
    conversation_test_database,
    tmp_path,
):
    from swe.app.conversation_storage.archive_bundle_reader import (
        read_archive_bundle,
    )

    db = conversation_test_database
    session, first, second, store, _messages, rows, state = (
        await archive_sources(
            db,
            tmp_path,
        )
    )
    request = await operation(db, session, first, "compact")
    plan = compact_plan(first, rows, event_sequence=3, event_watermark=2)
    checkpoint = replace(
        CheckpointRecord.new(chat_id="first", epoch=1),
        revision=1,
        applied_event_sequence=2,
        archived_through="a",
    )
    event = CheckpointEvent.new(
        sequence=3,
        epoch=1,
        type="messages_archived",
        facts={"boundary_id": "boundary"},
        source_refs=("message:q", "message:a"),
    )
    await store.publications.reserve(request, plan)
    await store.publications.write_bundle(
        request.operation_key,
        [
            block("root", "recovery", state),
            block("checkpoint", "checkpoint", checkpoint.to_dict()),
            block("events", "events", [event.to_dict()]),
        ],
        plan=plan,
    )
    publication = await store.publications.commit(request.operation_key)
    assert publication["archive_first_order"] == 1
    assert publication["archive_last_order"] == 2
    archived = await read_archive_bundle(
        db,
        store.scope,
        store.bundles,
        publication,
    )
    try:
        assert [entry["raw_id"] for entry in archived.entries] == ["q", "a"]
        assert [entry["message"]["content"] for entry in archived.entries] == [
            "question",
            "answer",
        ]
    finally:
        await archived.pins.finish()
    chat = await db.fetch_one(
        "SELECT * FROM swe_conversation_chats WHERE id=%s",
        (first,),
    )
    other = await db.fetch_one(
        "SELECT * FROM swe_conversation_chats WHERE id=%s",
        (second,),
    )
    assert chat["active_checkpoint_publication_id"] == publication["id"]
    assert chat["history_high"] == 2 and other["history_high"] == 0
    assert (
        await store.reader.session_messages(session, layers=("memory",))
    ) == []


async def test_reset_advances_epochs_and_keeps_historical_occurrences(
    conversation_test_database,
    tmp_path,
):
    from tests.integrated.conversation_storage.test_archive_runtime_mysql import (
        setup,
        source,
    )

    db = conversation_test_database
    session, first, _, store = await setup(db, tmp_path)
    message = source("q", "question")
    state = (
        await store.append_message(
            "first",
            message,
            recovery_state={"revision": 0},
            authority=None,
        )
    ).recovery_state
    old = await db.fetch_one(
        "SELECT recovery_publication_id FROM swe_conversation_sessions WHERE id=%s",
        (session,),
    )
    await store.reset(
        "first",
        recovery_state=state,
        authority=None,
        reason="clear",
    )
    current = await db.fetch_one(
        "SELECT * FROM swe_conversation_sessions WHERE id=%s",
        (session,),
    )
    chat = await db.fetch_one(
        "SELECT * FROM swe_conversation_chats WHERE id=%s",
        (first,),
    )
    assert current["context_epoch"] == 1 and chat["epoch"] == 2
    assert current["recovery_publication_id"] != old["recovery_publication_id"]
    assert await store.reader.session_messages(session) == []
    assert await db.fetch_one(
        "SELECT id FROM swe_conversation_publications WHERE id=%s",
        (old["recovery_publication_id"],),
    )


async def test_failed_archive_install_rolls_back_all_metadata_and_visibility(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, first, _, store, _messages, rows, state = await archive_sources(
        db,
        tmp_path,
    )
    before = await db.fetch_one(
        "SELECT * FROM swe_conversation_sessions WHERE id=%s",
        (session,),
    )
    original_commit = store.publications.commit

    async def fail_commit(operation_key):
        fault = PublicationStore(
            InstallFailureDatabase(db),
            store.bundles,
            service_unit_id=store.scope.service_unit_id,
        )
        return await fault.commit(operation_key)

    store.publications.commit = fail_commit
    with pytest.raises(UnknownCommit):
        request = await operation(db, session, first, "compact")
        plan = compact_plan(first, rows, event_sequence=3, event_watermark=2)
        await store.publications.reserve(request, plan)
        blocks = compact_blocks()
        checkpoint = replace(
            CheckpointRecord.new(chat_id="first", epoch=1),
            revision=1,
            applied_event_sequence=2,
            archived_through="a",
        )
        events = [
            CheckpointEvent.new(
                sequence=3,
                epoch=1,
                type="messages_archived",
                facts={"boundary_id": "boundary"},
                source_refs=("message:q", "message:a"),
            ),
        ]
        await store.publications.write_bundle(
            request.operation_key,
            [
                *[
                    item
                    for item in blocks
                    if item.name not in ("checkpoint", "events")
                ],
                block("checkpoint", "checkpoint", checkpoint.to_dict()),
                block("events", "events", [item.to_dict() for item in events]),
            ],
            plan=plan,
        )
        await store.publications.commit(request.operation_key)
    store.publications.commit = original_commit
    after = await db.fetch_one(
        "SELECT * FROM swe_conversation_sessions WHERE id=%s",
        (session,),
    )
    chat = await db.fetch_one(
        "SELECT * FROM swe_conversation_chats WHERE id=%s",
        (first,),
    )
    assert (
        after["recovery_publication_id"] == before["recovery_publication_id"]
    )
    assert after["state_revision"] == before["state_revision"]
    assert chat["history_high"] == 0
    assert [
        item["raw_id"] for item in await store.reader.session_messages(session)
    ] == ["q", "a"]


@pytest.mark.parametrize(
    "damage",
    [
        "checkpoint_schema",
        "checkpoint_epoch",
        "checkpoint_revision",
        "checkpoint_watermark",
        "checkpoint_chat",
        "event_empty",
        "event_gap",
        "event_epoch",
        "event_duplicate",
        "batch",
        "display_count",
        "timestamp",
        "role",
    ],
)
async def test_invalid_immutable_archive_payload_never_installs(
    conversation_test_database,
    tmp_path,
    damage,
):
    from tests.integrated.conversation_storage.test_archive_runtime_mysql import (
        setup,
    )

    db = conversation_test_database
    session, first, _, runtime = await setup(db, tmp_path)
    rows = [
        {
            "id": index,
            "source_msg_key": key.encode(),
            "role_key": role.encode(),
            "origin_chat_id": None,
            "context_epoch": 0,
            "message_timestamp": None,
            "turn_id": None,
            "kind_key": b"message",
            "task_run_key": None,
            "source_occurrence_no": index - 1,
        }
        for index, (key, role) in enumerate(
            (("q", "user"), ("a", "assistant")),
            1,
        )
    ]
    service = runtime.publications
    request = await operation(db, session, first, "compact")
    plan = compact_plan(first, rows, reuse=False)
    blocks = compact_blocks()
    values = {item.name: json.loads(item.content) for item in blocks}
    bodies = [
        payload("q", "user", "question"),
        payload("a", "assistant", "answer"),
    ]
    if damage.startswith("checkpoint_"):
        key = damage.removeprefix("checkpoint_")
        values["checkpoint"][
            {
                "schema": "schema_version",
                "watermark": "applied_event_sequence",
                "chat": "chat_id",
            }.get(key, key)
        ] = (
            "other" if key == "chat" else 99
        )
    elif damage == "event_empty":
        values["events"] = []
    elif damage in ("event_gap", "event_epoch"):
        values["events"][0][
            "sequence" if damage == "event_gap" else "epoch"
        ] = 2
    elif damage == "event_duplicate":
        plan = replace(plan, events=EventInstall("events", 1, 2))
        values["events"].append({**values["events"][0], "sequence": 2})
    elif damage == "batch":
        bodies[0]["content"] = "different body"
    elif damage == "display_count":
        plan = replace(plan, archive=replace(plan.archive, display_count=3))
    elif damage == "timestamp":
        plan = replace(
            plan,
            archive=replace(
                plan.archive,
                first_timestamp="2026-10-30T00:00:02Z",
            ),
        )
    elif damage == "role":
        bodies[0]["role"] = "assistant"
    await service.reserve(request, plan)
    await service.write_bundle(
        request.operation_key,
        [block(item.name, item.kind, values[item.name]) for item in blocks]
        + [
            block("old-q", "archive", bodies[0]),
            block("old-a", "archive", bodies[1]),
        ],
        plan=plan,
    )
    with pytest.raises(IntegrityError):
        await service.commit(request.operation_key)
    assert (await service.get(request.operation_key))["state"] == "prepared"
    assert (
        await db.fetch_one(
            "SELECT state_revision FROM swe_conversation_sessions WHERE id=%s",
            (session,),
        )
    )["state_revision"] == 0


async def test_archive_preserves_turn_originating_in_another_chat_of_shared_session(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, first, second, runtime = await seed(db, tmp_path)
    turn = await insert_row(
        db,
        "swe_conversation_turns",
        {
            "chat_id": second,
            "session_id": session,
            "question_msg_key": b"q",
            "turn_order": 1,
            "context_epoch": 0,
            "generation": 0,
            "state": "succeeded",
            "history_status": "completed",
        },
    )
    from swe.app.conversation_storage.message_installs import MessageInstall

    rows = [
        {
            "id": index,
            "source_msg_key": key.encode(),
            "role_key": role.encode(),
            "origin_chat_id": None,
            "context_epoch": 0,
            "message_timestamp": datetime.fromisoformat(
                STAMP.replace("Z", "+00:00"),
            ),
            "turn_id": turn,
            "kind_key": b"message",
            "task_run_key": None,
            "source_occurrence_no": index - 1,
        }
        for index, (key, role) in enumerate(
            (("q", "user"), ("a", "assistant")),
            1,
        )
    ]
    state = {"unknown": {"keep": True}}
    request = await operation(db, session, first, "compact")
    plan = replace(
        compact_plan(
            first,
            rows,
            turn_id=turn,
            event_sequence=1,
            event_watermark=0,
        ),
        prune_ids=(),
        checkpoint=CheckpointInstall("checkpoint", 0, 1, 0, 0),
        messages=(
            MessageInstall(
                "old-q",
                "archive",
                "user",
                source_msg_key="q",
                archive_chat_id=first,
                origin_chat_id=second,
                turn_id=turn,
                message_timestamp=STAMP,
            ),
            MessageInstall(
                "old-a",
                "archive",
                "assistant",
                source_msg_key="a",
                archive_chat_id=first,
                origin_chat_id=second,
                turn_id=turn,
                message_timestamp=STAMP,
            ),
        ),
    )
    checkpoint = replace(
        CheckpointRecord.new(chat_id="first", epoch=1),
        revision=1,
        applied_event_sequence=0,
        archived_through="a",
    )
    events = [
        CheckpointEvent.new(
            sequence=1,
            epoch=1,
            type="messages_archived",
            facts={"boundary_id": "boundary"},
            source_refs=("message:q", "message:a"),
        ),
    ]
    await runtime.reserve(request, plan)
    await runtime.write_bundle(
        request.operation_key,
        [
            block("root", "recovery", state),
            block("checkpoint", "checkpoint", checkpoint.to_dict()),
            block("events", "events", [item.to_dict() for item in events]),
            block("old-q", "archive", payload("q", "user", "question")),
            block("old-a", "archive", payload("a", "assistant", "answer")),
        ],
        plan=plan,
    )
    publication = await runtime.commit(request.operation_key)
    from swe.app.conversation_storage.archive_bundle_reader import (
        read_archive_bundle,
    )

    archived = await read_archive_bundle(
        db,
        request.scope,
        runtime.bundles,
        publication,
    )
    try:
        assert [row["turn_id"] for row in archived.entries] == [turn, turn]
        assert [row["origin_chat_id"] for row in archived.entries] == [
            second,
            second,
        ]
        assert [row["archive_chat_id"] for row in archived.entries] == [
            first,
            first,
        ]
    finally:
        await archived.pins.finish()


async def test_archive_rejects_cross_session_historical_turn(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, first, _, runtime, _messages, rows, state = await archive_sources(
        db,
        tmp_path,
    )
    foreign_session = await insert_session(db, external_session_key=b"foreign")
    foreign_chat = await insert_chat(db, foreign_session, b"foreign")
    turn = await insert_row(
        db,
        "swe_conversation_turns",
        {
            "chat_id": foreign_chat,
            "session_id": foreign_session,
            "question_msg_key": b"foreign",
            "turn_order": 1,
            "context_epoch": 0,
            "generation": 0,
            "state": "succeeded",
        },
    )
    request = await operation(db, session, first, "compact")
    with pytest.raises(IntegrityError, match="Session"):
        await runtime.publications.reserve(
            request,
            compact_plan(first, rows, turn_id=turn),
        )
    assert await runtime.publications.get(request.operation_key) is None
