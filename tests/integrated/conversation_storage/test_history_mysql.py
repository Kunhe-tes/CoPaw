# -*- coding: utf-8 -*-
import json
from types import SimpleNamespace

import pytest
from agentscope.message import Msg

from swe.app.conversation_storage.bundle import (
    BundleBlock,
    BundleStore,
    new_operation_key,
)
from swe.app.conversation_storage.errors import ConflictError, IntegrityError
from swe.app.conversation_storage.message_bundle import (
    encode_archive_manifest,
    encode_message_bodies,
)
from swe.app.conversation_storage.history import HistoryStore
from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.runner import api
from tests.integrated.conversation_storage.test_schema import (
    insert_session,
    insert_chat,
    insert_row,
    insert_publication,
    NOW,
)

_SESSION_MESSAGES = {}
_SESSION_BODIES = {}
_ARCHIVE_BODIES = {}


def source(
    key,
    role="assistant",
    content="text",
    stamp="2026-10-30T00:00:01Z",
):
    msg = Msg(
        "user" if role == "user" else "assistant",
        content,
        role,
        timestamp=stamp,
    )
    msg.id = key
    return msg.to_dict()


async def dataset(db, tmp_path):
    _SESSION_MESSAGES[id(db)] = {}
    _SESSION_BODIES[id(db)] = {}
    _ARCHIVE_BODIES[id(db)] = {}
    session = await insert_session(db)
    first = await insert_chat(db, session, b"chat-a")
    second = await insert_chat(db, session, b"chat-b", registry_order=2)
    await db.execute(
        "UPDATE swe_conversation_sessions SET history_high=100 WHERE id=%s",
        (session,),
    )
    bundles = BundleStore(tmp_path)
    return (
        session,
        first,
        second,
        HistoryStore(
            db,
            WorkspaceScope(
                "tenant",
                "source",
                "agent",
                service_unit_id="schema-test-service",
            ),
            bundles,
            cursor_secret=b"shared-test-secret",
        ),
    )


