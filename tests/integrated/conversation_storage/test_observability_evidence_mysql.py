# -*- coding: utf-8 -*-
"""Tool evidence producer to authorized NAS-backed API contract."""

from __future__ import annotations

import io
import base64
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from agentscope.message import Msg
import httpx
from fastapi import FastAPI, Request
import pytest

from swe.app.conversation_storage.archive_binding import ArchiveBinding
from swe.app.conversation_storage.bundle import BundleStore
from swe.app.conversation_storage.history import HistoryStore
from swe.observability import instrumentation
from swe.observability.config import EmitterConfig
from swe.observability.context import bind_context
from swe.observability.emitter import JsonlEmitter
from swe.observability.models import ObservabilityContext, Scope
from swe.observability.projector import InboxProjector
from swe.observability.query import router as observability_router
from swe.observability.store import ObservabilityStore
from tests.integrated.conversation_storage.conftest import apply_sql_script
from tests.integrated.conversation_storage.test_archive_runtime_mysql import (
    setup,
)

_OBSERVABILITY_DDL = (
    Path(__file__).parents[3]
    / ".scratch"
    / "agent-observability"
    / "schema-draft.sql"
)


async def _publish_tool_and_assistant(
    archive,
    observability,
    attempt,
    *,
    tool_output="private tool output",
    compact_tool_output=False,
):
    tool_message = Msg(
        "system",
        [
            {
                "type": "tool_result",
                "id": "call-evidence-api",
                "name": "read_file",
                "output": [{"type": "text", "text": tool_output}],
            },
        ],
        "system",
    )
    memory = SimpleNamespace(
        content=[(tool_message, [])],
        _compressed_summary="",
    )
    committed_state = {"revision": 0}

    def accept_committed_state(state):
        committed_state.clear()
        committed_state.update(state)

    async def root_provider():
        return {
            **committed_state,
            "agent": {
                "memory": {
                    "content": [
                        [saved_message.to_dict(), []]
                        for saved_message, _ in memory.content
                    ],
                    "_compressed_summary": "",
                },
            },
        }

    binding = ArchiveBinding(
        store=archive,
        memory=memory,
        chat_id="first",
        execution=SimpleNamespace(
            accept_committed_state=accept_committed_state,
        ),
        root_provider=root_provider,
        authority=None,
    )
    with bind_context(attempt):
        tool_span = observability.span(
            "Tool",
            "execute",
            name="registered.tool",
            tool={
                "tool_key": "read_file",
                "tool_call_id": "call-evidence-api",
                "tool_execution_id": "00000000-0000-4000-8000-000000000001",
                "executor_kind": "agent_tool",
            },
        )
        with instrumentation.bind_tool_span(tool_span):
            if compact_tool_output:
                instrumentation.mark_tool_output_compacted(tool_message.id)
            await binding.append(tool_message)
        tool_span.end(status="succeeded")

        class Model:
            stream = True

            async def __call__(self, *_args, **_kwargs):
                async def response_stream():
                    yield SimpleNamespace(
                        id="response-evidence-api",
                        content=[
                            {
                                "type": "text",
                                "text": "private assistant answer",
                            },
                        ],
                        usage=None,
                        metadata={},
                    )

                return response_stream()

        response = await instrumentation.ObservabilityModelWrapper(
            Model(),
            provider_key="test-provider",
            model_key="test-model",
        )([])
        response_chunks = [chunk async for chunk in response]
        answer = Msg(
            "assistant",
            [{"type": "text", "text": "private assistant answer"}],
            "assistant",
            invocation_id=response_chunks[-1].id,
        )
        assert answer.invocation_id == "response-evidence-api"
        memory.content.append((answer, []))
        await binding.append(answer)
    return tool_span, tool_message, answer


