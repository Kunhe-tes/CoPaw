# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.swe.app.routers import console as console_router


class _FakeConsoleChannel:
    def resolve_session_id(self, sender_id: str, channel_meta: dict) -> str:
        return channel_meta.get("session_id") or f"console:{sender_id}"

    async def stream_one(self, payload):
        yield payload


class _FakeChannelManager:
    async def get_channel(self, name: str):
        assert name == "console"
        return _FakeConsoleChannel()


class _FakeChatManager:
    async def get_or_create_chat(
        self,
        session_id: str,
        user_id: str,
        channel_id: str,
        name: str,
        meta=None,
    ):
        _ = meta
        return SimpleNamespace(
            id=f"chat:{session_id}",
            session_id=session_id,
            user_id=user_id,
            channel=channel_id,
            name=name,
        )


class _FakeTaskTracker:
    async def attach_or_start(self, _run_key, _payload, _stream_fn):
        return object(), True

    async def attach(self, _run_key):
        return object()

    async def stream_from_queue(self, _queue, _run_key):
        await asyncio.sleep(0.03)
        yield 'data: {"done": true}\n\n'


def _build_upload_client(monkeypatch, media_dir):
    app = FastAPI()
    app.include_router(console_router.router)

    class _FakeUploadChannelManager:
        async def get_channel(self, name: str):
            assert name == "console"
            return SimpleNamespace(media_dir=media_dir)

    workspace = SimpleNamespace(
        channel_manager=_FakeUploadChannelManager(),
    )

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )
    return TestClient(app)


