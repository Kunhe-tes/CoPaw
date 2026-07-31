# -*- coding: utf-8 -*-
"""HTTP contract tests for W+ SOP generated artifacts."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from swe.app.wplus_sop import router as wplus_router
from swe.app.wplus_sop.models import (
    CommandReceipt,
    FinalSopResult,
    OwnershipTuple,
    SessionProjection,
    SessionState,
)
from swe.app.wplus_sop.runtime import get_wplus_safe_stream_trace_registry
from swe.app.wplus_sop.service import store_path_for_workspace
from swe.app.wplus_sop.store import WPlusSopStore


def _build_client(tmp_path, monkeypatch) -> TestClient:
    app = FastAPI()
    app.include_router(wplus_router.router)

    @app.middleware("http")
    async def add_identity(request: Request, call_next):
        request.state.tenant_id = "tenant-1"
        request.state.source_id = "console"
        request.state.user_id = request.headers.get("X-Test-User", "user-1")
        return await call_next(request)

    workspace = SimpleNamespace(
        workspace_dir=tmp_path,
        agent_id="agent-1",
    )

    async def fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        wplus_router,
        "get_agent_for_request",
        fake_get_agent_for_request,
    )
    store = WPlusSopStore(store_path_for_workspace(tmp_path))
    store.create_session(
        SessionProjection(
            sop_session_id="sop-1",
            ownership=OwnershipTuple(
                tenant_id="tenant-1",
                source_id="console",
                user_id="user-1",
                agent_id="agent-1",
                chat_id="chat-1",
                logical_chat_session_id="logical-1",
            ),
            skill_snapshot_id="sha256:miner-v1",
            state=SessionState.COMPLETED,
            state_version=20,
            title="客户经营 SOP",
            final_result=FinalSopResult(
                sop_spec={"name": "客户经营 SOP", "version": 1},
                readable_sop="# 客户经营 SOP",
                html="<h1>客户经营 SOP</h1>",
            ),
        ),
        command_receipt=CommandReceipt(
            command_request_id="cmd-entry",
            command="confirm_entry",
            sop_session_id="sop-1",
            resulting_state_version=20,
        ),
    )
    return TestClient(app)


def test_completed_artifacts_have_authenticated_downloads(
    tmp_path,
    monkeypatch,
) -> None:
    client = _build_client(tmp_path, monkeypatch)

    projection = client.get("/wplus-sop/sessions/sop-1")
    spec_url = projection.json()["artifacts"][0]["download_url"]
    downloaded = client.get(spec_url)

    assert projection.status_code == 200
    assert downloaded.status_code == 200
    assert downloaded.json() == {"name": "客户经营 SOP", "version": 1}
    assert downloaded.headers["content-disposition"] == (
        'attachment; filename="sop_spec.json"'
    )
    assert downloaded.headers["x-content-type-options"] == "nosniff"


def test_artifact_download_is_fail_closed_for_another_user(
    tmp_path,
    monkeypatch,
) -> None:
    client = _build_client(tmp_path, monkeypatch)

    response = client.get(
        "/wplus-sop/sessions/sop-1/artifacts/sop_render_html",
        headers={"X-Test-User": "attacker"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "W+ SOP Session not found"}


@pytest.mark.asyncio
async def test_session_get_checks_for_orphaned_generation_before_read(
    monkeypatch,
) -> None:
    calls: list[str] = []
    record = SimpleNamespace(projection=SimpleNamespace())

    class FakeService:
        async def recover_orphaned_generation_run(self, session_id):
            calls.append(f"recover:{session_id}")

        async def flush_chat_projection_outbox(self):
            calls.append("flush")

        def get_session(self, session_id):
            calls.append(f"get:{session_id}")
            return record

    async def fake_service_for_session(_request, _session_id):
        return FakeService()

    monkeypatch.setattr(
        wplus_router,
        "_service_for_session",
        fake_service_for_session,
    )
    monkeypatch.setattr(
        wplus_router,
        "serialize_session",
        lambda _record: {"state": "RecoverableFailure"},
    )

    response = await wplus_router.get_wplus_sop_session(
        "sop-orphan",
        SimpleNamespace(),
    )

    assert response == {"state": "RecoverableFailure"}
    assert calls == ["recover:sop-orphan", "flush", "get:sop-orphan"]


@pytest.mark.asyncio
async def test_sse_checks_for_orphan_and_emits_recovery_event(
    monkeypatch,
) -> None:
    calls: list[str] = []
    event = SimpleNamespace(
        event_id="evt-orphan",
        state_version=2,
        kind=SimpleNamespace(value="recoverable_failure"),
    )
    record = SimpleNamespace(
        events=[event],
        projection=SimpleNamespace(
            current_run_id="run-orphan",
            is_terminal=True,
        ),
    )

    class FakeService:
        async def recover_orphaned_generation_run(self, session_id):
            calls.append(f"recover:{session_id}")

        def get_session(self, session_id):
            calls.append(f"get:{session_id}")
            return record

    class FakeRequest:
        async def is_disconnected(self):
            return False

    async def fake_service_for_session(_request, _session_id):
        return FakeService()

    monkeypatch.setattr(
        wplus_router,
        "_service_for_session",
        fake_service_for_session,
    )
    monkeypatch.setattr(
        wplus_router,
        "serialize_session",
        lambda _record: {"state": "RecoverableFailure"},
    )

    response = await wplus_router.stream_wplus_sop_events(
        "sop-orphan",
        FakeRequest(),
    )
    chunk = await anext(response.body_iterator)

    assert '"kind": "recoverable_failure"' in chunk
    assert calls == ["recover:sop-orphan", "get:sop-orphan"]


@pytest.mark.asyncio
async def test_sse_emits_changed_safe_trace_without_persisting_an_event(
    monkeypatch,
) -> None:
    workspace = SimpleNamespace()
    registry = get_wplus_safe_stream_trace_registry(workspace)
    registry.start_run("sop-1", "run-1")
    registry.ingest(
        "sop-1",
        "run-1",
        "data: "
        + json.dumps(
            {
                "object": "message",
                "id": "msg-1",
                "type": "message",
                "role": "assistant",
                "status": "in_progress",
                "content": [
                    {
                        "type": "text",
                        "text": "ACCOUNT_SENTINEL=6222020202020202",
                    },
                ],
            },
            ensure_ascii=False,
        )
        + "\n\n",
    )
    persisted_events: list[object] = []
    record = SimpleNamespace(
        events=persisted_events,
        projection=SimpleNamespace(
            current_run_id="run-1",
            state_version=7,
            is_terminal=False,
        ),
    )

    class FakeService:
        def __init__(self):
            self.workspace = workspace

        async def recover_orphaned_generation_run(self, _session_id):
            return None

        def get_session(self, _session_id):
            return record

    class FakeRequest:
        def __init__(self):
            self.checks = 0

        async def is_disconnected(self):
            self.checks += 1
            return self.checks >= 3

    async def fake_service_for_session(_request, _session_id):
        return FakeService()

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(
        wplus_router,
        "_service_for_session",
        fake_service_for_session,
    )
    monkeypatch.setattr(wplus_router.asyncio, "sleep", no_sleep)

    response = await wplus_router.stream_wplus_sop_events(
        "sop-1",
        FakeRequest(),
    )
    chunks = [chunk async for chunk in response.body_iterator]

    assert len(chunks) == 1
    payload = json.loads(chunks[0].removeprefix("data: ").strip())
    assert payload == {
        "event_id": "trace:sop-1:run-1:1",
        "session_id": "sop-1",
        "state_version": 7,
        "kind": "safe_stream_trace",
        "run_id": "run-1",
        "safe_stream_trace": {
            "sequence": 1,
            "summary_text": (
                "message role=assistant type=message status=in_progress "
                "content_types=text content_chars=33 hidden=true"
            ),
            "truncated": False,
        },
    }
    assert "ACCOUNT_SENTINEL" not in chunks[0]
    assert "6222020202020202" not in chunks[0]
    assert persisted_events == []

    reconnect_response = await wplus_router.stream_wplus_sop_events(
        "sop-1",
        FakeRequest(),
    )
    reconnect_chunks = [chunk async for chunk in reconnect_response.body_iterator]
    assert len(reconnect_chunks) == 1
    reconnect_payload = json.loads(
        reconnect_chunks[0].removeprefix("data: ").strip(),
    )
    assert reconnect_payload["safe_stream_trace"]["sequence"] == 1
    assert persisted_events == []