async def _append_and_compact_answer(archive, observer, attempt, message):
    committed_state = {"revision": 0}
    memory = SimpleNamespace(
        content=[(message, [])],
        _compressed_summary="",
    )

    def accept_committed_state(state):
        committed_state.clear()
        committed_state.update(state)

    async def root_provider():
        return {
            **committed_state,
            "agent": {
                "memory": {
                    "content": [
                        [saved_message.to_dict(), []]
                        for saved_message, _ in memory.content
                    ],
                    "_compressed_summary": "",
                },
            },
        }

    binding = ArchiveBinding(
        store=archive,
        memory=memory,
        chat_id="first",
        execution=SimpleNamespace(
            accept_committed_state=accept_committed_state,
        ),
        root_provider=root_provider,
        authority=None,
    )

    class Model:
        stream = True

        async def __call__(self, *_args, **_kwargs):
            async def chunks():
                yield SimpleNamespace(
                    id=message.invocation_id,
                    content=message.content,
                    usage=None,
                    metadata={},
                )

            return chunks()

    with bind_context(attempt):
        response = await instrumentation.ObservabilityModelWrapper(
            Model(),
            provider_key="test-provider",
            model_key="test-model",
        )([])
        response_chunks = [chunk async for chunk in response]
        assert response_chunks[-1].id == message.invocation_id
        await binding.append(message)
    await archive.compact(
        "first",
        [message],
        recovery_state=committed_state,
        authority=None,
    )


async def _append_duplicate_tool_occurrences(archive, attempt):
    messages = [
        Msg(
            "system",
            [
                {
                    "type": "tool_result",
                    "id": "duplicate-tool-call",
                    "name": "read_file",
                    "output": [{"type": "text", "text": body}],
                },
            ],
            "system",
        )
        for body in ("first duplicate body", "second duplicate body")
    ]
    for message in messages:
        message.id = "duplicate-tool-message"
    memory = SimpleNamespace(
        content=[],
        _compressed_summary="",
    )
    committed_state = {"revision": 0}

    def accept_committed_state(state):
        committed_state.clear()
        committed_state.update(state)

    async def root_provider():
        return {
            **committed_state,
            "agent": {
                "memory": {
                    "content": [
                        [saved_message.to_dict(), []]
                        for saved_message, _ in memory.content
                    ],
                    "_compressed_summary": "",
                },
            },
        }

    binding = ArchiveBinding(
        store=archive,
        memory=memory,
        chat_id="first",
        execution=SimpleNamespace(
            accept_committed_state=accept_committed_state,
        ),
        root_provider=root_provider,
        authority=None,
    )
    spans = []
    for message in messages:
        memory.content.append((message, []))
        with bind_context(attempt):
            span = instrumentation.Observability().span(
                "Tool",
                "execute",
                name="registered.tool",
            )
            assert span is not None
            with instrumentation.bind_tool_span(span):
                await binding.append(message)
            span.end(status="succeeded")
        spans.append(span)
    chat = await archive.reader.chat("first")
    rows = await archive.reader.session_messages(
        chat["session_id"],
        layers=("memory",),
    )
    rows = [
        row for row in rows if row["source_msg_key"] == messages[0].id.encode()
    ]
    assert [row["source_occurrence_no"] for row in rows] == [0, 1], rows
    assert [row["layer"] for row in rows] == ["memory", "memory"]
    assert all(row.get("archive_chat_id") is None for row in rows)
    return spans, messages


async def _read_evidence_pages(client, url, headers, *, content_type):
    chunks = []
    params = {}
    while True:
        response = await client.get(url, headers=headers, params=params)
        assert response.status_code == 200
        item = next(
            item
            for item in response.json()["items"]
            if item["content_type"] == content_type
        )
        if not chunks:
            assert item["status"] in {"truncated", "compacted"}
        chunk = item.get("message_chunk")
        if chunk is not None:
            chunks.append(
                base64.urlsafe_b64decode(chunk + "=" * (-len(chunk) % 4)),
            )
        cursor = item.get("next_cursor")
        if cursor is None:
            return item, json.loads(b"".join(chunks))
        params = {"cursor": cursor}


async def _assert_other_source_forbidden(client, url):
    response = await client.get(
        url,
        headers={"X-User-Role": "manager", "X-Source-Id": "other"},
    )
    assert response.status_code == 404


