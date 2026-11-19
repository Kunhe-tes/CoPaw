# -*- coding: utf-8 -*-
"""Runtime façade uses existing workspace bundles and SQL occurrence locators."""

import asyncio
import io
import json
from types import SimpleNamespace

from agentscope.message import Msg
import pytest

from swe.app.conversation_storage.archive_runtime import MySQLArchiveStore
from swe.app.conversation_storage.bundle import BundleStore
from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.conversation_storage.session_adapter import MySQLSessionAdapter
from tests.integrated.conversation_storage.test_schema import (
    insert_chat,
    insert_session,
)


async def setup(db, root):
    session = await insert_session(db)
    chat = await insert_chat(db, session, b"first", epoch=1)
    second = await insert_chat(
        db,
        session,
        b"second",
        registry_order=2,
        epoch=1,
    )
    bundles = BundleStore(root)
    scope = WorkspaceScope(
        "tenant",
        "source",
        "agent",
        service_unit_id="schema-test-service",
    )
    adapter = MySQLSessionAdapter(db, scope, bundles, channel="console")
    store = MySQLArchiveStore(db, scope, bundles, adapter)
    return session, chat, second, store


def source(key, text):
    message = Msg("user", text, "user", timestamp="2026-10-30T00:00:01Z")
    message.id = key
    return message