async def add_messages(db, store, session, chat, items, *, boundary=False):
    operation = new_operation_key()
    is_archive = boundary or all(layer == "archive" for layer, _, _ in items)
    chat_row = await db.fetch_one(
        "SELECT external_chat_key,epoch FROM swe_conversation_chats WHERE id=%s",
        (chat,),
    )
    bodies = [payload for _, payload, _ in items]
    entries = []
    for index, (layer, payload, order) in enumerate(items):
        entries.append(
            {
                "sequence": order,
                "raw_id": payload["id"],
                "layer": layer,
                "visible": True,
                "current_visible": True,
                "in_context": layer == "memory",
                "session_order": None if is_archive else order,
                "chat_id": chat if layer in ("anchor", "archive") else None,
                "origin_chat_id": chat if layer == "anchor" else None,
                "archive_chat_id": chat if is_archive else None,
                "archive_order": order if is_archive else None,
                "source_occurrence_no": index,
                "role": payload.get("role") or "assistant",
                "kind": "message",
                "timestamp": payload.get("timestamp"),
                "body": {
                    "publication_id": "self",
                    "block_name": "message_bodies",
                    "position": index,
                },
            },
        )
    blocks = [
        BundleBlock(
            "message_directory",
            "message_directory",
            json.dumps(entries, ensure_ascii=False).encode(),
        ),
        BundleBlock(
            "message_bodies",
            "message_bodies",
            encode_message_bodies(bodies),
        ),
    ]
    index = store.bundles.publish(
        operation,
        blocks
        + (
            [
                BundleBlock(
                    "archive_manifest",
                    "archive_manifest",
                    encode_archive_manifest(
                        {
                            "format": "swe.archive-manifest.v1",
                            "chat_id": bytes(
                                chat_row["external_chat_key"],
                            ).decode(),
                            "epoch": chat_row["epoch"],
                            "first_sequence": min(
                                order for _, _, order in items
                            ),
                            "last_sequence": max(
                                order for _, _, order in items
                            ),
                            "chunks": [
                                {
                                    "publication_id": "self",
                                    "first_sequence": min(
                                        order for _, _, order in items
                                    ),
                                    "last_sequence": max(
                                        order for _, _, order in items
                                    ),
                                    "directory_block": "message_directory",
                                },
                            ],
                        },
                    ),
                ),
            ]
            if is_archive
            else []
        ),
        scope=store.scope,
        metadata={"operation_key": operation},
    )
    values = {
        "state": "committed",
        "session_id": session,
        "chat_id": chat,
        "byte_length": index.byte_length,
        "durable_at": NOW,
        "committed_at": NOW,
        "relative_path": index.relative_path.encode(),
    }
    if is_archive:
        orders = [order for _, _, order in items]
        manifest_extent = index.blocks["archive_manifest"]
        values.update(
            epoch=chat_row["epoch"],
            boundary_key=f"boundary-{min(orders)}".encode(),
            boundary_order=min(orders),
            archive_first_order=min(orders),
            archive_last_order=max(orders),
            archive_source_count=len(items),
            archive_display_count=len(items),
            archive_offset=manifest_extent.offset,
            archive_length=manifest_extent.length,
            archive_first_source_msg_key=items[0][1]["id"].encode(),
            archive_last_source_msg_key=items[-1][1]["id"].encode(),
        )
    publication = await insert_publication(db, operation.encode(), **values)
    if is_archive:
        _ARCHIVE_BODIES[id(db)][publication] = bodies
        await db.execute(
            "UPDATE swe_conversation_chats SET history_high=%s WHERE id=%s",
            (max(order for _, _, order in items), chat),
        )
    else:
        current = _SESSION_MESSAGES[id(db)].setdefault(session, [])
        start_order = max(
            (entry["session_order"] for entry in current),
            default=0,
        )
        body_start = len(_SESSION_BODIES[id(db)].setdefault(session, []))
        current.extend(
            {
                **entry,
                "sequence": start_order + position + 1,
                "session_order": start_order + position + 1,
                "body": {
                    "publication_id": "self",
                    "block_name": "message_bodies",
                    "position": body_start + position,
                },
            }
            for position, entry in enumerate(entries)
        )
        session_bodies = _SESSION_BODIES[id(db)].setdefault(session, [])
        session_bodies.extend(bodies)
        publication, index = await _publish_session_snapshot(
            db,
            store,
            session,
        )
    return publication, index


async def _publish_session_snapshot(db, store, session):
    entries = _SESSION_MESSAGES[id(db)][session]
    bodies = _SESSION_BODIES[id(db)][session]
    operation = new_operation_key()
    envelope = {
        "format": "swe-recovery-projection",
        "version": 1,
        "state": {},
        "lists": [],
        "turns": [],
        "identity": {"operation_key": operation},
        "message_directory": entries,
    }
    index = store.bundles.publish(
        operation,
        [
            BundleBlock("recovery", "recovery", json.dumps(envelope).encode()),
            BundleBlock(
                "message_bodies",
                "message_bodies",
                encode_message_bodies(bodies),
            ),
        ],
        scope=store.scope,
        metadata={"operation_key": operation},
    )
    publication = await insert_publication(
        db,
        operation.encode(),
        state="committed",
        session_id=session,
        byte_length=index.byte_length,
        durable_at=NOW,
        committed_at=NOW,
        relative_path=index.relative_path.encode(),
    )
    extent = index.blocks["recovery"]
    await db.execute(
        "UPDATE swe_conversation_sessions SET recovery_publication_id=%s,"
        "recovery_offset=%s,recovery_length=%s,state_revision=state_revision+1,"
        "history_high=%s WHERE id=%s",
        (publication, extent.offset, extent.length, len(entries), session),
    )
    return publication, index


async def _update_session_directory(db, store, session, update):
    entries = _SESSION_MESSAGES[id(db)][session]
    update(entries)
    return await _publish_session_snapshot(db, store, session)