async def _remove_chat_bundles(database, bundles, chat_key):
    chat = await database.fetch_one(
        "SELECT id FROM swe_conversation_chats WHERE external_chat_key=%s",
        (chat_key.encode("utf-8"),),
    )
    publications = await database.fetch_all(
        "SELECT relative_path FROM swe_conversation_publications "
        "WHERE chat_id=%s AND state='committed'",
        (chat["id"],),
    )
    for publication in publications:
        path = Path(bundles.root) / publication["relative_path"]
        if path.exists():
            path.unlink()


def _single_evidence_item(response):
    items = response.json()["items"]
    assert len(items) == 1
    return items[0]


def _assert_evidence_unavailable(response):
    assert response.status_code == 200
    items = response.json()["items"]
    answer = next(
        item for item in items if item["content_type"] == "assistant_answer"
    )
    model_input = next(
        item for item in items if item["content_type"] == "model_input"
    )
    assert answer["status"] == "unavailable"
    assert "message" not in answer
    assert model_input["status"] == "not_saved"


def _assert_archived_evidence_refs(references):
    assert len(references) == 2
    answer = next(
        item
        for item in references
        if item["content_type"] == "assistant_answer"
    )
    model_input = next(
        item for item in references if item["content_type"] == "model_input"
    )
    assert answer["occurrence_id"] == 0
    assert model_input["saved_state"] == "not_saved"


def _assert_assistant_evidence_response(response, span_id, answer):
    items = response.json()["items"]
    assistant = next(
        item for item in items if item["content_type"] == "assistant_answer"
    )
    model_input = next(
        item for item in items if item["content_type"] == "model_input"
    )
    assert assistant["status"] == "available"
    assert assistant["message"]["id"] == answer.id
    assert "private assistant answer" in json.dumps(assistant["message"])
    assert model_input["status"] == "not_saved"
    assert "message" not in model_input
    assert model_input["reference_id"] == span_id


def _events_without_private_body(stream, body):
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert body not in stream.getvalue()
    return events


def _assert_pending_and_saved_evidence(events, count, *, compacted=0):
    states = [
        (event.get("event_type"), event.get("saved_state"))
        for event in events
        if event.get("event_type") in {"evidence.pending", "evidence.linked"}
        and event.get("content_type") in {"tool_output", "assistant_answer"}
    ]
    assert states.count(("evidence.pending", "pending")) == count
    assert states.count(("evidence.linked", "available")) == count - compacted
    assert states.count(("evidence.linked", "compacted")) == compacted
    linked = [
        event
        for event in events
        if event.get("event_type") == "evidence.linked"
    ]
    pending = [
        event
        for event in events
        if event.get("event_type") == "evidence.pending"
    ]
    linked = [
        event
        for event in linked
        if event.get("content_type") in {"tool_output", "assistant_answer"}
    ]
    assert len(linked) == count
    assert {event.get("reference_id") for event in pending} == {
        event.get("reference_id") for event in linked
    }
    assert all(event.get("occurrence_id") == 0 for event in linked)


