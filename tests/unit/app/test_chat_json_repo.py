# -*- coding: utf-8 -*-
"""Tests for JSON chat repository runtime-state worker boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swe.app.runner.models import ChatSpec, ChatsFile
from swe.app.runner.repo.json_repo import JsonChatRepository


@pytest.mark.asyncio
async def test_chat_repo_load_uses_runtime_state_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "chats.json"
    path.write_text(
        json.dumps(
            ChatsFile(
                version=1,
                chats=[
                    ChatSpec(session_id="s1", user_id="u1", channel="console"),
                ],
            ).model_dump(mode="json"),
        ),
        encoding="utf-8",
    )
    calls: list[str] = []

    async def fake_worker(func, /, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "swe.app.runner.repo.json_repo.run_runtime_state_work",
        fake_worker,
    )

    repo = JsonChatRepository(path)
    loaded = await repo.load()

    assert [chat.session_id for chat in loaded.chats] == ["s1"]
    assert calls == ["_load_sync"]


@pytest.mark.asyncio
async def test_chat_repo_save_uses_runtime_state_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "chats.json"
    calls: list[str] = []

    async def fake_worker(func, /, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "swe.app.runner.repo.json_repo.run_runtime_state_work",
        fake_worker,
    )

    repo = JsonChatRepository(path)
    await repo.save(
        ChatsFile(
            version=1,
            chats=[ChatSpec(session_id="s1", user_id="u1", channel="console")],
        ),
    )

    assert calls == ["_save_sync"]
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["chats"][0]["session_id"] == "s1"


@pytest.mark.asyncio
async def test_chat_repo_get_chat_reuses_valid_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = JsonChatRepository(tmp_path / "chats.json")
    chat = ChatSpec(session_id="s1", user_id="u1", channel="console")
    await repo.save(ChatsFile(version=1, chats=[chat]))

    async def fail_worker(func, /, *args, **kwargs):
        if func.__name__ == "_load_sync":
            raise AssertionError("snapshot should avoid full reload")
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "swe.app.runner.repo.json_repo.run_runtime_state_work",
        fail_worker,
    )

    loaded = await repo.get_chat(chat.id)

    assert loaded is not None
    assert loaded.session_id == "s1"
