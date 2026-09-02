# -*- coding: utf-8 -*-
"""Contract tests for the deep QueryExecution facade seam."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agentscope.message import Msg

from swe.app.runner.query_execution import (
    QueryExecution,
    QueryFrame,
    QueryInvocation,
)
from swe.app.runner.runner import AgentRunner, _QueryPreflight


def test_query_handler_context_prepares_trace_identity_metadata(
    tmp_path,
) -> None:
    runner = AgentRunner(agent_id="test-agent", workspace_dir=tmp_path)
    context = runner._prepare_query_handler_context(
        [Msg(name="user", role="user", content="hello")],
        SimpleNamespace(
            session_id="session-1",
            user_id="user-1",
            channel_meta={},
        ),
    )
    assert context.query == "hello"
    assert context.session_id == "session-1"
    assert context.trace_fields is None


class _RecordingAdapter:
    def __init__(self) -> None:
        self.invocations: list[QueryInvocation] = []

    async def stream(self, invocation: QueryInvocation):
        self.invocations.append(invocation)
        yield QueryFrame(
            message=Msg(name="Friday", role="assistant", content="first"),
            last=False,
        )
        yield QueryFrame(
            message=Msg(name="Friday", role="assistant", content="final"),
            last=True,
        )


@pytest.mark.asyncio
async def test_query_handler_preserves_query_execution_frame_order(
    tmp_path,
) -> None:
    """The facade forwards one immutable invocation without reordering frames."""
    runner = AgentRunner(agent_id="test-agent", workspace_dir=tmp_path)
    adapter = _RecordingAdapter()
    runner._query_execution = QueryExecution(adapter)
    request = SimpleNamespace(
        session_id="session-1",
        user_id="user-1",
        channel="console",
        channel_meta={},
    )
    messages = [Msg(name="user", role="user", content="hello")]

    frames = [
        frame
        async for frame in runner.query_handler(messages, request=request)
    ]

    assert adapter.invocations == [
        QueryInvocation(request=request, msgs=tuple(messages)),
    ]
    assert [(msg.get_text_content(), last) for msg, last in frames] == [
        ("first", False),
        ("final", True),
    ]


@pytest.mark.asyncio
async def test_live_adapter_runs_admission_without_runner_entry(
    tmp_path,
) -> None:
    """The live Adapter owns admission instead of calling the legacy entry."""
    runner = AgentRunner(agent_id="test-agent", workspace_dir=tmp_path)
    request = SimpleNamespace(
        session_id="session-1",
        user_id="user-1",
        channel="console",
        channel_meta={},
    )
    runner._prepare_query_preflight = AsyncMock(
        return_value=_QueryPreflight(
            response=Msg(name="Friday", role="assistant", content="blocked"),
        ),
    )

    async def unexpected_legacy_entry(*_args, **_kwargs):
        if _args:
            raise AssertionError("live adapter called runner entry")
        yield Msg(name="Friday", role="assistant", content="unexpected"), True

    runner._stream_query_entry = unexpected_legacy_entry

    frames = [
        frame
        async for frame in runner.query_handler(
            [Msg(name="user", role="user", content="hello")],
            request=request,
        )
    ]

    assert [(msg.get_text_content(), last) for msg, last in frames] == [
        ("blocked", True),
    ]
