# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agentscope.message import Msg

from swe.app.crons.manager import CronManager
from swe.app.runner.runner import AgentRunner


class _FakeAgent:
    def __init__(self, content: str = "agent reply") -> None:
        self._content = content

    def state_dict(self) -> dict:
        return {
            "memory": {
                "content": [
                    [
                        Msg(
                            name="Friday",
                            role="assistant",
                            content=self._content,
                        ).to_dict(),
                        [],
                    ],
                ],
            },
        }


class _AtomicSessionDouble:
    def __init__(self) -> None:
        self.state: dict = {}
        self._lock = asyncio.Lock()
        self.merge_started = asyncio.Event()
        self.allow_merge_to_continue = asyncio.Event()

    async def get_session_state_dict(
        self,
        session_id: str,
        user_id: str = "",
        allow_not_exist: bool = True,
    ) -> dict:
        del session_id, user_id, allow_not_exist
        snapshot = copy.deepcopy(self.state)
        self.merge_started.set()
        await self.allow_merge_to_continue.wait()
        return snapshot

    async def save_merged_state(
        self,
        session_id: str,
        user_id: str = "",
        state: dict | None = None,
    ) -> None:
        del session_id, user_id
        self.state = copy.deepcopy(state or {})

    async def update_session_state(
        self,
        session_id: str,
        key,
        value,
        user_id: str = "",
        create_if_not_exist: bool = True,
    ) -> None:
        del session_id, user_id, create_if_not_exist
        async with self._lock:
            state = copy.deepcopy(self.state)
            path = key.split(".") if isinstance(key, str) else list(key)
            cur = state
            for part in path[:-1]:
                if part not in cur or not isinstance(cur[part], dict):
                    cur[part] = {}
                cur = cur[part]
            cur[path[-1]] = value
            self.state = state

    async def mutate_session_state(
        self,
        session_id: str,
        mutator,
        user_id: str = "",
        create_if_not_exist: bool = True,
    ) -> dict:
        del session_id, user_id, create_if_not_exist
        async with self._lock:
            self.merge_started.set()
            await self.allow_merge_to_continue.wait()
            working = copy.deepcopy(self.state)
            updated = mutator(working)
            if updated is None:
                updated = working
            self.state = copy.deepcopy(updated)
            return copy.deepcopy(self.state)


def _make_runner(monkeypatch, tmp_path: Path, session) -> AgentRunner:
    runner = AgentRunner(agent_id="test-agent", workspace_dir=tmp_path)
    runner.session = session
    setattr(runner, "_chat_manager", None)
    monkeypatch.setattr(
        "swe.app.runner.runner._build_and_connect_mcp_clients",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "swe.app.runner.runner._cleanup_mcp_clients",
        AsyncMock(),
    )
    return runner


@pytest.mark.asyncio
async def test_regular_session_save_preserves_concurrent_key_update(
    monkeypatch,
    tmp_path: Path,
) -> None:
    session = _AtomicSessionDouble()
    runner = _make_runner(monkeypatch, tmp_path, session)

    save_task = asyncio.create_task(
        runner._save_regular_session_state(
            _FakeAgent(),
            session_id="session-1",
            user_id="user-1",
            hook_overlay=None,
        ),
    )

    await asyncio.wait_for(session.merge_started.wait(), timeout=1)
    update_task = asyncio.create_task(
        session.update_session_state(
            "session-1",
            "task_messages",
            [{"id": "msg-1", "content": "persisted task update"}],
            user_id="user-1",
        ),
    )
    await asyncio.sleep(0)
    session.allow_merge_to_continue.set()

    await asyncio.gather(save_task, update_task)

    assert session.state["agent"]["memory"]["content"]
    assert session.state["task_messages"] == [
        {"id": "msg-1", "content": "persisted task update"},
    ]


@pytest.mark.asyncio
async def test_cron_text_append_preserves_concurrent_agent_update(
    monkeypatch,
    tmp_path: Path,
) -> None:
    session = _AtomicSessionDouble()
    runner = _make_runner(monkeypatch, tmp_path, session)
    manager = CronManager(
        repo=object(),
        runner=runner,
        channel_manager=object(),
    )

    append_task = asyncio.create_task(
        manager._append_text_task_message(
            "session-1",
            "user-1",
            "cron preview",
        ),
    )

    await asyncio.wait_for(session.merge_started.wait(), timeout=1)
    update_task = asyncio.create_task(
        session.update_session_state(
            "session-1",
            "agent",
            _FakeAgent("concurrent agent state").state_dict(),
            user_id="user-1",
        ),
    )
    await asyncio.sleep(0)
    session.allow_merge_to_continue.set()

    await asyncio.gather(append_task, update_task)

    assert session.state["agent"]["memory"]["content"]
    assert session.state["task_messages"][0]["content"][0]["text"] == (
        "cron preview"
    )
