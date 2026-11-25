# -*- coding: utf-8 -*-
"""媒体回退重试应复用同一步的观测 step 索引。"""

from __future__ import annotations

from contextlib import nullcontext
import inspect

import pytest
from agentscope.message import Msg

from swe.agents.react_agent import SWEAgent

# 跳过 AgentScope 钩子包装，直接驱动被包装的原始方法。
_REASONING = inspect.unwrap(SWEAgent._reasoning)


def _configure_agent(agent: SWEAgent, *, step_index: int, runner) -> None:
    """桩掉媒体回退路径依赖，只保留 step 索引行为。"""
    agent._observability_step_index = step_index
    agent.agent_phase = lambda *_args, **_kwargs: nullcontext()
    agent._proactive_strip_media_blocks = lambda: 0
    agent._strip_media_blocks_from_memory = lambda: 1
    agent._is_bad_request_or_media_error = lambda _exc: True
    agent._run_reasoning_with_internal_context = runner


@pytest.mark.asyncio
async def test_media_fallback_retry_reuses_step_index(monkeypatch):
    """被动回退重试不应额外消耗一个 step。"""
    monkeypatch.setattr(
        "swe.agents.react_agent.get_active_model_supports_multimodal",
        lambda: False,
    )
    agent = object.__new__(SWEAgent)
    entries: list[int] = []

    async def runner(tool_choice=None):
        # 记录进入 ToolGuardMixin 前的索引，并模拟其自增行为。
        entries.append(agent._observability_step_index)
        agent._observability_step_index = (
            agent._observability_step_index or 0
        ) + 1
        if len(entries) == 1:
            raise RuntimeError("400 unsupported image")
        return Msg("Friday", "ok", "assistant")

    _configure_agent(agent, step_index=5, runner=runner)

    result = await _REASONING(agent, tool_choice="auto")

    assert result.get_text_content() == "ok"
    # 第一次调用内部把 5 自增到 6；回退重试前必须恢复为 5。
    assert entries == [5, 5]
    # 两次调用最终只推进一次 step，而不是消耗两个 step。
    assert agent._observability_step_index == 6


@pytest.mark.asyncio
async def test_success_path_keeps_incremented_step_index(monkeypatch):
    """正常成功路径不恢复索引，保持 ToolGuardMixin 的自增结果。"""
    monkeypatch.setattr(
        "swe.agents.react_agent.get_active_model_supports_multimodal",
        lambda: False,
    )
    agent = object.__new__(SWEAgent)
    entries: list[int] = []

    async def runner(tool_choice=None):
        entries.append(agent._observability_step_index)
        agent._observability_step_index = (
            agent._observability_step_index or 0
        ) + 1
        return Msg("Friday", "ok", "assistant")

    _configure_agent(agent, step_index=5, runner=runner)

    result = await _REASONING(agent, tool_choice="auto")

    assert result.get_text_content() == "ok"
    assert entries == [5]
    assert agent._observability_step_index == 6
