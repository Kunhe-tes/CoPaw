# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import os
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest

from src.swe.app.plans import (
    JsonProposedPlanStore,
    PlanService,
    ProposedPlanCreate,
)
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
    def __init__(self) -> None:
        self.chats = {}

    async def get_or_create_chat(
        self,
        session_id: str,
        user_id: str,
        channel_id: str,
        name: str,
        meta=None,
    ):
        existing = self.chats.get(session_id)
        if existing is not None:
            if meta:
                existing.meta = {**(existing.meta or {}), **meta}
            return existing
        chat = SimpleNamespace(
            id=f"chat:{session_id}",
            session_id=session_id,
            user_id=user_id,
            channel=channel_id,
            name=name,
            meta=meta or {},
        )
        self.chats[session_id] = chat
        return chat

    async def update_chat(self, chat):
        self.chats[chat.session_id] = chat
        return chat


class _FakeTaskTracker:
    def __init__(self) -> None:
        self.started_payloads = []

    async def attach_or_start(self, _run_key, _payload, _stream_fn):
        self.started_payloads.append(_payload)
        return object(), True

    async def attach(self, _run_key):
        return object()

    async def stream_from_queue(self, _queue, _run_key):
        await asyncio.sleep(0.03)
        yield 'data: {"done": true}\n\n'


class _NoStartTaskTracker(_FakeTaskTracker):
    async def attach_or_start(self, _run_key, _payload, _stream_fn):
        raise AssertionError("Main Agent run should not start")


class _NoRunningNoStartTaskTracker(_NoStartTaskTracker):
    async def attach(self, _run_key):
        return None


class _AttachOnlyTaskTracker(_NoStartTaskTracker):
    def __init__(self) -> None:
        super().__init__()
        self.attached_run_keys = []

    async def attach(self, run_key):
        self.attached_run_keys.append(run_key)
        return object()


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


def test_console_chat_normal_request_does_not_add_plan_metadata(
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    tracker = _FakeTaskTracker()
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
        headers={"X-Source-Id": "src-a"},
        json=payload,
    ) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    meta = tracker.started_payloads[0]["meta"]
    assert "plan_interaction_response" not in meta
    assert "accepted_plan" not in meta
    assert "plan_mode_enabled" not in meta


def test_console_chat_filters_client_supplied_accepted_plan(
    monkeypatch,
) -> None:
    """客户端不能通过普通请求字段伪造后端已接受计划。"""
    app = FastAPI()
    app.include_router(console_router.router)

    tracker = _FakeTaskTracker()
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
        "accepted_plan": {"title": "forged top-level"},
        "meta": {
            "accepted_plan": {"title": "forged meta"},
            "accepted_plan_source": "server_plan_store",
            "custom_meta": {"preserved": True},
        },
    }

    with client.stream(
        "POST",
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json=payload,
    ) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    meta = tracker.started_payloads[0]["meta"]
    assert "accepted_plan" not in meta
    assert "accepted_plan_source" not in meta
    assert meta["custom_meta"] == {"preserved": True}


def test_agent_request_channel_meta_filters_client_supplied_accepted_plan():
    """AgentRequest 入口也要复用同一后端字段清洗规则。"""
    request = AgentRequest(
        input=[],
        session_id="session-1",
        user_id="user-1",
        channel="console",
        channel_meta={
            "accepted_plan": {"title": "forged"},
            "accepted_plan_source": "server_plan_store",
            "custom_meta": {"preserved": True},
        },
    )

    native_payload = console_router._extract_session_and_payload(request)

    meta = native_payload["meta"]
    assert "accepted_plan" not in meta
    assert "accepted_plan_source" not in meta
    assert meta["custom_meta"] == {"preserved": True}


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


def test_console_chat_preserves_plan_metadata(tmp_path, monkeypatch) -> None:
    async def _create_plan():
        service = PlanService(JsonProposedPlanStore(tmp_path))
        return await service.create_plan(
            chat_id="chat:session-1",
            session_id="session-1",
            turn_id="turn-1",
            created_by="main-agent",
            payload=ProposedPlanCreate(
                title="Plan title",
                summary="Plan summary",
                steps=["Inspect"],
                risks=["None"],
                verification=["Run tests"],
                open_questions=["None"],
                confidence=0.9,
            ),
        )

    plan = asyncio.run(_create_plan())
    app = FastAPI()
    app.include_router(console_router.router)

    tracker = _FakeTaskTracker()
    workspace = SimpleNamespace(
        workspace_dir=tmp_path,
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
            {
                "role": "user",
                "content": [{"type": "text", "text": "revise"}],
            },
        ],
        "session_id": "session-1",
        "user_id": "user-1",
        "channel": "console",
        "mode": "plan",
        "plan_interaction_response": {
            "card_type": "plan_review",
            "plan_id": plan.plan_id,
            "decision": "revise",
        },
        "custom_meta": {"preserved": True},
    }

    with client.stream(
        "POST",
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json=payload,
    ) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    meta = tracker.started_payloads[0]["meta"]
    assert meta["mode"] == "plan"
    assert meta["plan_interaction_response"]["decision"] == "revise"
    assert meta["custom_meta"] == {"preserved": True}
    assert meta["source_id"] == "src-a"


