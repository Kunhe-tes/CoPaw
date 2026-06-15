# -*- coding: utf-8 -*-
"""End-to-end critical path: scheduled agent run through MCP tool use."""

from __future__ import annotations

import pytest
from agentscope.model._model_response import ChatResponse
from agentscope.model._model_usage import ChatUsage

from swe.agents import model_factory
from swe.app.crons import executor as executor_module
from swe.app.crons.executor import CronExecutor
from swe.app.runner.runner import AgentRunner
from swe.providers.rate_limiter import reset_rate_limiter

from tests.integrated.critical_paths.conftest import (
    FakeProvider,
    FakeProviderManager,
    build_agent_job,
    mcp_config_for,
)


class RoutedReActModel(model_factory.ChatModelBase):
    def __init__(self) -> None:
        super().__init__(model_name="critical-routed-model", stream=False)
        self.calls: list[dict] = []
        self.reacted_with_tool = False
        self.reacted_with_final = False

    async def __call__(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        text = str(kwargs.get("messages") or args)
        usage = ChatUsage(input_tokens=1, output_tokens=1, time=0.0)
        if "请用一句自然中文描述" in text:
            return ChatResponse(
                content=[{"type": "text", "text": "工具摘要"}],
                usage=usage,
            )
        if "tool_result" in text or "echo:from scheduled agent" in text:
            self.reacted_with_final = True
            return ChatResponse(
                content=[
                    {
                        "type": "text",
                        "text": "final reply after echo:from scheduled agent",
                    },
                ],
                usage=usage,
            )

        self.reacted_with_tool = True
        return ChatResponse(
            content=[
                {
                    "type": "tool_use",
                    "id": "tool-call-1",
                    "name": "echo",
                    "input": {"text": "from scheduled agent"},
                },
            ],
            usage=usage,
        )


@pytest.fixture(autouse=True)
def _reset_rate_limiter_registry():
    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.mark.asyncio
async def test_scheduled_agent_runs_react_mcp_tool_and_delivers_final_message(
    monkeypatch,
    isolated_agent_config,
    loopback_mcp_server,
    recording_channel_manager,
) -> None:
    workspace_dir, write_agent_config = isolated_agent_config
    write_agent_config(mcp=mcp_config_for(loopback_mcp_server), max_iters=3)
    bottom_model = RoutedReActModel()
    manager = FakeProviderManager(FakeProvider(bottom_model))

    for provider_manager in (
        model_factory.ProviderManager,
        executor_module.ProviderManager,
    ):
        monkeypatch.setattr(
            provider_manager,
            "ensure_tenant_provider_storage",
            lambda _tenant_id: None,
        )
        monkeypatch.setattr(
            provider_manager,
            "get_instance",
            lambda _tenant_id=None: manager,
        )

    runner = AgentRunner(
        agent_id="critical-agent",
        workspace_dir=workspace_dir,
    )
    await runner.start()
    try:
        executor = CronExecutor(
            runner=runner,
            channel_manager=recording_channel_manager,
        )
        job = build_agent_job(
            workspace_dir=workspace_dir,
            text="Use the echo MCP tool and then answer.",
            timeout_seconds=15,
        )

        result = await executor.execute(job)
    finally:
        await runner.stop()

    assert bottom_model.reacted_with_tool is True
    assert bottom_model.reacted_with_final is True
    assert loopback_mcp_server.calls == [
        {"tool": "echo", "text": "from scheduled agent"},
    ]
    assert recording_channel_manager.events
    assert result.output_preview == (
        "final reply after echo:from scheduled agent"
    )
