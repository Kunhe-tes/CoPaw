# -*- coding: utf-8 -*-
"""Agent operation Span 契约测试。"""

from __future__ import annotations

import pytest

from swe.agents import react_agent


class _FakeSpan:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_agent_operation_span_uses_agent_contract(monkeypatch):
    calls: list[tuple[tuple, dict]] = []

    class _FakeObservability:
        def span(self, *args, **kwargs):
            calls.append((args, kwargs))
            return _FakeSpan()

    monkeypatch.setattr(
        "swe.observability.instrumentation.Observability",
        _FakeObservability,
    )

    with react_agent._agent_operation_span():
        pass

    assert calls == [
        (("Agent", "agent.execute"), {"name": "agent.execute"}),
    ]


def test_agent_operation_span_degrades_when_observability_fails(monkeypatch):
    class _BrokenObservability:
        def span(self, *_args, **_kwargs):
            raise RuntimeError("observability unavailable")

    monkeypatch.setattr(
        "swe.observability.instrumentation.Observability",
        _BrokenObservability,
    )

    with react_agent._agent_operation_span():
        pass