@pytest.mark.asyncio
async def test_tool_and_assistant_evidence_reach_authorized_api_after_nas_commit(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    database = conversation_test_database
    await apply_sql_script(database, _OBSERVABILITY_DDL)
    _, _, _, archive = await setup(database, tmp_path)
    await database.execute(
        "UPDATE swe_conversation_chats SET metadata_text=%s "
        "WHERE external_chat_key=%s",
        (json.dumps({"source_id": "source", "agent_id": "agent"}), b"first"),
    )

    store = ObservabilityStore(database)
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    monkeypatch.setattr(instrumentation, "default_emitter", lambda: emitter)
    observability = instrumentation.Observability(emitter)
    context = observability.admit_run(
        scope=Scope("swe", "source", "tenant", "agent"),
        business_ref={"chat_id": "first", "session_id": "session"},
        enabled=True,
    )
    attempt = observability.start_attempt(context)
    observability.run_state(attempt, status="running")
    tool_span, message, answer = await _publish_tool_and_assistant(
        archive,
        observability,
        attempt,
        compact_tool_output=True,
    )
    observability.end_attempt(attempt, status="succeeded")
    observability.end_run(attempt, status="succeeded")
    assert emitter.close(timeout=2) == 0

    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    _assert_pending_and_saved_evidence(events, 2, compacted=1)
    assistant_span_id = next(
        event["obs_span_id"]
        for event in events
        if event["event_name"] == "span.started"
        and event.get("operation") == "chat"
    )
    async with database.transaction() as session:
        for event in events:
            await session.insert(
                "INSERT INTO swe_agentobs_inbox (payload_text) VALUES (%s)",
                (json.dumps(event, separators=(",", ":")),),
            )
    projector = InboxProjector(store, poll_seconds=0.01)
    while await projector.project_batch():
        pass
    tool_refs = await store.list_span_evidence_refs(
        run_id=context.obs_run_id,
        span_id=tool_span.span_id,
        source_ids=["source"],
    )
    assert (
        len(tool_refs) == 1
        and tool_refs[0]["saved_state"] == "compacted"
        and tool_refs[0]["occurrence_id"] == 0
    )

    history = HistoryStore(
        database,
        archive.scope,
        archive.reader.bundles,
        cursor_secret=b"tool-evidence-api-mysql-test",
    )
    workspace = SimpleNamespace(
        agent_id="agent",
        conversation_storage=SimpleNamespace(history=history),
    )
    monkeypatch.setattr(
        "swe.app.runner.api.get_workspace",
        AsyncMock(return_value=workspace),
    )
    api = FastAPI()
    api.state.agent_observability_store = store

    @api.middleware("http")
    async def bind_test_source(request: Request, call_next):
        request.state.source_id = request.headers.get("X-Source-Id")
        return await call_next(request)

    api.include_router(observability_router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api),
        base_url="http://agentobs.test",
    ) as client:
        tool_response = await client.get(
            f"/agent-observability/runs/{context.obs_run_id}"
            f"/spans/{tool_span.span_id}/evidence",
            headers={"X-User-Role": "manager", "X-Source-Id": "source"},
        )
        assistant_response = await client.get(
            f"/agent-observability/runs/{context.obs_run_id}"
            f"/spans/{assistant_span_id}/evidence",
            headers={"X-User-Role": "manager", "X-Source-Id": "source"},
        )

    assert tool_response.status_code == 200
    tool_item = _single_evidence_item(tool_response)
    assert tool_item["status"] == "compacted"
    assert tool_item["content_type"] == "tool_output"
    assert tool_item["message"]["id"] == message.id
    assert "private tool output" in json.dumps(tool_item["message"])

    assert assistant_response.status_code == 200
    _assert_assistant_evidence_response(
        assistant_response,
        assistant_span_id,
        answer,
    )
    assert "private tool output" not in json.dumps(events)
    assert "private assistant answer" not in json.dumps(events)