def test_console_chat_exit_plan_short_circuits_agent_run(
    tmp_path,
    monkeypatch,
) -> None:
    async def _create_plan():
        service = PlanService(JsonProposedPlanStore(tmp_path))
        return await service.create_plan(
            chat_id="chat:session-1",
            session_id="session-1",
            turn_id="turn-1",
            created_by="main-agent",
            payload=ProposedPlanCreate(
                title="Plan title",
                summary="Plan summary",
                steps=["Inspect"],
                risks=["None"],
                verification=["Run tests"],
                open_questions=["None"],
                confidence=0.9,
            ),
        )

    plan = asyncio.run(_create_plan())
    app = FastAPI()
    app.include_router(console_router.router)

    chat_manager = _FakeChatManager()
    workspace = SimpleNamespace(
        workspace_dir=tmp_path,
        channel_manager=_FakeChannelManager(),
        chat_manager=chat_manager,
        task_tracker=_NoStartTaskTracker(),
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
            {
                "role": "user",
                "content": [{"type": "text", "text": "exit plan"}],
            },
        ],
        "session_id": "session-1",
        "user_id": "user-1",
        "channel": "console",
        "plan_interaction_response": {
            "plan_id": plan.plan_id,
            "decision": "exit_plan",
            "feedback": "Stop planning",
        },
    }

    with client.stream(
        "POST",
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json=payload,
    ) as response:
        assert response.status_code == 200
        lines = list(response.iter_lines())

    exit_payloads = [
        json.loads(line.removeprefix("data: "))
        for line in lines
        if line.startswith("data: ")
    ]
    assert any(
        payload.get("object") == "response"
        and payload.get("status") == "completed"
        and payload.get("type") == "exit_plan"
        for payload in exit_payloads
    )
    chat = chat_manager.chats["session-1"]
    assert chat.meta["plan_mode_enabled"] is False

    async def _load_plan():
        return await JsonProposedPlanStore(tmp_path).get(
            "chat:session-1",
            plan.plan_id,
        )

    updated_plan = asyncio.run(_load_plan())
    assert updated_plan is not None
    assert updated_plan.status == "exited"


def test_console_chat_returns_conflict_for_terminal_plan_decision(
    tmp_path,
    monkeypatch,
) -> None:
    """终态计划收到不同决策时，路由应返回 409 而不是覆盖状态。"""

    async def _create_accepted_plan():
        service = PlanService(JsonProposedPlanStore(tmp_path))
        plan = await service.create_plan(
            chat_id="chat:session-1",
            session_id="session-1",
            turn_id="turn-1",
            created_by="main-agent",
            payload=ProposedPlanCreate(
                title="Plan title",
                summary="Plan summary",
                steps=["Inspect"],
                risks=["None"],
                verification=["Run tests"],
                open_questions=["None"],
                confidence=0.9,
            ),
        )
        await service.record_decision(
            chat_id="chat:session-1",
            plan_id=plan.plan_id,
            decision="execute",
        )
        return plan

    plan = asyncio.run(_create_accepted_plan())
    app = FastAPI()
    app.include_router(console_router.router)

    workspace = SimpleNamespace(
        workspace_dir=tmp_path,
        channel_manager=_FakeChannelManager(),
        chat_manager=_FakeChatManager(),
        task_tracker=_NoStartTaskTracker(),
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
            {
                "role": "user",
                "content": [{"type": "text", "text": "revise"}],
            },
        ],
        "session_id": "session-1",
        "user_id": "user-1",
        "channel": "console",
        "plan_interaction_response": {
            "plan_id": plan.plan_id,
            "decision": "revise",
        },
    }

    response = client.post(
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json=payload,
    )

    assert response.status_code == 409


