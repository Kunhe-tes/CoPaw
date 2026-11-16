# -*- coding: utf-8 -*-
"""Runtime contract tests for independent Tool execution spans."""

from __future__ import annotations

import asyncio
import io
import json
from types import SimpleNamespace

import pytest

from swe.agents.tool_guard_mixin import ToolGuardMixin
from swe.observability.config import EmitterConfig
from swe.observability.context import bind_context
from swe.observability.emitter import JsonlEmitter
from swe.observability.models import ObservabilityContext, Scope


class _ToolExecutor:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    async def _acting(self, tool_call):
        self.calls.append(tool_call)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class _ObservedToolAgent(ToolGuardMixin, _ToolExecutor):
    def _resolve_mcp_server(self, _tool_name):
        return None

    def _tool_has_specific_timeout(self, _tool_name):
        return True


def _events(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "span_status", "technical_status", "has_error"),
    [
        (
            {"content": "safe result"},
            "succeeded",
            "OK",
            False,
        ),
        (
            {"isError": True, "error_type": "permission_denied"},
            "failed",
            "OK",
            False,
        ),
    ],
)
async def test_tool_execution_preserves_business_result_and_projects_outcome(
    monkeypatch,
    outcome,
    span_status,
    technical_status,
    has_error,
):
    from swe.observability import instrumentation

    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    monkeypatch.setattr(instrumentation, "default_emitter", lambda: emitter)
    agent = _ObservedToolAgent(outcome)
    tool_call = {"id": "call-1", "name": "read_file", "input": {}}
    context = ObservabilityContext.new_run(
        capture_enabled=True,
        scope=Scope("swe", "source-a", "tenant-a", "agent-a"),
    ).new_attempt()

    with bind_context(context):
        result = await agent._run_tool_call_with_hard_timeout_impl(
            tool_call,
            "read_file",
            {},
        )
    emitter.close()
    events = _events(stream)

    assert result is outcome
    assert agent.calls == [tool_call]
    assert [event["event_name"] for event in events] == [
        "span.started",
        "span.ended",
    ]
    assert events[0]["tool"]["tool_key"] == "read_file"
    assert events[0]["tool"]["tool_call_id"] == "call-1"
    assert events[1]["status"] == span_status
    assert events[1]["technical_status"] == technical_status
    assert events[1]["has_error"] is has_error
    assert events[1].get("error_type") == outcome.get("error_type")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status", "technical_status"),
    [
        (RuntimeError("private tool error"), "failed", "ERROR"),
        (asyncio.CancelledError(), "cancelled", None),
    ],
)
async def test_tool_execution_records_exception_and_preserves_propagation(
    monkeypatch,
    error,
    expected_status,
    technical_status,
):
    from swe.observability import instrumentation

    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    monkeypatch.setattr(instrumentation, "default_emitter", lambda: emitter)
    agent = _ObservedToolAgent(error)
    context = ObservabilityContext.new_run(
        capture_enabled=True,
        scope=Scope("swe", "source-a", "tenant-a", "agent-a"),
    ).new_attempt()

    with bind_context(context):
        with pytest.raises(type(error)):
            await agent._run_tool_call_with_hard_timeout_impl(
                {"id": "call-2", "name": "read_file", "input": {}},
                "read_file",
                {},
            )
    emitter.close()
    events = _events(stream)

    assert [event["event_name"] for event in events] == [
        "span.started",
        "span.ended",
    ]
    assert events[1]["status"] == expected_status
    assert events[1].get("technical_status") == technical_status
    if technical_status is not None:
        assert events[1]["error_type"] == type(error).__name__
    assert "private tool error" not in stream.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        ("auto_denied", "rejected"),
        ("needs_approval", "waiting_approval"),
    ],
)
async def test_guard_short_circuit_emits_guard_span_without_tool_execution(
    monkeypatch,
    decision,
    expected_status,
):
    from swe.observability import instrumentation

    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    monkeypatch.setattr(instrumentation, "default_emitter", lambda: emitter)

    class DenyingAgent(_ObservedToolAgent):
        def __init__(self):
            super().__init__({"content": "must not execute"})
            self._tool_guard_lock = asyncio.Lock()
            self.executed_guard_action = False

        def _ensure_tool_guard(self):
            return None

        async def _acting_shell_installation_denial(self, *_args):
            return False

        async def _acting_policy_denial(self, *_args, **_kwargs):
            return False

        async def _apply_pre_tool_hook(self, tool_call, tool_name, tool_input):
            return tool_call, tool_input, False, None

        async def _notify_skill_detector_tool_call(self, *_args):
            return None

        async def _decide_guard_action(self, tool_call):
            return SimpleNamespace(
                kind=decision,
                tool_name=tool_call["name"],
                tool_input=tool_call["input"],
                guard_result=None,
            )

        async def _execute_guard_action(self, _action, _tool_call):
            self.executed_guard_action = True
            return {"isError": True, "error_type": "tool_guard_denied"}

        async def _emit_tool_trace_start(self, *_args):
            return ""

        async def _emit_tool_trace_end(self, *_args, **_kwargs):
            return None

    agent = DenyingAgent()
    context = ObservabilityContext.new_run(
        capture_enabled=True,
        scope=Scope("swe", "source-a", "tenant-a", "agent-a"),
    ).new_attempt()

    with bind_context(context):
        result = await agent._acting_impl(
            {"id": "call-denied", "name": "read_file", "input": {}},
        )
    emitter.close()
    events = _events(stream)

    assert result["error_type"] == "tool_guard_denied"
    assert not agent.calls
    assert agent.executed_guard_action
    assert [event["event_name"] for event in events] == [
        "span.started",
        "span.ended",
    ]
    assert all(event["span_type"] == "Guard" for event in events)
    assert events[1]["status"] == expected_status
    assert events[1]["technical_status"] == "OK"
    assert events[1]["has_error"] is False
    from swe.observability.projector import _validate_payload

    for event in events:
        _validate_payload(json.dumps(event))