@pytest.mark.asyncio
async def test_long_evidence_continues_through_authorized_mysql_nas_api(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "SWE_AGENTOBS_CURSOR_SECRET",
        "evidence-integration-secret-at-least-32",
    )
    database = conversation_test_database
    await apply_sql_script(database, _OBSERVABILITY_DDL)
    _, _, _, archive = await setup(database, tmp_path)
    await database.execute(
        "UPDATE swe_conversation_chats SET metadata_text=%s WHERE external_chat_key=%s",
        (json.dumps({"source_id": "source", "agent_id": "agent"}), b"first"),
    )
    store = ObservabilityStore(database)
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    monkeypatch.setattr(instrumentation, "default_emitter", lambda: emitter)
    observer = instrumentation.Observability(emitter)
    context = observer.admit_run(
        scope=Scope("swe", "source", "tenant", "agent"),
        business_ref={"chat_id": "first", "session_id": "session"},
        enabled=True,
    )
    attempt = observer.start_attempt(context)
    original_text = "private multilingual 内容 " * 5000
    from swe.agents.utils.tool_output_compaction import compact_text_output

    compacted = compact_text_output(
        original_text,
        max_bytes=32 * 1024,
        artifact_dir=tmp_path / "tool_result",
        workspace_dir=tmp_path,
    )
    assert compacted.artifact_path is not None
    tool_span, message, _ = await _publish_tool_and_assistant(
        archive,
        observer,
        attempt,
        tool_output=compacted.text,
        compact_tool_output=True,
    )
    observer.end_attempt(attempt, status="succeeded")
    observer.end_run(context, status="succeeded")
    assert emitter.close(timeout=2) == 0
    events = _events_without_private_body(stream, original_text)
    async with database.transaction() as session:
        for event in events:
            await session.insert(
                "INSERT INTO swe_agentobs_inbox (payload_text) VALUES (%s)",
                (json.dumps(event, separators=(",", ":")),),
            )
    while await InboxProjector(store).project_batch():
        pass
    history = HistoryStore(
        database,
        archive.scope,
        archive.reader.bundles,
        cursor_secret=b"evidence-continuation-test",
    )
    workspace = SimpleNamespace(
        agent_id="agent",
        conversation_storage=SimpleNamespace(history=history),
    )
    monkeypatch.setattr(
        "swe.app.runner.api.get_workspace",
        AsyncMock(return_value=workspace),
    )
    api = FastAPI()
    api.state.agent_observability_store = store

    @api.middleware("http")
    async def bind_test_source(request: Request, call_next):
        request.state.source_id = request.headers.get("X-Source-Id")
        return await call_next(request)

    api.include_router(observability_router)
    url = f"/agent-observability/runs/{context.obs_run_id}/spans/{tool_span.span_id}/evidence"
    headers = {"X-User-Role": "manager", "X-Source-Id": "source"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api),
        base_url="http://agentobs.test",
    ) as client:
        item, decoded = await _read_evidence_pages(
            client,
            url,
            headers,
            content_type="tool_output",
        )
        forbidden = await client.get(
            url,
            headers={**headers, "X-Source-Id": "other"},
        )
    assert forbidden.status_code == 404
    assert decoded["id"] == message.id
    saved_tool_output = json.loads(decoded["content"][0]["data"]["output"])
    assert saved_tool_output[0]["text"] == compacted.text
    assert original_text not in json.dumps(decoded, ensure_ascii=False)
    assert item["status"] == "compacted"


@pytest.mark.asyncio
async def test_archived_message_evidence_reads_exact_occurrence_through_api(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "SWE_AGENTOBS_CURSOR_SECRET",
        "archive-evidence-cursor-secret-at-least-32",
    )
    database = conversation_test_database
    await apply_sql_script(database, _OBSERVABILITY_DDL)
    _, _, _, archive = await setup(database, tmp_path)
    await database.execute(
        "UPDATE swe_conversation_chats SET metadata_text=%s "
        "WHERE external_chat_key=%s",
        (json.dumps({"source_id": "source", "agent_id": "agent"}), b"first"),
    )
    message = Msg(
        "assistant",
        [{"type": "text", "text": "archived private answer " * 5000}],
        "assistant",
        invocation_id="archived-answer-invocation",
    )
    message.id = "archived-answer"

    store = ObservabilityStore(database)
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    monkeypatch.setattr(instrumentation, "default_emitter", lambda: emitter)
    observer = instrumentation.Observability(emitter)
    context = observer.admit_run(
        scope=Scope("swe", "source", "tenant", "agent"),
        business_ref={"chat_id": "first", "session_id": "session"},
        enabled=True,
    )
    attempt = observer.start_attempt(context)
    await _append_and_compact_answer(archive, observer, attempt, message)
    observer.end_attempt(attempt, status="succeeded")
    observer.end_run(context, status="succeeded")
    assert emitter.close(timeout=1) == 0
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert "archived private answer" not in stream.getvalue()
    linked_event = next(
        event
        for event in events
        if event.get("event_type") == "evidence.linked"
        and event.get("content_type") == "assistant_answer"
    )
    assert linked_event["occurrence_id"] == 0
    async with database.transaction() as session:
        for event in events:
            await session.insert(
                "INSERT INTO swe_agentobs_inbox (payload_text) VALUES (%s)",
                (json.dumps(event, separators=(",", ":")),),
            )
    while await InboxProjector(store).project_batch():
        pass
    references = await store.list_span_evidence_refs(
        run_id=context.obs_run_id,
        span_id=linked_event["obs_span_id"],
        source_ids=["source"],
    )
    _assert_archived_evidence_refs(references)

    history = HistoryStore(
        database,
        archive.scope,
        archive.reader.bundles,
        cursor_secret=b"archived-evidence-api-test",
    )
    workspace = SimpleNamespace(
        agent_id="agent",
        conversation_storage=SimpleNamespace(history=history),
    )
    monkeypatch.setattr(
        "swe.app.runner.api.get_workspace",
        AsyncMock(return_value=workspace),
    )
    api = FastAPI()
    api.state.agent_observability_store = store

    @api.middleware("http")
    async def bind_test_source(request: Request, call_next):
        request.state.source_id = request.headers.get("X-Source-Id")
        return await call_next(request)

    api.include_router(observability_router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api),
        base_url="http://agentobs.test",
    ) as client:
        url = (
            f"/agent-observability/runs/{context.obs_run_id}"
            f"/spans/{linked_event['obs_span_id']}/evidence"
        )
        response_headers = {
            "X-User-Role": "manager",
            "X-Source-Id": "source",
        }
        item, decoded = await _read_evidence_pages(
            client,
            url,
            response_headers,
            content_type="assistant_answer",
        )
        await _assert_other_source_forbidden(client, url)
        await _remove_chat_bundles(
            database,
            archive.bundles,
            "first",
        )
        deleted = await client.get(url, headers=response_headers)
    assert item["status"] == "available"
    assert item["content_type"] == "assistant_answer"
    assert decoded["id"] == message.id
    assert decoded["content"][0]["text"] == "archived private answer " * 5000
    _assert_evidence_unavailable(deleted)


