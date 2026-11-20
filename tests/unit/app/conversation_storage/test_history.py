# -*- coding: utf-8 -*-
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agentscope.message import Msg

from swe.app.conversation_storage.bundle import BundleStore
from swe.app.conversation_storage.history import HistoryStore
from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.conversation_storage.errors import (
    IntegrityError,
    StorageUnavailable,
)
from swe.app.runner import api
from swe.app.runner.models import ChatHistory, ChatSpec, ChatArchivePage


def history(tmp_path):
    return HistoryStore(
        None,
        WorkspaceScope(
            "tenant",
            "source",
            "agent",
            service_unit_id="schema-test-service",
        ),
        BundleStore(tmp_path),
        cursor_secret=b"test-secret",
    )


def test_archive_cursor_binds_scope_chat_epoch_and_high(tmp_path):
    store = history(tmp_path)
    token = store._encode_cursor("chat", epoch=3, high=10, before=7)
    assert store._decode_cursor(token, "chat") == {
        "v": 2,
        "chat": "chat",
        "epoch": 3,
        "high": 10,
        "before": 7,
    }
    with pytest.raises(ValueError, match="cursor"):
        store._decode_cursor(token, "other")
    with pytest.raises(ValueError, match="cursor"):
        store._decode_cursor(token + "x", "chat")
    other = HistoryStore(
        None,
        WorkspaceScope(
            "tenant",
            "other",
            "agent",
            service_unit_id="schema-test-service",
        ),
        BundleStore(tmp_path),
        cursor_secret=b"test-secret",
    )
    with pytest.raises(ValueError, match="cursor"):
        other._decode_cursor(token, "chat")


async def test_memory_payload_preserves_duplicate_source_and_fragments(
    tmp_path,
):
    store = history(tmp_path)
    msg = Msg(
        "assistant",
        [{"type": "thinking", "thinking": "a"}, {"type": "text", "text": "b"}],
        "assistant",
    )
    msg.id = "duplicate"
    rows = [
        {"layer": "memory", "source_occurrence_no": i, "task_run_key": None}
        for i in (1, 2)
    ]
    messages = await store._convert(
        rows,
        [msg.to_dict(), msg.to_dict()],
        "session",
    )
    assert len(messages) == 4
    assert {api._message_original_id(m) for m in messages} == {"duplicate"}
    assert messages[0].id == messages[2].id


async def test_business_turn_population_is_workspace_scoped_and_bounded(
    tmp_path,
):
    from datetime import datetime, timezone

    store = history(tmp_path)
    database = SimpleNamespace(fetch_all=AsyncMock(return_value=[]))
    store.db = database
    start = datetime(2026, 11, 17, tzinfo=timezone.utc)
    end = datetime(2026, 11, 18, tzinfo=timezone.utc)

    result = await store.business_turn_population(
        start_at=start,
        end_at=end,
        limit=100,
    )

    assert result == []
    query, params = database.fetch_all.await_args.args
    assert "t.admission_publication_id IS NOT NULL" in query
    assert "c.deleted_at IS NULL" in query
    assert query.count("tenant_key=%s") == 2
    assert query.count("source_key=%s") == 2
    assert params[:3] == store.scope.sql_values[:1] + (
        start.replace(tzinfo=None),
        end.replace(tzinfo=None),
    )
    assert params[-5:] == (*store.scope.sql_values, 101)


@pytest.mark.asyncio
async def test_business_visible_chat_sessions_use_current_scope_and_deletes(
    tmp_path,
):
    store = history(tmp_path)
    database = SimpleNamespace(fetch_all=AsyncMock(return_value=[]))
    store.db = database

    assert await store.business_visible_chat_sessions(limit=100) == []

    query, params = database.fetch_all.await_args.args
    assert "JOIN swe_conversation_sessions s ON s.id=c.session_id" in query
    assert "c.deleted_at IS NULL" in query
    assert query.count("tenant_key=%s") == 2
    assert query.count("source_key=%s") == 2
    assert params == (*store.scope.sql_values, *store.scope.sql_values, 101)


