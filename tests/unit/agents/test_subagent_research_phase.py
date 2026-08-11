# -*- coding: utf-8 -*-
"""Tests for the explicit SubAgent research ReAct phase."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agentscope.message import Msg

from swe.agents.react_agent import SWEAgent
from swe.config.config import ToolResultCompactConfig


class _Memory:
    def __init__(self) -> None:
        self.messages: list[Msg] = []

    async def add(self, message) -> None:
        if message is not None:
            self.messages.append(message)

    async def get_memory(self) -> list[Msg]:
        return list(self.messages)


def _agent(*, max_iters: int, replies: list[Msg]) -> SWEAgent:
    """Build a minimal SWEAgent shell around the phase controller."""
    agent = object.__new__(SWEAgent)
    agent.memory = _Memory()
    agent.max_iters = max_iters
    agent.parallel_tool_calls = False
    agent._workspace_dir = None
    agent._task_tracker = None
    agent._request_context = {}
    agent._agent_config = SimpleNamespace(
        running=SimpleNamespace(
            tool_result_compact=ToolResultCompactConfig(),
        ),
    )
    agent._reply_task = None
    agent._required_structured_model = object()
    agent.finish_function_name = "generate_response"
    agent.toolkit = SimpleNamespace(remove_tool_function=lambda _name: None)
    agent._retrieve_from_long_term_memory = AsyncMock()
    agent._retrieve_from_knowledge = AsyncMock()
    agent._compress_memory_if_needed = AsyncMock()
    agent._reasoning = AsyncMock(side_effect=replies)
    agent._acting = AsyncMock()
    agent._summarizing = AsyncMock()
    agent._start_watchdog = lambda: None
    agent._stop_watchdog = lambda: None
    agent.agent_phase = lambda *_args, **_kwargs: nullcontext()
    return agent


@pytest.mark.asyncio
async def test_research_phase_runs_tools_then_finishes_on_plain_reply(
    monkeypatch,
) -> None:
    from swe.agents import react_agent as react_agent_module

    monkeypatch.setattr(
        react_agent_module,
        "process_file_and_media_blocks_in_message",
        AsyncMock(),
    )
    tool_reply = Msg(
        "Friday",
        [
            {
                "type": "tool_use",
                "id": "tool-1",
                "name": "read_file",
                "input": {"path": "README.md"},
            },
        ],
        "assistant",
    )
    final_reply = Msg("Friday", "research synthesis", "assistant")
    agent = _agent(max_iters=2, replies=[tool_reply, final_reply])

    result = await agent.run_research_phase(
        Msg("user", "research this", "user"),
    )

    assert result.status == "completed"
    assert result.reply == final_reply
    assert result.turns_used == 2
    agent._acting.assert_awaited_once()
    assert agent._reasoning.await_args_list[0].args == ()
    assert agent._reasoning.await_args_list[1].args == ()
    assert agent._reasoning.await_args_list[0].kwargs == {}
    assert agent._reasoning.await_args_list[1].kwargs == {}
    agent._summarizing.assert_not_called()


@pytest.mark.asyncio
async def test_research_phase_reports_turn_limit_without_summarizing(
    monkeypatch,
) -> None:
    from swe.agents import react_agent as react_agent_module

    monkeypatch.setattr(
        react_agent_module,
        "process_file_and_media_blocks_in_message",
        AsyncMock(),
    )
    tool_reply = Msg(
        "Friday",
        [
            {
                "type": "tool_use",
                "id": "tool-1",
                "name": "read_file",
                "input": {"path": "README.md"},
            },
        ],
        "assistant",
    )
    agent = _agent(max_iters=1, replies=[tool_reply])

    result = await agent.run_research_phase(
        Msg("user", "research this", "user"),
    )

    assert result.status == "turn_limit_reached"
    assert result.reply == tool_reply
    assert result.turns_used == 1
    agent._acting.assert_awaited_once()
    agent._summarizing.assert_not_called()