@pytest.mark.asyncio
async def test_duplicate_message_evidence_reads_exact_occurrences_through_api(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    database = conversation_test_database
    await apply_sql_script(database, _OBSERVABILITY_DDL)
    _, _, _, archive = await setup(database, tmp_path)
    await database.execute(
        "UPDATE swe_conversation_chats SET metadata_text=%s "
        "WHERE external_chat_key=%s",
        (json.dumps({"source_id": "source", "agent_id": "agent"}), b"first"),
    )
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    monkeypatch.setattr(instrumentation, "default_emitter", lambda: emitter)
    observer = instrumentation.Observability(emitter)
    context = observer.admit_run(
        scope=Scope("swe", "source", "tenant", "agent"),
        business_ref={"chat_id": "first", "session_id": "session"},
        enabled=True,
    )
    attempt = observer.start_attempt(context)
    spans, messages = await _append_duplicate_tool_occurrences(
        archive,
        attempt,
    )
    observer.end_attempt(attempt, status="succeeded")
    observer.end_run(context, status="succeeded")
    assert emitter.close(timeout=1) == 0
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    links = [
        event
        for event in events
        if event.get("event_type") == "evidence.linked"
    ]
    assert len(links) == 2
    assert [event["occurrence_id"] for event in links] == [0, 1]
    assert all(event["message_id"] == messages[0].id for event in links)
    assert all(
        body not in stream.getvalue()
        for body in ("first duplicate body", "second duplicate body")
    )

    store = ObservabilityStore(database)
    async with database.transaction() as session:
        for event in events:
            await session.insert(
                "INSERT INTO swe_agentobs_inbox (payload_text) VALUES (%s)",
                (json.dumps(event, separators=(",", ":")),),
            )
    while await InboxProjector(store).project_batch():
        pass
    direct_refs = await store.list_span_evidence_refs(
        run_id=context.obs_run_id,
        span_id=spans[0].span_id,
        source_ids=["source"],
    )
    assert len(direct_refs) == 1
    history = HistoryStore(
        database,
        archive.scope,
        archive.reader.bundles,
        cursor_secret=b"duplicate-evidence-api-test",
    )
    monkeypatch.setattr(
        "swe.app.runner.api.get_workspace",
        AsyncMock(
            return_value=SimpleNamespace(
                agent_id="agent",
                conversation_storage=SimpleNamespace(history=history),
            ),
        ),
    )
    api = FastAPI()
    api.state.agent_observability_store = store

    @api.middleware("http")
    async def bind_test_source(request: Request, call_next):
        request.state.source_id = "source"
        return await call_next(request)

    api.include_router(observability_router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api),
        base_url="http://agentobs.test",
    ) as client:
        for index, (link, span) in enumerate(zip(links, spans)):
            response = await client.get(
                f"/agent-observability/runs/{context.obs_run_id}"
                f"/spans/{span.span_id}/evidence",
                headers={"X-User-Role": "manager", "X-Source-Id": "source"},
            )
            assert response.status_code == 200
            item = _single_evidence_item(response)
            assert item["status"] == "available", item
            assert item["occurrence_id"] == index
            assert item["message"]["id"] == messages[0].id
            expected_body = (
                "first duplicate body"
                if index == 0
                else "second duplicate body"
            )
            assert expected_body in json.dumps(
                item["message"],
                ensure_ascii=False,
            )