async def test_message_occurrence_reads_one_exact_saved_row(tmp_path):
    store = history(tmp_path)
    chat = {"id": 7, "session_id": 11}
    row = {
        "source_msg_key": b"message-1",
        "source_occurrence_no": 3,
        "message": {"id": "message-1", "role": "user"},
    }
    store._chat = AsyncMock(return_value=chat)
    store._find_message_occurrence = AsyncMock(
        return_value=("available", row),
    )
    store._pins = AsyncMock(return_value=["batch"])
    store.chats._hydrate = AsyncMock(
        return_value=[ChatSpec(id="chat", session_id="s", user_id="alice")],
    )
    store.chats._finish_batches = AsyncMock()
    from swe.app.runner.models import ChatMessage

    store._convert = AsyncMock(
        return_value=[
            ChatMessage(
                id="message-1",
                role="user",
                content=[{"type": "text", "text": "secret"}],
                metadata={
                    "console_hidden_context_v1": {
                        "visible_text": "safe",
                        "suffix": "secret",
                    },
                },
            ),
        ],
    )

    result = await store.message_occurrence(
        "chat",
        "message-1",
        occurrence_no=3,
    )

    assert result["status"] == "available"
    assert result["message"]["id"] == "message-1"
    assert result["message"]["content"][0]["text"] == "safe"
    assert "console_hidden_context_v1" not in result["message"]["metadata"]
    store._find_message_occurrence.assert_awaited_once_with(
        chat,
        b"message-1",
        3,
    )
    store.chats._finish_batches.assert_awaited_once_with(["batch"])


async def test_message_occurrence_rejects_oversize_payload_before_convert(
    tmp_path,
):
    store = history(tmp_path)
    row = {
        "source_msg_key": b"message-1",
        "source_occurrence_no": 0,
        "message": {"id": "message-1", "content": "x" * 1024},
    }
    store._chat = AsyncMock(return_value={"id": 7, "session_id": 11})
    store._find_message_occurrence = AsyncMock(
        return_value=("available", row),
    )
    store._pins = AsyncMock(return_value=["batch"])
    store.chats._hydrate = AsyncMock(
        return_value=[ChatSpec(id="chat", session_id="s", user_id="alice")],
    )
    store.chats._finish_batches = AsyncMock()
    store._convert = AsyncMock()
    authorized = []

    def authorize(chat):
        authorized.append(chat)

    result = await store.message_occurrence(
        "chat",
        "message-1",
        max_bytes=32,
        authorize=authorize,
    )

    assert result == {"status": "truncated", "message": None}
    assert len(authorized) == 1
    store._convert.assert_not_awaited()
    store.chats._finish_batches.assert_awaited_once_with(["batch"])


async def test_message_occurrence_authorizes_before_reporting_truncation(
    tmp_path,
):
    store = history(tmp_path)
    row = {
        "source_msg_key": b"message-1",
        "source_occurrence_no": 0,
        "message": {"id": "message-1", "content": "x" * 1024},
    }
    store._chat = AsyncMock(return_value={"id": 7, "session_id": 11})
    store._find_message_occurrence = AsyncMock(
        return_value=("available", row),
    )
    store._pins = AsyncMock(return_value=["batch"])
    store.chats._hydrate = AsyncMock(
        return_value=[ChatSpec(id="chat", session_id="s", user_id="alice")],
    )
    store.chats._finish_batches = AsyncMock()
    store._convert = AsyncMock()

    def deny(_chat):
        raise KeyError("not authorized")

    with pytest.raises(KeyError):
        await store.message_occurrence(
            "chat",
            "message-1",
            max_bytes=32,
            authorize=deny,
        )
    store._convert.assert_not_awaited()
    store.chats._finish_batches.assert_awaited_once_with(["batch"])


@pytest.mark.parametrize(
    "expected",
    ["unavailable", "unresolved"],
)
async def test_message_occurrence_does_not_guess_missing_or_duplicate_ids(
    tmp_path,
    expected,
):
    store = history(tmp_path)
    store._chat = AsyncMock(return_value={"id": 7, "session_id": 11})
    store._find_message_occurrence = AsyncMock(
        return_value=(expected, None),
    )
    result = await store.message_occurrence("chat", "duplicate")
    assert result == {"status": expected, "message": None}


async def test_message_occurrence_finds_exact_active_nas_directory_row(
    tmp_path,
):
    store = history(tmp_path)
    chat = {"id": 7, "session_id": 11}
    row = {
        "source_msg_key": b"duplicate",
        "source_occurrence_no": 1,
    }
    store.reader.session_messages = AsyncMock(
        return_value=[
            {"source_msg_key": b"duplicate", "source_occurrence_no": 0},
            row,
        ],
    )
    store.db = SimpleNamespace(fetch_all=AsyncMock())

    status, found = await store._find_message_occurrence(
        chat,
        b"duplicate",
        1,
    )

    assert status == "available"
    assert found is row
    store.db.fetch_all.assert_not_awaited()


