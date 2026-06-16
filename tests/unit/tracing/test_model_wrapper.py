# -*- coding: utf-8 -*-
"""Tests for TracingModelWrapper trace context binding."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.tracing.model_wrapper import TracingModelWrapper


class _FakeModel:
    model_name = "fake-model"
    config = {"model_name": "fake-model"}

    async def __call__(self, messages, tools=None, tool_choice=None, **kwargs):
        del messages, tools, tool_choice, kwargs
        return SimpleNamespace(
            usage=SimpleNamespace(
                input_tokens=11,
                output_tokens=7,
            ),
        )


@pytest.mark.asyncio
async def test_wrapper_prefers_bound_trace_context_over_current_trace(
    monkeypatch,
) -> None:
    emitted = []
    updated = []

    class FakeTraceManager:
        enabled = True

        async def emit_llm_input(self, **kwargs):
            emitted.append(kwargs)
            return "span-1"

        async def emit_llm_output(
            self,
            trace_id,
            span_id,
            output_tokens,
            input_tokens=0,
        ):
            updated.append(
                {
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "output_tokens": output_tokens,
                    "input_tokens": input_tokens,
                },
            )

        async def update_span(self, **kwargs):
            updated.append(kwargs)

    current_trace = SimpleNamespace(
        trace_id="trace-current",
        user_id="user-current",
        session_id="session-current",
        channel="console",
        source_id="source-current",
        user_name=None,
        bbk_id=None,
    )

    monkeypatch.setattr(
        "swe.tracing.model_wrapper.get_trace_manager",
        FakeTraceManager,
    )
    monkeypatch.setattr(
        "swe.tracing.model_wrapper.get_current_trace",
        lambda: current_trace,
    )

    wrapper = TracingModelWrapper(
        "openai",
        _FakeModel(),
        trace_context={
            "trace_id": "trace-bound",
            "user_id": "user-bound",
            "session_id": "session-bound",
            "channel": "console",
            "source_id": "source-bound",
            "user_name": "user-name",
            "bbk_id": "bbk-1",
        },
    )

    await wrapper([{"role": "user", "content": "hello"}])

    assert emitted[0]["trace_id"] == "trace-bound"
    assert emitted[0]["user_id"] == "user-bound"
    assert emitted[0]["session_id"] == "session-bound"
    assert emitted[0]["source_id"] == "source-bound"
    assert updated[0]["trace_id"] == "trace-bound"