async def _update_archive_directory(db, store, publication_id, update):
    row = await db.fetch_one(
        "SELECT relative_path,byte_length FROM swe_conversation_publications "
        "WHERE id=%s",
        (publication_id,),
    )
    index = store.bundles.inspect(
        bytes(row["relative_path"]).decode(),
        expected_length=row["byte_length"],
    )
    extent = index.blocks["message_directory"]
    entries = json.loads(
        store.bundles.read_extent(
            index.relative_path,
            extent.offset,
            extent.length,
            expected_length=index.byte_length,
        ),
    )
    update(entries)
    operation = new_operation_key()
    old_manifest = json.loads(
        store.bundles.read_extent(
            index.relative_path,
            index.blocks["archive_manifest"].offset,
            index.blocks["archive_manifest"].length,
            expected_length=index.byte_length,
        ),
    )
    blocks = [
        BundleBlock(
            "message_directory",
            "message_directory",
            json.dumps(entries).encode(),
        ),
        BundleBlock(
            "message_bodies",
            "message_bodies",
            encode_message_bodies(_ARCHIVE_BODIES[id(db)][publication_id]),
        ),
        BundleBlock(
            "archive_manifest",
            "archive_manifest",
            encode_archive_manifest(old_manifest),
        ),
    ]
    replacement = store.bundles.publish(
        operation,
        blocks,
        scope=store.scope,
        metadata={"operation_key": operation},
    )
    await db.execute(
        "UPDATE swe_conversation_publications SET operation_key=%s,"
        "relative_path=%s,byte_length=%s,archive_offset=%s,archive_length=%s "
        "WHERE id=%s",
        (
            operation.encode(),
            replacement.relative_path.encode(),
            replacement.byte_length,
            replacement.blocks["archive_manifest"].offset,
            replacement.blocks["archive_manifest"].length,
            publication_id,
        ),
    )