async def test_message_occurrence_falls_back_to_archived_nas_directory(
    tmp_path,
    monkeypatch,
):
    store = history(tmp_path)
    chat = {"id": 7, "session_id": 11}
    boundary = {"id": 9, "archive_last_order": 3}
    store.reader.session_messages = AsyncMock(return_value=[])
    store.db = SimpleNamespace(
        fetch_all=AsyncMock(return_value=[boundary]),
    )
    read = SimpleNamespace(
        entries=(
            {
                "sequence": 3,
                "raw_id": "archived",
                "source_occurrence_no": 2,
                "role": "assistant",
                "message": {"id": "archived", "role": "assistant"},
            },
        ),
        pins=SimpleNamespace(finish=AsyncMock()),
    )
    reader = AsyncMock(return_value=read)
    monkeypatch.setattr(
        "swe.app.conversation_storage.archive_bundle_reader."
        "read_archive_bundle",
        reader,
    )

    status, found = await store._find_message_occurrence(
        chat,
        b"archived",
        2,
    )

    assert status == "available"
    assert found["archive_order"] == 3
    assert found["source_occurrence_no"] == 2
    reader.assert_awaited_once()
    read.pins.finish.assert_awaited_once()


async def test_current_route_uses_injected_history_without_file_session(
    tmp_path,
):
    spec = ChatSpec(id="chat", session_id="s", user_id="alice")
    injected = SimpleNamespace(
        current=AsyncMock(return_value=ChatHistory(chat=spec)),
    )
    workspace = SimpleNamespace(
        conversation_storage=SimpleNamespace(history=injected),
    )
    result = await api._build_chat_history(
        spec,
        session=object(),
        workspace=workspace,
    )
    assert result.chat.id == "chat"
    injected.current.assert_awaited_once()


async def test_archive_route_uses_injected_indexed_reader(tmp_path):
    expected = ChatArchivePage(has_more=True, next_cursor="cursor")
    injected = SimpleNamespace(archive_page=AsyncMock(return_value=expected))
    workspace = SimpleNamespace(
        conversation_storage=SimpleNamespace(history=injected),
    )
    assert await api._archive_page(workspace, "chat", None, 5) is expected
    injected.archive_page.assert_awaited_once_with(
        "chat",
        before=None,
        limit=5,
    )


async def test_task_projection_envelope_preserves_exact_run_index(tmp_path):
    store = history(tmp_path)
    msg = Msg("assistant", "answer", "assistant")
    msg.id = "raw"
    row = {
        "layer": "memory",
        "source_occurrence_no": 0,
        "task_run_key": b"run",
    }
    payload = {
        "version": 1,
        "message": msg.to_dict(),
        "history_projection": {
            "task_run_id": "run",
            "task_run_index": 7,
            "task_run_section": "final",
        },
    }
    messages = await store._convert([row], [payload], "session")
    assert messages[0].metadata["task_run_index"] == 7
    assert messages[0].metadata["task_run_section"] == "final"
    with pytest.raises(IntegrityError, match="projection"):
        await store._convert([row], [msg.to_dict()], "session")


async def test_tracing_overlay_binds_target_scope_and_restores_operator(
    tmp_path,
    monkeypatch,
):
    from swe.config.context import (
        tenant_context,
        get_current_scope_id,
        resolve_scope_id,
    )
    from swe.app.conversation_storage.history import HistorySnapshot

    store = history(tmp_path)
    spec = ChatSpec(id="chat", session_id="s", user_id="bob")
    store.chats._hydrate = AsyncMock(return_value=[spec])
    store._validate_snapshot = AsyncMock()
    store._payloads = AsyncMock(return_value=[])
    store._finish = AsyncMock()
    seen = []

    async def overlay(messages):
        seen.append(get_current_scope_id())
        return messages

    monkeypatch.setattr(api, "_annotate_approval_action_statuses", overlay)
    with tenant_context(tenant_id="operator", source_id="operator-source"):
        operator = get_current_scope_id()
        await store._assemble(HistorySnapshot({}, [], [], []), tracing=True)
        assert get_current_scope_id() == operator
    assert seen == [resolve_scope_id("tenant", "source")]


@pytest.mark.parametrize("kind", ["storage", "mysql", "nas"])
async def test_indexed_detail_storage_failure_maps_to_503(tmp_path, kind):
    from fastapi import HTTPException
    from mysql.connector.errors import InterfaceError

    spec = ChatSpec(id="chat", session_id="s", user_id="alice")
    error = {
        "storage": StorageUnavailable("db unavailable"),
        "mysql": InterfaceError("connection lost"),
        "nas": OSError("NAS missing"),
    }[kind]
    injected = SimpleNamespace(current=AsyncMock(side_effect=error))
    workspace = SimpleNamespace(
        conversation_storage=SimpleNamespace(history=injected),
    )
    manager = SimpleNamespace(get_chat=AsyncMock(return_value=spec))
    with pytest.raises(HTTPException) as failure:
        await api.get_chat(
            SimpleNamespace(state=SimpleNamespace(user_id="alice")),
            "chat",
            mgr=manager,
            session=object(),
            workspace=workspace,
        )
    assert failure.value.status_code == 503