@pytest.mark.parametrize(
    "file_name",
    ["script.py", "Example.JAVA", "app.min.js", "Program.cs"],
)
def test_console_upload_rejects_executable_code_extensions_without_writing(
    tmp_path,
    monkeypatch,
    file_name,
) -> None:
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    client = _build_upload_client(monkeypatch, media_dir)

    response = client.post(
        "/console/upload",
        files={"file": (file_name, b"code", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Unsupported file type for chat attachment upload",
    }
    assert list(media_dir.iterdir()) == []


@pytest.mark.parametrize(
    "file_name",
    ["archive.zip", "script.py.zip", "report.pdf"],
)
def test_console_upload_allows_archive_and_document_extensions(
    tmp_path,
    monkeypatch,
    file_name,
) -> None:
    media_dir = tmp_path / "media"
    client = _build_upload_client(monkeypatch, media_dir)

    response = client.post(
        "/console/upload",
        files={"file": (file_name, b"content", "application/octet-stream")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["file_name"] == file_name
    assert body["size"] == len(b"content")

    stored_files = list(media_dir.iterdir())
    assert len(stored_files) == 1
    assert stored_files[0].name.endswith(f"_{file_name}")
    assert stored_files[0].read_bytes() == b"content"


def test_console_chat_stream_emits_keepalive_and_disables_proxy_buffering(
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    workspace = SimpleNamespace(
        channel_manager=_FakeChannelManager(),
        chat_manager=_FakeChatManager(),
        task_tracker=_FakeTaskTracker(),
    )

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )
    monkeypatch.setattr(
        console_router,
        "_CONSOLE_SSE_HEARTBEAT_SECONDS",
        0.01,
        raising=False,
    )

    client = TestClient(app)
    payload = {
        "input": [
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        ],
        "session_id": "session-1",
        "user_id": "user-1",
        "channel": "console",
    }

    with client.stream(
        "POST",
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json=payload,
    ) as response:
        assert response.status_code == 200
        assert response.headers["x-accel-buffering"] == "no"

        lines = response.iter_lines()
        first_line = next(lines)
        if first_line == ": keep-alive":
            assert next(lines) == ""
        else:
            assert first_line == 'data: {"done": true}'
            return

        for line in lines:
            if not line or line == ": keep-alive":
                continue
            assert line == 'data: {"done": true}'
            break
        else:
            raise AssertionError(
                "expected streamed data event after keepalive",
            )


def test_console_chat_copies_b3_trace_id_to_native_meta(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    class _CapturingTaskTracker:
        def __init__(self) -> None:
            self.payload = None

        async def attach_or_start(self, _run_key, payload, _stream_fn):
            self.payload = payload
            return object(), True

        async def stream_from_queue(self, _queue, _run_key):
            yield 'data: {"done": true}\n\n'

    tracker = _CapturingTaskTracker()
    workspace = SimpleNamespace(
        channel_manager=_FakeChannelManager(),
        chat_manager=_FakeChatManager(),
        task_tracker=tracker,
    )

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    client = TestClient(app)
    payload = {
        "input": [
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        ],
        "session_id": "session-1",
        "user_id": "user-1",
        "channel": "console",
    }

    with client.stream(
        "POST",
        "/console/chat",
        headers={
            "X-Source-Id": "src-a",
            "X-B3-Traceid": "8267fd70bacf497704fec30eaa353979",
        },
        json=payload,
    ) as response:
        assert response.status_code == 200
        next(response.iter_lines())

    assert tracker.payload is not None
    assert tracker.payload["meta"]["b3_trace_id"] == (
        "8267fd70bacf497704fec30eaa353979"
    )


def test_console_chat_copies_structured_context_references_to_native_meta(
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    class _CapturingTaskTracker:
        def __init__(self) -> None:
            self.payload = None

        async def attach_or_start(self, _run_key, payload, _stream_fn):
            self.payload = payload
            return object(), True

        async def stream_from_queue(self, _queue, _run_key):
            yield 'data: {"done": true}\n\n'

    tracker = _CapturingTaskTracker()
    workspace = SimpleNamespace(
        channel_manager=_FakeChannelManager(),
        chat_manager=_FakeChatManager(),
        task_tracker=tracker,
    )

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )
    client = TestClient(app)
    references = [
        {"type": "skill", "id": "skill:writer", "name": "writer"},
        {
            "type": "workspace_file",
            "id": "workspace_file:media/report.txt",
            "root": "media",
            "relative_path": "report.txt",
        },
    ]

    with client.stream(
        "POST",
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json={
            "input": [
                {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            ],
            "session_id": "session-1",
            "user_id": "user-1",
            "context_references": references,
        },
    ) as response:
        assert response.status_code == 200
        next(response.iter_lines())

    assert tracker.payload is not None
    assert tracker.payload["meta"]["context_references"] == references


def test_generated_files_returns_chat_files_sorted_by_time(
    tmp_path,
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    static_dir = tmp_path / "static"
    media_dir = tmp_path / "media"
    static_dir.mkdir()
    media_dir.mkdir()
    old_file = static_dir / "old.txt"
    new_file = media_dir / "new"
    old_file.write_text("old", encoding="utf-8")
    new_file.write_text("new", encoding="utf-8")
    os.utime(old_file, (100, 100))
    os.utime(new_file, (200, 200))

    workspace = SimpleNamespace(workspace_dir=tmp_path)

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    client = TestClient(app)

    desc_response = client.get("/console/generated-files?sort=desc")
    assert desc_response.status_code == 200
    desc_files = desc_response.json()["files"]
    assert [item["name"] for item in desc_files] == ["new", "old.txt"]
    assert [item["display_name"] for item in desc_files] == [
        "new",
        "old.txt",
    ]
    assert [item["source"] for item in desc_files] == [
        "uploaded",
        "generated",
    ]
    assert desc_files[0]["preview_type"] == "text"

    asc_response = client.get("/console/generated-files?sort=asc")
    assert asc_response.status_code == 200
    assert [item["name"] for item in asc_response.json()["files"]] == [
        "old.txt",
        "new",
    ]

    uploaded_response = client.get(
        "/console/generated-files?source=uploaded",
    )
    assert uploaded_response.status_code == 200
    assert uploaded_response.json()["files"] == [
        {
            **desc_files[0],
            "name": "new",
            "source": "uploaded",
            "preview_type": "text",
        },
    ]


def test_generated_files_returns_empty_when_static_dir_missing(
    tmp_path,
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)
    workspace = SimpleNamespace(workspace_dir=tmp_path)

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    client = TestClient(app)
    response = client.get("/console/generated-files")

    assert response.status_code == 200
    assert response.json() == {"files": []}


def test_generated_files_uses_console_channel_media_dir(
    tmp_path,
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    media_dir = tmp_path / "custom-media"
    media_dir.mkdir()
    uploaded_file = media_dir / "uploaded.txt"
    uploaded_file.write_text("uploaded", encoding="utf-8")

    class _FakeChannelManager:
        async def get_channel(self, _name):
            return SimpleNamespace(media_dir=media_dir)

    workspace = SimpleNamespace(
        workspace_dir=tmp_path,
        channel_manager=_FakeChannelManager(),
    )

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    client = TestClient(app)
    response = client.get("/console/generated-files?source=uploaded")

    assert response.status_code == 200
    files = response.json()["files"]
    assert len(files) == 1
    assert files[0]["name"] == "uploaded.txt"
    assert files[0]["display_name"] == "uploaded.txt"
    assert files[0]["source"] == "uploaded"


def test_generated_files_hides_uploaded_uuid_prefix(
    tmp_path,
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    stored_name = "5b2dc838632e4be48f1fd39a08f50bb6_report.txt"
    uploaded_file = media_dir / stored_name
    uploaded_file.write_text("uploaded", encoding="utf-8")

    workspace = SimpleNamespace(workspace_dir=tmp_path)

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    client = TestClient(app)
    response = client.get("/console/generated-files?source=uploaded")

    assert response.status_code == 200
    files = response.json()["files"]
    assert len(files) == 1
    assert files[0]["name"] == stored_name
    assert files[0]["display_name"] == "report.txt"
    assert files[0]["file_url"].endswith(stored_name)
