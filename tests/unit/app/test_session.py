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
async def test_load_session_state_accepts_hook_developer_role(
    tmp_path,
) -> None:
    """带 developer role 的 hook 上下文应能从会话文件恢复。"""
    session = SafeJSONSession(save_dir=str(tmp_path))
    memory = ReMeInMemoryMemory(token_counter=MagicMock())
    msg = build_hook_additional_context_msg(
        "[Hook additional context]\nremember for next turn",
    )
    session_path = session._get_save_path("session-1", "user-1")

    with open(session_path, "w", encoding="utf-8") as file:
        json.dump(
            {
                "memory": {
                    "content": [
                        [
                            msg.to_dict(),
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
    assert memory.content[0][0].role == "developer"
    assert "remember for next turn" in memory.content[0][0].content
