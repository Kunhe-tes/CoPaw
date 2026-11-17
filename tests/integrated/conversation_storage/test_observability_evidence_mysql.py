# -*- coding: utf-8 -*-
"""Tool evidence producer to authorized NAS-backed API contract."""

from __future__ import annotations

import io
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


async def _publish_tool_and_assistant(archive, observability, attempt):
    tool_message = Msg(
        "system",
        [
            {
                "type": "tool_result",
                "id": "call-evidence-api",
                "name": "read_file",
                "output": [{"type": "text", "text": "private tool output"}],
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
    )
    observability.end_attempt(attempt, status="succeeded")
    observability.end_run(attempt, status="succeeded")
    assert emitter.close(timeout=2) == 0

    events = [json.loads(line) for line in stream.getvalue().splitlines()]
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
    tool_item = tool_response.json()["items"][0]
    assert tool_item["status"] == "available"
    assert tool_item["content_type"] == "tool_output"
    assert tool_item["message"]["id"] == message.id
    assert "private tool output" in json.dumps(tool_item["message"])

    assert assistant_response.status_code == 200
    assistant_item = assistant_response.json()["items"][0]
    assert assistant_item["status"] == "available"
    assert assistant_item["content_type"] == "assistant_answer"
    assert assistant_item["message"]["id"] == answer.id
    assert "private assistant answer" in json.dumps(assistant_item["message"])
    assert "private tool output" not in json.dumps(events)
    assert "private assistant answer" not in json.dumps(events)