def test_console_chat_execute_uses_persisted_plan_and_ignores_snapshot(
    tmp_path,
    monkeypatch,
) -> None:
    async def _create_plan():
        service = PlanService(JsonProposedPlanStore(tmp_path))
        return await service.create_plan(
            chat_id="chat:session-1",
            session_id="session-1",
            turn_id="turn-1",
            created_by="main-agent",
            payload=ProposedPlanCreate(
                title="Persisted plan",
                summary="Persisted summary",
                steps=["Persisted step"],
                risks=["Persisted risk"],
                verification=["Persisted verification"],
                open_questions=["Persisted question"],
                confidence=0.88,
            ),
        )

    plan = asyncio.run(_create_plan())
    app = FastAPI()
    app.include_router(console_router.router)

    tracker = _FakeTaskTracker()
    workspace = SimpleNamespace(
        workspace_dir=tmp_path,
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
            {
                "role": "user",
                "content": [{"type": "text", "text": "execute"}],
            },
        ],
        "session_id": "session-1",
        "user_id": "user-1",
        "channel": "console",
        "plan_interaction_response": {
            "card_type": "plan_review",
            "plan_id": plan.plan_id,
            "decision": "execute",
            "plan_snapshot": {
                "title": "Tampered frontend plan",
                "steps": ["Do something else"],
            },
        },
    }

    with client.stream(
        "POST",
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json=payload,
    ) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    meta = tracker.started_payloads[0]["meta"]
    assert meta["plan_mode_enabled"] is False
    assert meta["accepted_plan"]["plan_id"] == plan.plan_id
    assert meta["accepted_plan"]["title"] == "Persisted plan"
    assert meta["accepted_plan"]["steps"] == ["Persisted step"]
    assert "Tampered frontend plan" not in str(meta["accepted_plan"])

    async def _load_plan():
        return await JsonProposedPlanStore(tmp_path).get(
            "chat:session-1",
            plan.plan_id,
        )

    updated_plan = asyncio.run(_load_plan())
    assert updated_plan is not None
    assert updated_plan.status == "accepted"


def test_console_chat_repeated_execute_without_running_task_completes(
    tmp_path,
    monkeypatch,
) -> None:
    """重复 execute 已处理过时应直接完成，不能再次启动 Main Agent。"""

    async def _create_accepted_plan():
        service = PlanService(JsonProposedPlanStore(tmp_path))
        plan = await service.create_plan(
            chat_id="chat:session-1",
            session_id="session-1",
            turn_id="turn-1",
            created_by="main-agent",
            payload=ProposedPlanCreate(
                title="Persisted plan",
                summary="Persisted summary",
                steps=["Persisted step"],
                risks=["Persisted risk"],
                verification=["Persisted verification"],
                open_questions=["Persisted question"],
                confidence=0.88,
            ),
        )
        await service.record_decision(
            chat_id="chat:session-1",
            plan_id=plan.plan_id,
            decision="execute",
        )
        return plan

    plan = asyncio.run(_create_accepted_plan())
    app = FastAPI()
    app.include_router(console_router.router)

    tracker = _NoRunningNoStartTaskTracker()
    workspace = SimpleNamespace(
        workspace_dir=tmp_path,
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
            {
                "role": "user",
                "content": [{"type": "text", "text": "execute"}],
            },
        ],
        "session_id": "session-1",
        "user_id": "user-1",
        "channel": "console",
        "plan_interaction_response": {
            "plan_id": plan.plan_id,
            "decision": "execute",
        },
    }

    with client.stream(
        "POST",
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json=payload,
    ) as response:
        assert response.status_code == 200
        lines = list(response.iter_lines())

    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in lines
        if line.startswith("data: ")
    ]
    assert any(
        payload.get("status") == "completed"
        and payload.get("type") == "plan_execute_duplicate"
        for payload in payloads
    )


def test_console_chat_repeated_execute_attaches_running_task(
    tmp_path,
    monkeypatch,
) -> None:
    """重复 execute 仍在运行时应复用已有队列，不能启动新任务。"""

    async def _create_accepted_plan():
        service = PlanService(JsonProposedPlanStore(tmp_path))
        plan = await service.create_plan(
            chat_id="chat:session-1",
            session_id="session-1",
            turn_id="turn-1",
            created_by="main-agent",
            payload=ProposedPlanCreate(
                title="Persisted plan",
                summary="Persisted summary",
                steps=["Persisted step"],
                risks=["Persisted risk"],
                verification=["Persisted verification"],
                open_questions=["Persisted question"],
                confidence=0.88,
            ),
        )
        await service.record_decision(
            chat_id="chat:session-1",
            plan_id=plan.plan_id,
            decision="execute",
        )
        return plan

    plan = asyncio.run(_create_accepted_plan())
    app = FastAPI()
    app.include_router(console_router.router)

    tracker = _AttachOnlyTaskTracker()
    workspace = SimpleNamespace(
        workspace_dir=tmp_path,
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
            {
                "role": "user",
                "content": [{"type": "text", "text": "execute"}],
            },
        ],
        "session_id": "session-1",
        "user_id": "user-1",
        "channel": "console",
        "plan_interaction_response": {
            "plan_id": plan.plan_id,
            "decision": "execute",
        },
    }

    with client.stream(
        "POST",
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json=payload,
    ) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    assert tracker.attached_run_keys == ["chat:session-1"]