async def test_shared_memory_and_chat_anchors_archive_are_independent(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, a, b, store = await dataset(db, tmp_path)
    await add_messages(
        db,
        store,
        session,
        a,
        [
            ("memory", source("shared", "assistant"), 1),
            ("anchor", source("anchor-a", "user"), 2),
        ],
    )
    await add_messages(
        db,
        store,
        session,
        b,
        [("anchor", source("anchor-b", "user"), 3)],
    )
    await add_messages(
        db,
        store,
        session,
        a,
        [("archive", source("archived-a"), 1)],
        boundary=True,
    )
    first = await store.current("chat-a")
    second = await store.current("chat-b")
    assert [api._message_original_id(m) for m in first.messages] == [
        "shared",
        "anchor-a",
    ]
    assert [api._message_original_id(m) for m in second.messages] == [
        "shared",
        "anchor-b",
    ]
    assert first.archive.has_more and not second.archive.has_more
    traced = await store.tracing_view("chat-a")
    assert traced.chat is None and not traced.archive.has_more
    assert [api._message_original_id(m) for m in traced.messages] == ["shared"]


async def test_archive_limit_counts_sources_and_cursor_keeps_original_high(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, a, _, store = await dataset(db, tmp_path)
    fragment = [
        {"type": "thinking", "thinking": "x"},
        {"type": "text", "text": "y"},
    ]
    await add_messages(
        db,
        store,
        session,
        a,
        [
            ("archive", source("one"), 1),
            ("archive", source("two", content=fragment), 2),
            ("archive", source("three"), 3),
        ],
        boundary=True,
    )
    page = await store.archive_page("chat-a", limit=2)
    assert len(page.messages) == 3 and page.has_more and page.next_cursor
    assert [api._message_original_id(m) for m in page.messages] == [
        "two",
        "two",
        "three",
    ]
    older = await store.archive_page(
        "chat-a",
        limit=2,
        before=page.next_cursor,
    )
    assert [api._message_original_id(m) for m in older.messages] == ["one"]
    assert not older.has_more
    with pytest.raises(ValueError, match="cursor"):
        await store.archive_page("chat-b", before=page.next_cursor)


async def test_legacy_answer_turn_is_point_range_and_unknown_status_stays_none(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, a, _, store = await dataset(db, tmp_path)
    await add_messages(
        db,
        store,
        session,
        a,
        [
            ("memory", source("q", "user"), 1),
            ("memory", source("answer"), 2),
            ("memory", source("next", "user"), 3),
            ("memory", source("other"), 4),
        ],
    )
    result = await store.answer_turn(
        "q",
        chat_id="chat-a",
        session_id="wrong-ignored",
        user_id="alice",
    )
    assert [api._message_original_id(m) for m in result.messages] == [
        "q",
        "answer",
    ]
    assert result.turn_status is None
    with pytest.raises(KeyError):
        await store.answer_turn("answer", chat_id="chat-a", user_id="alice")


async def test_import_display_order_preserves_interleaved_error_answer_turn(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, chat, _, store = await dataset(db, tmp_path)
    from swe.app.conversation_storage.migration.importer import (
        display_order_messages,
        extract_messages,
    )

    messages = display_order_messages(
        extract_messages(
            {
                "agent": {
                    "memory": {
                        "content": [
                            source("q1", "user", stamp="2026-10-30T00:00:01Z"),
                            source("q2", "user", stamp="2026-10-30T00:00:03Z"),
                        ],
                    },
                },
                "model_call_failed_messages": [
                    {
                        "id": "e1",
                        "role": "assistant",
                        "code": "model_call_failed",
                        "message": "failed",
                        "timestamp": "2026-10-30T00:00:02Z",
                    },
                ],
            },
            context_epoch=0,
        ),
    )
    await add_messages(
        db,
        store,
        session,
        chat,
        [
            (item["layer"], item["payload"], order)
            for order, item in enumerate(messages, start=1)
        ],
    )

    result = await store.answer_turn("q1", chat_id="chat-a", user_id="alice")

    assert [
        api._message_original_id(message) for message in result.messages
    ] == [
        "q1",
        "e1",
    ]


async def test_history_rechecks_deletion_after_nas_and_releases_pins(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, a, _, store = await dataset(db, tmp_path)
    await add_messages(
        db,
        store,
        session,
        a,
        [("memory", source("visible"), 1)],
    )
    original = store._payloads

    async def delete_after_read(snapshot):
        payloads = await original(snapshot)
        await db.execute(
            "UPDATE swe_conversation_chats "
            "SET deleted_at=UTC_TIMESTAMP(6) WHERE id=%s",
            (a,),
        )
        return payloads

    store._payloads = delete_after_read
    with pytest.raises(ConflictError):
        await store.current("chat-a")
    assert not await db.fetch_all(
        "SELECT id FROM swe_conversation_retentions "
        "WHERE kind='reader' AND state='active'",
    )


async def test_numeric_usage_never_reads_nas_and_future_version_is_unavailable(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, _, _, store = await dataset(db, tmp_path)
    store.bundles.read_extent = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("NAS read"),
    )
    assert (await store.context_usage("chat-a")).available is False
    await db.execute(
        "UPDATE swe_conversation_sessions SET context_usage_text=%s "
        "WHERE id=%s",
        (json.dumps({"schema_version": 99}), session),
    )
    assert (await store.context_usage("chat-a")).available is False


async def test_answer_turn_honors_stored_chat_and_original_status(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, a, b, store = await dataset(db, tmp_path)
    await add_messages(
        db,
        store,
        session,
        a,
        [
            ("memory", source("question", "user"), 1),
            ("memory", source("response"), 2),
        ],
    )
    await insert_row(
        db,
        "swe_conversation_turns",
        {
            "session_id": session,
            "chat_id": b,
            "question_msg_key": b"question",
            "turn_order": 1,
            "context_epoch": 0,
            "generation": 0,
            "state": "succeeded",
            "history_status": "cancelled",
        },
    )
    with pytest.raises(KeyError):
        await store.answer_turn("question", chat_id="chat-a", user_id="alice")
    result = await store.answer_turn(
        "question",
        session_id="session",
        user_id="alice",
    )
    assert result.chat.id == "chat-b" and result.turn_status == "cancelled"


async def test_history_route_index_and_current_identity_authorization(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, a, _, store = await dataset(db, tmp_path)
    await add_messages(
        db,
        store,
        session,
        a,
        [("memory", source("visible"), 1)],
    )
    workspace = SimpleNamespace(
        conversation_storage=SimpleNamespace(history=store),
        agent_id="agent",
    )
    manager = SimpleNamespace(get_chat=store.chats.get_chat)
    request = SimpleNamespace(
        state=SimpleNamespace(
            user_id="alice",
            source_id="source",
            agent_id="agent",
        ),
    )
    result = await api.get_chat(
        request,
        "chat-a",
        mgr=manager,
        session=object(),
        workspace=workspace,
    )
    assert [api._message_original_id(m) for m in result.messages] == [
        "visible",
    ]
    request.state.user_id = "other"
    with pytest.raises(Exception) as error:
        await api.get_chat(
            request,
            "chat-a",
            mgr=manager,
            session=object(),
            workspace=workspace,
        )
    assert error.value.status_code == 404


async def test_deleted_chat_after_pin_before_nas_refuses_read(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, a, _, store = await dataset(db, tmp_path)
    await add_messages(
        db,
        store,
        session,
        a,
        [("memory", source("never-read"), 1)],
    )
    original = store._snapshot

    async def delete_after_snapshot(*args, **kwargs):
        snapshot = await original(*args, **kwargs)
        await db.execute(
            "UPDATE swe_conversation_chats "
            "SET deleted_at=UTC_TIMESTAMP(6) WHERE id=%s",
            (a,),
        )
        return snapshot

    store._snapshot = delete_after_snapshot
    store.bundles.read_extent = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("NAS read after deletion"),
    )
    with pytest.raises(ConflictError):
        await store.current("chat-a")
    assert not await db.fetch_all(
        "SELECT id FROM swe_conversation_retentions "
        "WHERE kind='reader' AND state='active'",
    )


async def test_all_shared_layers_duplicates_and_archive_anchor_suppression(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, a, _, store = await dataset(db, tmp_path)
    task = {
        "id": "task",
        "role": "assistant",
        "content": "task text",
        "timestamp": "2026-10-30T00:00:02Z",
    }
    error = {
        "id": "error",
        "role": "assistant",
        "code": "model_call_failed",
        "message": "failed",
        "timestamp": "2026-10-30T00:00:03Z",
    }
    await add_messages(
        db,
        store,
        session,
        a,
        [
            ("memory", source("duplicate"), 1),
            ("memory", source("duplicate"), 2),
            ("task", task, 3),
            ("error", error, 4),
            ("anchor", source("archived-anchor", "user"), 5),
        ],
    )
    await add_messages(
        db,
        store,
        session,
        a,
        [("archive", source("archived-anchor", "user"), 1)],
        boundary=True,
    )
    first = await store.current("chat-a")
    second = await store.current("chat-b")
    assert [api._message_original_id(m) for m in first.messages] == [
        "duplicate",
        "duplicate",
        "task",
        "error",
    ]
    assert [api._message_original_id(m) for m in second.messages] == [
        "duplicate",
        "duplicate",
        "task",
        "error",
    ]
    tracing = await store.tracing_view("chat-a")
    assert [api._message_original_id(m) for m in tracing.messages] == [
        "duplicate",
        "duplicate",
        "task",
    ]


async def test_corrupt_publication_scope_or_extent_fails_not_empty(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, a, _, store = await dataset(db, tmp_path)
    publication, _ = await add_messages(
        db,
        store,
        session,
        a,
        [("memory", source("body"), 1)],
    )
    await db.execute(
        "UPDATE swe_conversation_publications SET source_key=%s WHERE id=%s",
        (b"other", publication),
    )
    with pytest.raises(IntegrityError, match="scope"):
        await store.current("chat-a")
    await db.execute(
        "UPDATE swe_conversation_publications SET source_key=%s WHERE id=%s",
        (b"source", publication),
    )
    await db.execute(
        "UPDATE swe_conversation_publications SET byte_length=999999 "
        "WHERE id=%s",
        (publication,),
    )
    with pytest.raises(IntegrityError, match="length"):
        await store.current("chat-a")


async def test_numeric_snapshot_stale_only_for_active_chat(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, a, _, store = await dataset(db, tmp_path)
    snapshot = {
        "schema_version": 1,
        "used_tokens": 10,
        "max_tokens": 100,
        "remaining_tokens": 90,
        "usage_ratio": 0.1,
        "system_context_tokens": 2,
        "tool_definition_tokens": 3,
        "conversation_tokens": 5,
        "governance_threshold_ratio": 0.5,
        "active_threshold_ratio": 0.7,
        "emergency_threshold_ratio": 0.9,
        "status": "normal",
        "estimated": True,
        "as_of": "2026-10-30T00:00:00Z",
    }
    turn = await insert_row(
        db,
        "swe_conversation_turns",
        {
            "session_id": session,
            "chat_id": a,
            "question_msg_key": b"q",
            "turn_order": 1,
            "context_epoch": 0,
            "generation": 1,
            "state": "running",
        },
    )
    await db.execute(
        "UPDATE swe_conversation_sessions SET context_usage_text=%s,"
        "active_turn_id=%s WHERE id=%s",
        (json.dumps(snapshot), turn, session),
    )
    assert (await store.context_usage("chat-a")).stale is True
    assert (await store.context_usage("chat-b")).stale is False


async def test_archived_turn_stays_hidden_but_visible_typed_turn_is_readable(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, a, _, store = await dataset(db, tmp_path)
    await add_messages(
        db,
        store,
        session,
        a,
        [
            ("memory", source("cold-q", "user"), 1),
            ("memory", source("cold-a"), 2),
        ],
    )
    turn = await insert_row(
        db,
        "swe_conversation_turns",
        {
            "session_id": session,
            "chat_id": a,
            "question_msg_key": b"cold-q",
            "turn_order": 1,
            "context_epoch": 0,
            "generation": 0,
            "state": "succeeded",
            "history_status": "completed",
        },
    )
    memory_publication, _ = await _update_session_directory(
        db,
        store,
        session,
        lambda entries: [
            entry.update(
                turn_id=turn,
                visible=False,
                current_visible=False,
                in_context=False,
            )
            for entry in entries
        ],
    )
    archive_publication, _ = await add_messages(
        db,
        store,
        session,
        a,
        [
            ("archive", source("cold-q", "user"), 1),
            ("archive", source("cold-a"), 2),
        ],
        boundary=True,
    )
    await _update_archive_directory(
        db,
        store,
        archive_publication,
        lambda entries: [entry.update(turn_id=turn) for entry in entries],
    )
    with pytest.raises(KeyError):
        await store.answer_turn("cold-q", chat_id="chat-a", user_id="alice")
    memory_publication, _ = await _update_session_directory(
        db,
        store,
        session,
        lambda entries: [
            entry.update(visible=True, current_visible=True)
            for entry in entries
        ],
    )
    await db.execute(
        "UPDATE swe_conversation_sessions SET recovery_publication_id=%s "
        "WHERE id=%s",
        (memory_publication, session),
    )
    result = await store.answer_turn(
        "cold-q",
        chat_id="chat-a",
        user_id="alice",
    )
    assert [api._message_original_id(m) for m in result.messages] == [
        "cold-q",
        "cold-a",
    ]
    assert result.turn_status == "completed"