@pytest.mark.asyncio
async def test_evidence_limit_applies_after_pending_available_resolution(
    conversation_test_database,
):
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    database = conversation_test_database
    await apply_sql_script(database, _OBSERVABILITY_DDL)
    store = ObservabilityStore(database)
    run_id, span_id = str(uuid4()), str(uuid4())
    start = datetime.now(timezone.utc).replace(tzinfo=None)
    async with database.transaction() as session:
        for index in range(80):
            is_available = index >= 40
            locator_index = index - 40 if is_available else index
            payload = {
                "event_type": (
                    "evidence.linked" if is_available else "evidence.pending"
                ),
                "chat_id": "chat-a",
                "message_id": f"message-{locator_index}",
                "reference_id": f"reference-{locator_index}",
                "content_type": "tool_output",
                "saved_state": "available" if is_available else "pending",
            }
            if is_available:
                payload["occurrence_id"] = 0
            await session.insert(
                "INSERT INTO swe_agentobs_events "
                "(event_id,schema_version,event_name,entity_kind,entity_id,phase_key,local_seq,"
                "run_id,span_id,service_unit_key,source_key,tenant_key,agent_key,occurred_at,"
                "first_ingest_id,producer_id,metadata_text) "
                "VALUES (%s,1,'span.event','span',%s,'event',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    str(uuid4()),
                    span_id,
                    index,
                    run_id,
                    span_id,
                    b"swe",
                    b"source",
                    b"tenant",
                    b"agent",
                    start + timedelta(microseconds=index),
                    index + 1,
                    "evidence-test",
                    json.dumps(payload, separators=(",", ":")),
                ),
            )

    refs = await store.list_span_evidence_refs(
        run_id=run_id,
        span_id=span_id,
        source_ids=["source"],
        limit=32,
    )
    assert len(refs) == 32
    assert [item["message_id"] for item in refs] == [
        f"message-{index}" for index in range(32)
    ]
    assert all(item["saved_state"] == "available" for item in refs)


