# -*- coding: utf-8 -*-
"""Document-contract tests for AgentTraceSDK semantic decorators."""

from __future__ import annotations

import asyncio
import json
from io import StringIO
from types import SimpleNamespace

import pytest
from agentscope.message import Msg

from swe.agents.agent_trace_output import ToolTraceOutcome
from swe.agents.react_agent import SWEAgent
from swe.agents.tool_guard_mixin import ToolGuardMixin
from swe.observability import (
    Observability,
    ObservabilityContext,
    Scope,
    bind_context,
)
from swe.observability.emitter import JsonlEmitter
from trace_sdk import chat_traced
from trace_sdk._records import reset, spans


class _ToolTraceAgent(ToolGuardMixin):
    async def _run_tool_call_with_hard_timeout_impl(
        self,
        _tool_call,
        _tool_name,
        _tool_input,
    ):
        return None

    def _extract_current_tool_response(
        self,
        _tool_use_id,
        *,
        include_structured_failure=False,
    ):
        assert include_structured_failure is True
        return {"message": "safe result"}

    def _resolve_mcp_server(self, _tool_name):
        return None


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


def test_reasoning_uses_chat_traced_with_structured_output_capture() -> None:
    config = SWEAgent._run_reasoning_with_internal_context._trace_sdk_config
    agent = SimpleNamespace(
        _resolved_model_slot={"provider_id": "provider-1", "model": "model-1"},
    )

    assert config["request_model_factory"](agent, None) == "model-1"
    assert config["provider_name_factory"](agent, None) == "provider-1"
    output = config["output_arguments_factory"](
        Msg(name="Friday", role="assistant", content="model output"),
    )
    assert output["text"] == "model output"


def test_only_main_reasoning_uses_chat_traced() -> None:
    assert not hasattr(SWEAgent._summarizing, "_trace_sdk_config")


def test_common_tool_execution_uses_execute_tool_traced() -> None:
    config = (
        ToolGuardMixin._run_tool_call_with_hard_timeout_traced._trace_sdk_config
    )
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
    output = config["output_arguments_factory"](
        ToolTraceOutcome(
            business_result=None,
            terminal_output={"content": "tool output"},
            tool_name="execute_shell_command",
        ),
    )
    assert output["status"] == "ok"
    assert not hasattr(
        ToolGuardMixin._run_approved_tool_call,
        "_trace_sdk_config",
    )


@pytest.mark.asyncio
async def test_public_tool_boundary_keeps_business_result_and_traces_memory_output():
    reset()
    agent = _ToolTraceAgent()

    result = await agent._run_tool_call_with_hard_timeout(
        {"id": "call-1", "name": "get_current_time", "input": {}},
        "get_current_time",
        {},
    )

    assert result is None
    assert json.loads(spans[0]["attributes"]["cmb.output.arguments"]) == {
        "status": "ok",
        "output_bytes": 26,
        "truncated": False,
        "output_preview": {"message": "safe result"},
    }


@pytest.mark.asyncio
async def test_real_tool_boundary_classifies_structured_results_and_cancellation(
    monkeypatch,
):
    from swe.observability import instrumentation

    class Agent(ToolGuardMixin):
        def __init__(self, result):
            self.result = result
            self.memory = SimpleNamespace(content=[])

        async def _run_tool_call_with_hard_timeout_raw(self, *_args):
            if isinstance(self.result, BaseException):
                raise self.result
            return self.result

        def _extract_current_tool_response(self, *_args, **_kwargs):
            return self.result

        def _resolve_mcp_server(self, _tool_name):
            return None

        def _tool_has_specific_timeout(self, _tool_name):
            return False

    sink = StringIO()
    emitter = JsonlEmitter(stream=sink)
    observability = Observability(emitter)
    monkeypatch.setattr(
        instrumentation,
        "Observability",
        lambda: observability,
    )
    context = observability.prepare_run(
        scope=Scope("svc", "source", "tenant", "agent"),
        enabled=True,
    )
    assert context.capture_enabled is True

    async def execute(result):
        with bind_context(context):
            return await Agent(result)._run_tool_call_with_hard_timeout_impl(
                {"id": "call-1"},
                "read_file",
                {"path": "/private/path"},
            )

    successful = {"content": "private result"}
    assert await execute(successful) == successful

    structured_failure = {
        "isError": True,
        "error_type": "permission_denied",
        "content": [{"type": "text", "text": "private detail"}],
    }
    assert await execute(structured_failure) == structured_failure

    assert await execute({"isError": True}) == {"isError": True}

    with pytest.raises(RuntimeError, match="private exception"):
        await execute(RuntimeError("private exception"))

    with pytest.raises(asyncio.CancelledError):
        await execute(asyncio.CancelledError())
    assert emitter.close(timeout=1) == 0
    events = [json.loads(line) for line in sink.getvalue().splitlines()]
    ended = [event for event in events if event["event_name"] == "span.ended"]
    assert [event["status"] for event in ended] == [
        "succeeded",
        "failed",
        "failed",
        "failed",
        "cancelled",
    ]
    assert ended[0]["technical_status"] == "OK"
    assert ended[0]["has_error"] is False
    assert ended[0]["tool"]["tool_key"] == "read_file"
    assert ended[0]["tool"]["tool_call_id"] == "call-1"
    assert ended[1]["technical_status"] == "OK"
    assert ended[1]["has_error"] is False
    assert ended[1]["error_type"] == "permission_denied"
    assert ended[2]["error_type"] == "tool_failure"
    assert ended[3]["technical_status"] == "ERROR"
    assert ended[3]["has_error"] is True
    assert "technical_status" not in ended[4]
    serialized = sink.getvalue()
    assert "/private/path" not in serialized
    assert "private result" not in serialized
    assert "private detail" not in serialized
    assert "private exception" not in serialized
