# -*- coding: utf-8 -*-
"""Source 输出截断配置接入 Agent 运行时的回归测试。"""

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentscope.agent import ReActAgent

from swe.agents.react_agent import SWEAgent
from swe.app.source_system_config.models import (
    EffectiveSourceSystemConfig,
    SourceSystemConfig,
)
from swe.app.source_system_config.runtime import bind_source_system_config
from swe.config.config import ToolResultCompactConfig
from swe.config.context import (
    get_current_file_read_max_bytes,
    get_current_recent_max_bytes,
    get_current_tool_result_retention_days,
    set_current_file_read_max_bytes,
    set_current_recent_max_bytes,
    set_current_tool_result_retention_days,
)


def _build_effective_config() -> EffectiveSourceSystemConfig:
    """构造携带工具输出配置的 source 运行时配置。"""
    return EffectiveSourceSystemConfig(
        source_id="portal",
        config=SourceSystemConfig.model_validate(
            {
                "tool_result_compact": {
                    "recent_max_bytes": 32000,
                    "retention_days": 8,
                },
                "file_read_truncation": {
                    "enabled": True,
                    "max_bytes": 12000,
                },
            },
        ).merged_with_defaults(),
        raw_config=SourceSystemConfig.model_validate(
            {
                "tool_result_compact": {
                    "recent_max_bytes": 32000,
                    "retention_days": 8,
                },
                "file_read_truncation": {
                    "enabled": True,
                    "max_bytes": 12000,
                },
            },
        ),
        version=1,
    )


@pytest.mark.asyncio
async def test_reply_binds_source_output_truncation_contexts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reply 进入父类前应把 runtime 截断上下文接好。"""
    agent = object.__new__(SWEAgent)
    agent._workspace_dir = Path(".")
    agent._task_tracker = None
    agent._request_context = {}
    agent.command_handler = SimpleNamespace(
        is_command=lambda _query: False,
    )
    agent._instance_pre_reply_hooks = {}
    agent._instance_post_reply_hooks = {}
    SWEAgent._class_pre_reply_hooks = {}
    SWEAgent._class_post_reply_hooks = {}
    agent.max_iters = 1
    agent.memory = SimpleNamespace()
    agent.memory_manager = None
    agent._start_watchdog = lambda: None
    agent._stop_watchdog = lambda: None
    agent.agent_phase = lambda *_args, **_kwargs: nullcontext()
    agent._agent_config = SimpleNamespace(
        running=SimpleNamespace(
            tool_result_compact=ToolResultCompactConfig(
                recent_max_bytes=50000,
            ),
            memory_summary=SimpleNamespace(force_memory_search=False),
        ),
    )

    async def _noop_process(_msg) -> None:
        return None

    async def _fake_parent_reply(self, msg=None, structured_model=None):
        assert self is agent
        assert msg is None
        assert structured_model is None
        assert get_current_recent_max_bytes() == 32000
        assert get_current_file_read_max_bytes() == 12000
        assert get_current_tool_result_retention_days() == 8
        return SimpleNamespace(ok=True)

    monkeypatch.setattr(
        "swe.agents.react_agent.process_file_and_media_blocks_in_message",
        _noop_process,
    )
    monkeypatch.setattr(
        "swe.agents.react_agent.apply_skill_config_env_overrides",
        lambda *_args, **_kwargs: nullcontext(),
    )
    monkeypatch.setattr(ReActAgent, "reply", _fake_parent_reply)

    with bind_source_system_config(_build_effective_config()):
        try:
            result = await SWEAgent.reply(agent, None)
        finally:
            set_current_recent_max_bytes(None)
            set_current_file_read_max_bytes(None)
            set_current_tool_result_retention_days(None)

    assert result.ok is True
