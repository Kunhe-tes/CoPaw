# -*- coding: utf-8 -*-
"""History totals use the authenticated scope and span summary pages."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from swe.app.runner.api import get_chat_manager, get_workspace, router
from swe.app.runner.manager import ChatManager
from swe.app.runner.models import ChatSpec, ChatsFile
from swe.app.runner.repo.json_repo import JsonChatRepository


@pytest.mark.asyncio
async def test_history_total_counts_only_matching_non_task_chats(tmp_path):
    repo = JsonChatRepository(tmp_path / "chats.json")
    await repo.save(
        ChatsFile(
            chats=[
                ChatSpec(session_id="session", user_id="alice"),
                ChatSpec(session_id="session", user_id="alice"),
                ChatSpec(
                    session_id="session",
                    user_id="alice",
                    meta={"session_kind": "task"},
                ),
                ChatSpec(session_id="session", user_id="bob"),
            ],
        ),
    )
    manager = ChatManager(repo=repo)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_chat_manager] = lambda: manager
    workspace = SimpleNamespace()
    app.dependency_overrides[get_workspace] = lambda: workspace

    @app.middleware("http")
    async def set_identity(request, call_next):
        request.state.user_id = "alice"
        return await call_next(request)

    with TestClient(app) as client:
        params = {"page_size": 1, "include_history_total": True}
        first = client.get("/chats/-/summaries", params=params)
        assert first.status_code == 200
        assert first.json()["history_total"] == 2
        cursor = first.json()["next_cursor"]
        assert cursor

        second = client.get(
            "/chats/-/summaries",
            params={**params, "cursor": cursor},
        )
        assert second.status_code == 200
        assert second.json()["history_total"] == 2

        empty = client.get(
            "/chats/-/summaries",
            params={**params, "session_id": "missing"},
        )
        assert empty.status_code == 200
        assert empty.json()["history_total"] == 0
