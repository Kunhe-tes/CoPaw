# -*- coding: utf-8 -*-
"""Document-contract tests for AgentTraceSDK semantic decorators."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from swe.agents.react_agent import SWEAgent
from swe.agents.tool_guard_mixin import ToolGuardMixin
from trace_sdk import chat_traced
from trace_sdk._records import reset, spans


@chat_traced(output_arguments_factory=lambda result: {"answer": result})
async def _traced_sample() -> str:
    return "done"


@chat_traced(output_arguments_factory=lambda result: {"answer": result})
async def _traced_failure() -> str:
    raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_fake_sdk_records_output_factory_value():
    reset()

    await _traced_sample()

    assert json.loads(spans[0]["attributes"]["cmb.output.arguments"]) == {
        "answer": "done",
    }


@pytest.mark.asyncio
async def test_fake_sdk_does_not_record_output_for_failed_call():
    reset()

    with pytest.raises(RuntimeError, match="boom"):
        await _traced_failure()

    assert "cmb.output.arguments" not in spans[0]["attributes"]


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
        ToolGuardMixin._run_approved_tool_call,
        "_trace_sdk_config",
    )
