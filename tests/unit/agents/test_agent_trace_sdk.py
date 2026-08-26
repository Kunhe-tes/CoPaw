# -*- coding: utf-8 -*-
"""Document-contract tests for AgentTraceSDK semantic decorators."""

from __future__ import annotations

from types import SimpleNamespace

from swe.agents.react_agent import SWEAgent
from swe.agents.tool_guard_mixin import ToolGuardMixin


def test_reasoning_uses_chat_traced_without_output_capture() -> None:
    config = SWEAgent._run_reasoning_with_internal_context._trace_sdk_config
    agent = SimpleNamespace(
        _resolved_model_slot={"provider_id": "provider-1", "model": "model-1"},
    )

    assert config["request_model_factory"](agent, None) == "model-1"
    assert config["provider_name_factory"](agent, None) == "provider-1"
    assert config["output_arguments_factory"]("model output") == {}


def test_only_main_reasoning_uses_chat_traced() -> None:
    assert not hasattr(SWEAgent._summarizing, "_trace_sdk_config")


def test_common_tool_execution_uses_execute_tool_traced() -> None:
    config = ToolGuardMixin._run_tool_call_with_hard_timeout._trace_sdk_config
    agent = SimpleNamespace()
    tool_input = {"command": "pwd"}

    assert (
        config["tool_name_factory"](
            agent,
            {"id": "call-1"},
            "execute_shell_command",
            tool_input,
        )
        == "execute_shell_command"
    )
    assert (
        config["input_arguments_factory"](
            agent,
            {"id": "call-1"},
            "execute_shell_command",
            tool_input,
        )
        == tool_input
    )
    assert config["output_arguments_factory"]({"content": "tool output"}) == {}
    assert not hasattr(
        ToolGuardMixin._run_approved_tool_call, "_trace_sdk_config",
    )
