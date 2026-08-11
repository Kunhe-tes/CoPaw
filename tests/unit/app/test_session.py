# -*- coding: utf-8 -*-
"""会话状态加载的兼容性测试。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from reme.memory.file_based.reme_in_memory_memory import ReMeInMemoryMemory

from swe.agents.hook_runtime.messages import (
    build_hook_additional_context_msg,
)
from swe.app.runner.session import SafeJSONSession


@pytest.mark.asyncio
async def test_load_session_state_migrates_hook_developer_role_to_system(
    tmp_path,
) -> None:
    """旧 developer hook 上下文加载后应单向迁移为 system。"""
    session = SafeJSONSession(save_dir=str(tmp_path))
    memory = ReMeInMemoryMemory(token_counter=MagicMock())
    session_path = session._get_save_path("session-1", "user-1")

    with open(session_path, "w", encoding="utf-8") as file:
        json.dump(
            {
                "memory": {
                    "content": [
                        [
                            {
                                "id": "msg-1",
                                "name": "system",
                                "role": "developer",
                                "content": (
                                    "[Hook additional context]\n"
                                    "remember for next turn"
                                ),
                                "metadata": {},
                            },
                            [],
                        ],
                    ],
                },
            },
            file,
            ensure_ascii=False,
        )

    await session.load_session_state(
        session_id="session-1",
        user_id="user-1",
        memory=memory,
    )

    assert len(memory.content) == 1
    assert memory.content[0][0].role == "system"
    assert "remember for next turn" in memory.content[0][0].content
