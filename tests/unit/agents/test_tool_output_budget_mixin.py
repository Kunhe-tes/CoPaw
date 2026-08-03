# -*- coding: utf-8 -*-
"""Regression coverage for bounded AgentScope tool-result messages."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

from swe.agents.tool_output_budget_mixin import ToolOutputBudgetMixin
from swe.app.source_system_config.models import (
    EffectiveSourceSystemConfig,
    SourceSystemConfig,
)
from swe.app.source_system_config.runtime import bind_source_system_config
from swe.config.config import ToolResultCompactConfig


class _Memory:
    def __init__(self) -> None:
        self.messages = []

    async def add(self, msg) -> None:
        self.messages.append(msg)


class _Toolkit:
    def __init__(self, chunks: list[ToolResponse]) -> None:
        self._chunks = chunks

    async def call_tool_function(self, _tool_call):
        async def _stream():
            for chunk in self._chunks:
                yield chunk

        return _stream()


class _AgentScopeLikeAgent(ToolOutputBudgetMixin):
    """Minimal AgentScope boundary with a real toolkit response stream."""

    def __init__(
        self,
        *,
        config: ToolResultCompactConfig,
        workspace_dir: Path | None,
        chunks: list[ToolResponse],
    ) -> None:
        self._agent_config = SimpleNamespace(
            running=SimpleNamespace(tool_result_compact=config),
        )
        self._workspace_dir = workspace_dir
        self.toolkit = _Toolkit(chunks)
        self.memory = _Memory()
        self.printed = []
        self.finish_function_name = "finish"

    async def print(self, msg, is_last) -> None:
        self.printed.append((msg, is_last))


def _chunk(
    text: str,
    *,
    metadata: dict | None = None,
    is_interrupted: bool = False,
) -> ToolResponse:
    return ToolResponse(
        content=[TextBlock(type="text", text=text)],
        metadata=metadata,
        is_interrupted=is_interrupted,
    )


def _source_config(raw_config: dict) -> EffectiveSourceSystemConfig:
    source_config = SourceSystemConfig.model_validate(raw_config)
    return EffectiveSourceSystemConfig(
        source_id="portal",
        config=source_config.merged_with_defaults(),
        raw_config=source_config,
        version=1,
    )


@pytest.mark.asyncio
async def test_compacts_source_resolved_tool_result_before_print_and_memory(
    tmp_path: Path,
) -> None:
    agent = _AgentScopeLikeAgent(
        config=ToolResultCompactConfig(
            enabled=True,
            old_max_bytes=128,
            recent_max_bytes=1024,
            recent_n=1,
            retention_days=1,
        ),
        workspace_dir=tmp_path,
        chunks=[_chunk("x" * 4096)],
    )

    with bind_source_system_config(
        _source_config({"tool_result_compact": {"recent_max_bytes": 1000}}),
    ):
        result = await agent._acting(
            {"id": "tool-1", "name": "read_file", "input": {}},
        )

    assert result is None
    printed, is_last = agent.printed[0]
    stored = agent.memory.messages[0]
    assert is_last is True
    assert printed is stored
    output = stored.content[0]["output"][0]["text"]
    assert len(output.encode("utf-8")) <= 1000
    assert "<<<TRUNCATED>>>" in output
    artifacts = list((tmp_path / "tool_result").glob("*.txt"))
    assert len(artifacts) == 1
    assert artifacts[0].read_text(encoding="utf-8") == "x" * 4096


@pytest.mark.asyncio
async def test_compacts_with_fallback_workspace_when_workspace_is_none(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "swe.agents.tool_output_budget_mixin.WORKING_DIR",
        tmp_path,
    )
    agent = _AgentScopeLikeAgent(
        config=ToolResultCompactConfig(
            enabled=True,
            old_max_bytes=128,
            recent_max_bytes=1000,
            recent_n=1,
            retention_days=1,
        ),
        workspace_dir=None,
        chunks=[_chunk("x" * 4096)],
    )

    await agent._acting(
        {"id": "tool-1", "name": "read_file", "input": {}},
    )

    output = agent.memory.messages[0].content[0]["output"][0]["text"]
    assert len(output.encode("utf-8")) <= 1000
    assert "<<<TRUNCATED>>>" in output
    artifacts = list((tmp_path / "tool_result").glob("*.txt"))
    assert len(artifacts) == 1
    assert artifacts[0].read_text(encoding="utf-8") == "x" * 4096


@pytest.mark.asyncio
async def test_disabled_source_configuration_leaves_tool_output_unchanged(
    tmp_path: Path,
) -> None:
    original = "x" * 4096
    agent = _AgentScopeLikeAgent(
        config=ToolResultCompactConfig(
            enabled=True,
            old_max_bytes=1000,
            recent_max_bytes=1000,
            recent_n=1,
            retention_days=1,
        ),
        workspace_dir=tmp_path,
        chunks=[_chunk(original)],
    )

    with bind_source_system_config(
        _source_config({"tool_result_compact": {"enabled": False}}),
    ):
        await agent._acting(
            {"id": "tool-1", "name": "read_file", "input": {}},
        )

    stored = agent.memory.messages[0]
    assert agent.printed[0][0] is stored
    assert stored.content[0]["output"][0]["text"] == original
    assert not (tmp_path / "tool_result").exists()


@pytest.mark.asyncio
async def test_finish_returns_structured_output_after_printing_and_storing(
    tmp_path: Path,
) -> None:
    structured_output = {"answer": "done"}
    agent = _AgentScopeLikeAgent(
        config=ToolResultCompactConfig(enabled=False),
        workspace_dir=tmp_path,
        chunks=[
            _chunk(
                "finished",
                metadata={
                    "success": True,
                    "structured_output": structured_output,
                },
            ),
        ],
    )

    result = await agent._acting(
        {"id": "tool-1", "name": "finish", "input": {}},
    )

    assert result == structured_output
    assert len(agent.printed) == len(agent.memory.messages) == 1
    assert agent.printed[0][0] is agent.memory.messages[0]


@pytest.mark.asyncio
async def test_interrupted_chunk_is_printed_and_stored_before_cancellation(
    tmp_path: Path,
) -> None:
    agent = _AgentScopeLikeAgent(
        config=ToolResultCompactConfig(enabled=False),
        workspace_dir=tmp_path,
        chunks=[_chunk("interrupted", is_interrupted=True)],
    )

    with pytest.raises(asyncio.CancelledError):
        await agent._acting(
            {"id": "tool-1", "name": "read_file", "input": {}},
        )

    assert len(agent.printed) == len(agent.memory.messages) == 1
    assert agent.printed[0][0] is agent.memory.messages[0]