async def test_runtime_compact_reuses_original_body_extent_and_dependency_pins(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    session, chat, other, store = await setup(db, tmp_path)
    first, second = source("q", "question"), source(
        "q",
        "second occurrence with reused ID",
    )
    state = {"revision": 0, "unknown_module": {"keep": ["all"]}}
    for message in (first, second):
        result = await store.append_message(
            "first",
            message,
            recovery_state=state,
            authority=None,
        )
        state = result.recovery_state
    originals = await db.fetch_all(
        "SELECT * FROM swe_conversation_messages ORDER BY session_order",
    )
    result = await store.compact(
        "first",
        [first],
        recovery_state={
            **state,
            "agent": {
                "memory": {
                    "content": [[second.to_dict(), []]],
                    "_compressed_summary": "new",
                },
            },
        },
        authority=None,
    )
    archived = await db.fetch_one(
        "SELECT * FROM swe_conversation_messages WHERE layer='archive'",
    )
    assert (
        archived["publication_id"],
        archived["byte_offset"],
        archived["byte_length"],
    ) == (
        originals[0]["publication_id"],
        originals[0]["byte_offset"],
        originals[0]["byte_length"],
    )
    assert archived["archive_publication_id"] == result.publication["id"]
    pins = await db.fetch_all(
        "SELECT publication_id FROM swe_conversation_retentions WHERE kind='dependency' AND state='active'",
    )
    assert sorted({row["publication_id"] for row in pins}) == sorted(
        {item["publication_id"] for item in originals},
    )
    assert result.recovery_state["unknown_module"] == {"keep": ["all"]}
    assert (
        await db.fetch_one(
            "SELECT history_high FROM swe_conversation_chats WHERE id=%s",
            (other,),
        )
    )["history_high"] == 0
    evidence = await store.recover_evidence(
        chat_id="first",
        epoch=1,
        refs=["message:q"],
    )
    assert [message.content for message in evidence] == ["question"]
    checkpoint = await store.read_checkpoint_state("first")
    assert checkpoint.record.revision == 1
    assert checkpoint.record.applied_event_sequence == 1
    assert [event.sequence for event in checkpoint.events] == [2, 3]
    reset = await store.reset(
        "first",
        recovery_state=result.recovery_state,
        authority=None,
        reason="clear",
    )
    assert reset.state.current_epoch == 2
    assert (
        await store.recover_evidence(
            chat_id="first",
            epoch=1,
            refs=["message:q"],
        )
        == []
    )
    assert (
        await store.recover_evidence(
            chat_id="first",
            epoch=2,
            refs=["message:q"],
        )
        == []
    )
    assert (
        await db.fetch_one(
            "SELECT COUNT(*) AS n FROM swe_conversation_messages WHERE layer='archive'",
        )
    )["n"] == 1


async def test_runtime_binding_updates_complete_root_only_after_compact_confirmation(
    conversation_test_database,
    tmp_path,
):
    db = conversation_test_database
    _, _, _, store = await setup(db, tmp_path)
    first = source("q", "one")
    result = await store.append_message(
        "first",
        first,
        recovery_state={"revision": 0, "unknown": {"preserve": True}},
        authority=None,
    )
    memory = SimpleNamespace(content=[(first, [])], _compressed_summary="old")
    current = dict(result.recovery_state)

    def accept(state):
        current.clear()
        current.update(state)

    execution = SimpleNamespace(
        accept_committed_state=accept,
        mutation_lock=asyncio.Lock(),
        pending_operation=None,
    )

    async def root():
        return {
            **current,
            "agent": {
                "memory": {
                    "content": [
                        [message.to_dict(), marks]
                        for message, marks in memory.content
                    ],
                    "_compressed_summary": memory._compressed_summary,
                },
            },
        }

    store.bind_memory(memory, "first", execution, root, None)
    await memory.archive_compacted_messages([first], summary="new summary")
    assert memory.content == []
    assert current["agent"]["memory"]["_compressed_summary"] == "new summary"
    assert current["unknown"] == {"preserve": True}
    restored = await store.session_adapter.get_session_state_dict(
        "session",
        "alice",
    )
    assert restored == current


async def test_tool_output_evidence_follows_committed_message_locator(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    from swe.app.conversation_storage.archive_binding import ArchiveBinding
    from swe.app.conversation_storage.history import HistoryStore
    from swe.observability import instrumentation
    from swe.observability.config import EmitterConfig
    from swe.observability.context import bind_context
    from swe.observability.emitter import JsonlEmitter
    from swe.observability.models import ObservabilityContext, Scope
    from swe.observability.projector import _validate_payload

    db = conversation_test_database
    _, _, _, store = await setup(db, tmp_path)
    message = Msg(
        "system",
        [
            {
                "type": "tool_result",
                "id": "call-evidence",
                "name": "read_file",
                "output": [{"type": "text", "text": "private tool output"}],
            },
        ],
        "system",
    )
    memory = SimpleNamespace(
        content=[(message, [])],
        _compressed_summary="",
    )
    execution = SimpleNamespace(accept_committed_state=lambda _state: None)

    async def root_provider():
        return {
            "revision": 0,
            "agent": {
                "memory": {
                    "content": [[message.to_dict(), []]],
                    "_compressed_summary": "",
                },
            },
        }

    binding = ArchiveBinding(
        store=store,
        memory=memory,
        chat_id="first",
        execution=execution,
        root_provider=root_provider,
        authority=None,
    )
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    monkeypatch.setattr(instrumentation, "default_emitter", lambda: emitter)
    context = ObservabilityContext.new_run(
        capture_enabled=True,
        scope=Scope("swe", "source", "tenant", "agent"),
        business_ref={"chat_id": "first"},
    ).new_attempt()

    with bind_context(context):
        span = instrumentation.Observability().span(
            "Tool",
            "execute",
            name="registered.tool",
            tool={
                "tool_key": "read_file",
                "tool_call_id": "call-evidence",
                "tool_execution_id": ("00000000-0000-4000-8000-000000000001"),
                "executor_kind": "agent_tool",
            },
        )
        with instrumentation.bind_tool_span(span):
            await binding.append(message)
        span.end(status="succeeded")
    emitter.close()

    history = HistoryStore(
        db,
        store.scope,
        store.reader.bundles,
        cursor_secret=b"tool-output-evidence-test",
    )
    saved = await history.message_occurrence("first", message.id)
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    evidence = next(
        event
        for event in events
        if event.get("event_type") == "evidence.linked"
    )

    assert saved["status"] == "available"
    assert message.id in json.dumps(saved["message"])
    assert "private tool output" in json.dumps(saved["message"])
    assert evidence["chat_id"] == "first"
    assert evidence["message_id"] == message.id
    assert evidence["content_type"] == "tool_output"
    assert evidence["saved_state"] == "available"
    assert "private tool output" not in json.dumps(evidence)
    assert _validate_payload(json.dumps(evidence))["event_type"] == (
        "evidence.linked"
    )


async def test_assistant_answer_evidence_follows_committed_message_locator(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    from swe.app.conversation_storage.archive_binding import ArchiveBinding
    from swe.app.conversation_storage.history import HistoryStore
    from swe.observability import instrumentation
    from swe.observability.config import EmitterConfig
    from swe.observability.context import bind_context
    from swe.observability.emitter import JsonlEmitter
    from swe.observability.models import ObservabilityContext, Scope
    from swe.observability.projector import _validate_payload

    db = conversation_test_database
    _, _, _, store = await setup(db, tmp_path)

    class Model:
        model_name = "test-model"
        stream = True

        async def __call__(self, *_args, **_kwargs):
            async def response_stream():
                yield SimpleNamespace(
                    id="response-answer-evidence",
                    content=[{"type": "text", "text": "private answer body"}],
                    usage=None,
                    metadata={},
                )

            return response_stream()

    response_chunks = []
    message = Msg(
        "assistant",
        [{"type": "text", "text": "private answer body"}],
        "assistant",
        invocation_id=None,
    )
    memory = SimpleNamespace(content=[(message, [])], _compressed_summary="")
    execution = SimpleNamespace(accept_committed_state=lambda _state: None)

    async def root_provider():
        return {
            "revision": 0,
            "agent": {
                "memory": {
                    "content": [[message.to_dict(), []]],
                    "_compressed_summary": "",
                },
            },
        }

    binding = ArchiveBinding(
        store=store,
        memory=memory,
        chat_id="first",
        execution=execution,
        root_provider=root_provider,
        authority=None,
    )
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    monkeypatch.setattr(instrumentation, "default_emitter", lambda: emitter)
    context = ObservabilityContext.new_run(
        capture_enabled=True,
        scope=Scope("swe", "source", "tenant", "agent"),
        business_ref={"chat_id": "first"},
    ).new_attempt()

    with bind_context(context):
        response = await instrumentation.ObservabilityModelWrapper(
            Model(),
            provider_key="test-provider",
            model_key="test-model",
        )([])
        response_chunks = [chunk async for chunk in response]
        message.invocation_id = response_chunks[-1].id
        await binding.append(message)
    emitter.close()

    history = HistoryStore(
        db,
        store.scope,
        store.reader.bundles,
        cursor_secret=b"assistant-answer-evidence-test",
    )
    saved = await history.message_occurrence("first", message.id)
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    answer_span = next(
        event
        for event in events
        if event["event_name"] == "span.started"
        and event.get("operation") == "chat"
    )
    evidence = next(
        event
        for event in events
        if event.get("event_type") == "evidence.linked"
        and event.get("content_type") == "assistant_answer"
    )

    assert saved["status"] == "available"
    assert message.id in json.dumps(saved["message"])
    assert "private answer body" in json.dumps(saved["message"])
    assert evidence["obs_span_id"] == answer_span["obs_span_id"]
    assert evidence["chat_id"] == "first"
    assert evidence["message_id"] == message.id
    assert evidence["saved_state"] == "available"
    assert "private answer body" not in json.dumps(evidence)
    assert _validate_payload(json.dumps(evidence))["event_type"] == (
        "evidence.linked"
    )


async def test_source_visibility_race_rolls_back_root_archive_and_dependency(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    from swe.app.conversation_storage.errors import IntegrityError
    from swe.app.conversation_storage import publications

    db = conversation_test_database
    session, _, _, store = await setup(db, tmp_path)
    message = source("q", "one")
    result = await store.append_message(
        "first",
        message,
        recovery_state={"revision": 0},
        authority=None,
    )
    snapshot = publications.snapshot_sources

    async def hide_after_snapshot(service, request, plan):
        value = await snapshot(service, request, plan)
        if value.rows:
            await db.execute(
                "UPDATE swe_conversation_messages SET current_visible=0 WHERE id=%s",
                (next(iter(value.rows)),),
            )
        return value

    monkeypatch.setattr(publications, "snapshot_sources", hide_after_snapshot)
    with pytest.raises(IntegrityError, match="changed"):
        await store.compact(
            "first",
            [message],
            recovery_state=result.recovery_state,
            authority=None,
        )
    assert (
        await db.fetch_one(
            "SELECT state_revision FROM swe_conversation_sessions WHERE id=%s",
            (session,),
        )
    )["state_revision"] == 1
    assert (
        await db.fetch_one(
            "SELECT COUNT(*) AS n FROM swe_conversation_messages WHERE layer='archive'",
        )
    )["n"] == 0
    assert (
        await db.fetch_one(
            "SELECT COUNT(*) AS n FROM swe_conversation_retentions WHERE kind='dependency' AND state='active'",
        )
    )["n"] == 0
    assert (
        await db.fetch_one(
            "SELECT COUNT(*) AS n FROM swe_conversation_retentions WHERE kind='reader' AND state='active'",
        )
    )["n"] == 0


async def test_pending_candidate_uses_explicit_key_and_atomic_checkpoint_archive(
    conversation_test_database,
    tmp_path,
):
    from dataclasses import replace
    from swe.agents.memory.chat_checkpoint import PrecompactionCandidate

    db = conversation_test_database
    _, _, _, store = await setup(db, tmp_path)
    message = source("q", "one")
    result = await store.append_message(
        "first",
        message,
        recovery_state={"revision": 0},
        authority=None,
    )
    active = await store.read_checkpoint_state("first")
    candidate = PrecompactionCandidate.new(
        record=replace(
            active.record,
            revision=1,
            source_revision=0,
            applied_event_sequence=1,
        ),
        base_revision=0,
        applied_event_sequence=1,
        source_message_ids=("q",),
    )
    await store.write_pending_candidate("first", candidate)
    result = await store.compact(
        "first",
        [message],
        recovery_state=result.recovery_state,
        authority=None,
        candidate_id=candidate.id,
    )
    assert result.record.revision == 1
    assert result.record.archived_through == result.boundary.id
    current = await store.read_checkpoint_state("first")
    assert current.record == result.record


async def test_runtime_active_owner_generation_fences_late_compact(
    conversation_test_database,
    tmp_path,
):
    from swe.app.conversation_storage.execution import ExecutionAuthority
    from swe.app.conversation_storage.identity import SessionIdentity
    from swe.app.conversation_storage.errors import ConflictError
    from tests.integrated.conversation_storage.test_schema import insert_row

    db = conversation_test_database
    session, chat, _, store = await setup(db, tmp_path)
    message = source("q", "one")
    state = (
        await store.append_message(
            "first",
            message,
            recovery_state={"revision": 0},
            authority=None,
        )
    ).recovery_state
    turn = await insert_row(
        db,
        "swe_conversation_turns",
        {
            "chat_id": chat,
            "session_id": session,
            "question_msg_key": b"active",
            "turn_order": 1,
            "context_epoch": 0,
            "generation": 1,
            "state": "running",
        },
    )
    await db.execute(
        "UPDATE swe_conversation_sessions SET generation=1,active_turn_id=%s,owner_key=%s,lease_until=TIMESTAMPADD(SECOND,60,UTC_TIMESTAMP(6)) WHERE id=%s",
        (turn, b"owner", session),
    )
    authority = ExecutionAuthority(
        SessionIdentity(store.scope, "alice", "console", "session"),
        session,
        chat,
        turn,
        1,
        "owner",
    )
    await db.execute(
        "UPDATE swe_conversation_sessions SET generation=2 WHERE id=%s",
        (session,),
    )
    with pytest.raises(ConflictError, match="authority"):
        await store.compact(
            "first",
            [message],
            recovery_state=state,
            authority=authority,
        )
    assert (
        await db.fetch_one(
            "SELECT COUNT(*) AS n FROM swe_conversation_messages WHERE layer='archive'",
        )
    )["n"] == 0
    assert (
        await db.fetch_one(
            "SELECT COUNT(*) AS n FROM swe_conversation_retentions WHERE kind='dependency' AND state='active'",
        )
    )["n"] == 0
