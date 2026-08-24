# -*- coding: utf-8 -*-
"""Contract tests for the deep QueryExecution facade seam."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from agentscope.message import Msg

from swe.app.runner.query_execution import (
    QueryExecution,
    QueryFrame,
    QueryInvocation,
)
from swe.app.runner.runner import AgentRunner


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