async def test_target_approval_overlay_uses_actual_scope_filter(
    tmp_path,
    monkeypatch,
):
    from swe.app.approvals.service import ApprovalService
    from swe.config.context import tenant_context, resolve_scope_id
    from swe.app.conversation_storage.history import HistorySnapshot
    from swe.app.runner.models import ChatMessage

    service = ApprovalService()
    service._completed["same-id"] = SimpleNamespace(
        scope_id=resolve_scope_id("tenant", "source"),
        status="approved",
    )
    monkeypatch.setattr(api, "get_approval_service", lambda: service)
    store = history(tmp_path)
    spec = ChatSpec(id="chat", session_id="s", user_id="bob")
    store.chats._hydrate = AsyncMock(return_value=[spec])
    store._validate_snapshot = AsyncMock()
    store._payloads = AsyncMock(return_value=[])
    store._finish = AsyncMock()
    message = ChatMessage(
        id="approval",
        role="assistant",
        content=[],
        metadata={
            "metadata": {
                "approval_action": {
                    "requestId": "same-id",
                    "status": "pending",
                },
            },
        },
    )
    store._convert = AsyncMock(return_value=[message])
    with tenant_context(tenant_id="operator", source_id="operator-source"):
        result = await store._assemble(
            HistorySnapshot({}, [], [], []),
            tracing=True,
        )
    assert (
        result.messages[0].metadata["metadata"]["approval_action"]["status"]
        == "approved"
    )


@pytest.mark.parametrize("tracing", [False, True])
async def test_shared_session_reset_during_payload_read(
    tmp_path,
    monkeypatch,
    tracing,
):
    from swe.app.conversation_storage.history import HistorySnapshot
    from swe.app.conversation_storage.errors import ConflictError

    store = history(tmp_path)
    epoch = 4

    async def session_row(*args):
        return {"context_epoch": epoch, "recovery_publication_id": None}

    store.db = SimpleNamespace(fetch_one=session_row)
    store._validate_chat_row = AsyncMock()
    store.chats._hydrate = AsyncMock(
        return_value=[
            ChatSpec(
                id="B",
                session_id="shared",
                user_id="bob",
            ),
        ],
    )

    async def read_then_reset(snapshot):
        nonlocal epoch
        epoch += 1  # A commits reset while B reads its pinned body.
        return []

    store._payloads = read_then_reset
    store._finish = AsyncMock()
    monkeypatch.setattr(
        api,
        "_annotate_approval_action_statuses",
        AsyncMock(return_value=[]),
    )
    snapshot = HistorySnapshot({"session_id": 1}, [], [], [])
    snapshot.context_epoch = 4
    with pytest.raises(ConflictError, match="Session history changed"):
        await store._assemble(snapshot, tracing=tracing)
    store._finish.assert_awaited_once_with(snapshot)


@pytest.mark.parametrize("tracing", [False, True])
@pytest.mark.parametrize(
    "change",
    [{"state_revision": 10}, {"recovery_publication_id": 111}],
    ids=["revision", "recovery-pointer"],
)
async def test_shared_session_publication_changes_during_payload_read(
    tmp_path,
    monkeypatch,
    tracing,
    change,
):
    from swe.app.conversation_storage.history import HistorySnapshot
    from swe.app.conversation_storage.errors import ConflictError

    store = history(tmp_path)
    session = {
        "context_epoch": 4,
        "state_revision": 9,
        "recovery_publication_id": 110,
    }
    store.db = SimpleNamespace(fetch_one=AsyncMock(return_value=session))
    store._validate_chat_row = AsyncMock()
    store.chats._hydrate = AsyncMock(
        return_value=[ChatSpec(id="B", session_id="shared", user_id="bob")],
    )

    async def read_then_publish(snapshot):
        session.update(change)
        return []

    store._payloads = read_then_publish
    store._convert = AsyncMock(return_value=[])
    store._finish = AsyncMock()
    monkeypatch.setattr(
        api,
        "_annotate_approval_action_statuses",
        AsyncMock(return_value=[]),
    )
    snapshot = HistorySnapshot(
        {"id": 2, "session_id": 1},
        [],
        [],
        [],
        **session,
    )
    with pytest.raises(ConflictError, match="Session history changed"):
        await store._assemble(snapshot, tracing=tracing)
    store._finish.assert_awaited_once_with(snapshot)