@pytest.mark.asyncio
async def test_new_occurrence_pending_is_not_hidden_by_previous_linked_evidence(
    conversation_test_database,
):
    from datetime import datetime, timezone
    from uuid import uuid4

    database = conversation_test_database
    await apply_sql_script(database, _OBSERVABILITY_DDL)
    store = ObservabilityStore(database)
    run_id, span_id = str(uuid4()), str(uuid4())
    start = datetime.now(timezone.utc).replace(tzinfo=None)
    records = [
        (
            1,
            "f0000000-0000-4000-8000-000000000001",
            {
                "event_type": "evidence.linked",
                "chat_id": "chat-a",
                "message_id": "message-a",
                "occurrence_id": 0,
                "content_type": "tool_output",
                "saved_state": "available",
            },
        ),
        (
            2,
            "e0000000-0000-4000-8000-000000000002",
            {
                "event_type": "evidence.pending",
                "chat_id": "chat-a",
                "message_id": "message-a",
                "content_type": "tool_output",
                "saved_state": "pending",
                "reference_id": "second-append",
            },
        ),
    ]

    async def insert_records(batch):
        async with database.transaction() as session:
            for order, event_id, payload in batch:
                await session.insert(
                    "INSERT INTO swe_agentobs_events "
                    "(event_id,schema_version,event_name,entity_kind,entity_id,"
                    "phase_key,local_seq,run_id,span_id,service_unit_key,"
                    "source_key,tenant_key,agent_key,occurred_at,first_ingest_id,"
                    "producer_id,metadata_text) VALUES "
                    "(%s,1,'span.event','span',%s,'event',%s,%s,%s,%s,%s,%s,"
                    "%s,%s,%s,%s,%s)",
                    (
                        event_id,
                        span_id,
                        order,
                        run_id,
                        span_id,
                        b"swe",
                        b"source",
                        b"tenant",
                        b"agent",
                        start,
                        order,
                        "evidence-occurrence-test",
                        json.dumps(payload, separators=(",", ":")),
                    ),
                )

    await insert_records(records)
    refs = await store.list_span_evidence_refs(
        run_id=run_id,
        span_id=span_id,
        source_ids=["source"],
    )
    assert {
        (item.get("occurrence_id"), item["saved_state"]) for item in refs
    } == {(0, "available"), (None, "pending")}

    await insert_records(
        [
            (
                3,
                "a0000000-0000-4000-8000-000000000003",
                {
                    "event_type": "evidence.linked",
                    "chat_id": "chat-a",
                    "message_id": "message-a",
                    "occurrence_id": 1,
                    "content_type": "tool_output",
                    "saved_state": "available",
                    "reference_id": "second-append",
                },
            ),
        ],
    )
    refs = await store.list_span_evidence_refs(
        run_id=run_id,
        span_id=span_id,
        source_ids=["source"],
    )
    assert {(item["occurrence_id"], item["saved_state"]) for item in refs} == {
        (0, "available"),
        (1, "available"),
    }

    pending = {
        "event_type": "evidence.pending",
        "chat_id": "chat-a",
        "message_id": "message-a",
        "content_type": "tool_output",
        "saved_state": "pending",
    }
    await insert_records(
        [
            (4, str(uuid4()), {**pending, "reference_id": "failed-append"}),
            (5, str(uuid4()), {**pending, "reference_id": "retry-append"}),
            (
                6,
                str(uuid4()),
                {
                    **pending,
                    "event_type": "evidence.linked",
                    "saved_state": "available",
                    "occurrence_id": 2,
                    "reference_id": "retry-append",
                },
            ),
        ],
    )
    refs = await store.list_span_evidence_refs(
        run_id=run_id,
        span_id=span_id,
        source_ids=["source"],
    )
    assert {
        (item.get("occurrence_id"), item["saved_state"]) for item in refs
    } == {
        (0, "available"),
        (1, "available"),
        (2, "available"),
        (None, "pending"),
    }
    pending_ref = next(
        item for item in refs if item["saved_state"] == "pending"
    )
    assert pending_ref["reference_id"] == "failed-append"

    legacy_pending = {
        "event_type": "evidence.pending",
        "chat_id": "chat-a",
        "message_id": "legacy-message",
        "content_type": "tool_output",
        "saved_state": "pending",
    }
    await insert_records(
        [
            (7, str(uuid4()), legacy_pending),
            (
                8,
                str(uuid4()),
                {
                    **legacy_pending,
                    "event_type": "evidence.linked",
                    "occurrence_id": 0,
                    "saved_state": "available",
                },
            ),
            (
                9,
                str(uuid4()),
                {
                    "event_type": "evidence.pending",
                    "chat_id": "chat-a",
                    "message_id": "legacy-pending-only",
                    "content_type": "tool_output",
                    "saved_state": "pending",
                },
            ),
        ],
    )
    refs = await store.list_span_evidence_refs(
        run_id=run_id,
        span_id=span_id,
        source_ids=["source"],
    )
    legacy_items = [
        item for item in refs if item["message_id"] == "legacy-message"
    ]
    assert {item["saved_state"] for item in legacy_items} == {
        "unresolved",
        "available",
    }
    pending_only = [
        item for item in refs if item["message_id"] == "legacy-pending-only"
    ]
    assert len(pending_only) == 1
    assert pending_only[0]["saved_state"] == "pending"
