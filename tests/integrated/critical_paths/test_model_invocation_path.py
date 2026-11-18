# -*- coding: utf-8 -*-
"""Critical-path checks for provider-to-model invocation."""

from __future__ import annotations

import io
import json

import pytest
from agentscope.model._model_response import ChatResponse
from agentscope.model._model_usage import ChatUsage

from swe.agents import model_factory
from swe.config.llm_workload import LLM_WORKLOAD_CRON, bind_llm_workload
from swe.providers.rate_limiter import reset_rate_limiter
from swe.providers.retry_chat_model import RetryChatModel
from swe.observability import Observability, Scope, bind_context
from swe.observability.config import EmitterConfig
from swe.observability.emitter import JsonlEmitter

from tests.integrated.critical_paths.conftest import (
    DeterministicChatModel,
    FakeProvider,
    FakeProviderManager,
)


@pytest.fixture(autouse=True)
def _reset_rate_limiter_registry():
    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.mark.asyncio
async def test_provider_model_factory_wrappers_and_retry_are_in_invocation_path(
    monkeypatch,
    isolated_agent_config,
) -> None:
    _, write_agent_config = isolated_agent_config
    write_agent_config()
    bottom_model = DeterministicChatModel(
        [
            TimeoutError("first model call timed out"),
            ChatResponse(
                content=[{"type": "text", "text": "retry ok"}],
                usage=ChatUsage(input_tokens=1, output_tokens=1, time=0.0),
            ),
        ],
    )
    manager = FakeProviderManager(FakeProvider(bottom_model))

    monkeypatch.setattr(
        model_factory.ProviderManager,
        "ensure_tenant_provider_storage",
        lambda _tenant_id: None,
    )
    monkeypatch.setattr(
        model_factory.ProviderManager,
        "get_instance",
        lambda _tenant_id=None: manager,
    )

    model, formatter = model_factory.create_model_and_formatter(
        agent_id="critical-agent",
    )

    assert isinstance(model._model, RetryChatModel)
    assert formatter is not None

    with bind_llm_workload(LLM_WORKLOAD_CRON):
        response = await model([])

    assert response.content[0]["text"] == "retry ok"
    assert len(bottom_model.calls) == 2


@pytest.mark.asyncio
async def test_model_retry_creates_linked_request_attempt_spans(
    monkeypatch,
    isolated_agent_config,
) -> None:
    _, write_agent_config = isolated_agent_config
    write_agent_config()
    bottom_model = DeterministicChatModel(
        [
            TimeoutError("private provider detail"),
            ChatResponse(
                content=[{"type": "text", "text": "retry ok"}],
                usage=ChatUsage(input_tokens=5, output_tokens=2, time=0.0),
            ),
        ],
    )
    manager = FakeProviderManager(FakeProvider(bottom_model))
    monkeypatch.setattr(
        model_factory.ProviderManager,
        "ensure_tenant_provider_storage",
        lambda _tenant_id: None,
    )
    monkeypatch.setattr(
        model_factory.ProviderManager,
        "get_instance",
        lambda _tenant_id=None: manager,
    )
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    monkeypatch.setattr(
        "swe.observability.instrumentation.default_emitter",
        lambda: emitter,
    )
    context = Observability().admit_run(
        scope=Scope("svc", "source", "tenant", "critical-agent"),
        enabled=True,
    )
    model, _formatter = model_factory.create_model_and_formatter(
        agent_id="critical-agent",
    )

    with bind_context(context), bind_llm_workload(LLM_WORKLOAD_CRON):
        result = await model([{"content": "private prompt"}])

    emitter.close()
    assert result.content[0]["text"] == "retry ok"
    assert len(bottom_model.calls) == 2
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    span_starts = [
        record for record in records if record["event_name"] == "span.started"
    ]
    request_starts = [
        record
        for record in records
        if record.get("operation") == "request_attempt"
        and record["event_name"] == "span.started"
    ]
    request_ends = [
        record
        for record in records
        if record.get("operation") == "request_attempt"
        and record["event_name"] == "span.ended"
    ]
    span_ends = [
        record for record in records if record["event_name"] == "span.ended"
    ]
    logical_end = next(
        record for record in span_ends if record.get("operation") == "chat"
    )
    assert len(span_starts) == 3
    assert len(request_starts) == len(request_ends) == 2, records
    assert [record["status"] for record in request_ends] == [
        "failed",
        "succeeded",
    ]
    assert request_starts[1]["links"] == [
        {
            "relation_type": "retry_of",
            "obs_span_id": request_starts[0]["obs_span_id"],
        },
    ]
    assert logical_end["metrics"]["input_tokens"] == 5
    assert logical_end["metrics"]["output_tokens"] == 2
    assert "private provider detail" not in stream.getvalue()


@pytest.mark.asyncio
async def test_empty_output_retry_emits_cause_and_linked_request_attempts(
    monkeypatch,
    isolated_agent_config,
) -> None:
    _, write_agent_config = isolated_agent_config
    write_agent_config()
    bottom_model = DeterministicChatModel(
        [
            ChatResponse(
                content=[],
                usage=ChatUsage(input_tokens=0, output_tokens=0, time=0.0),
            ),
            ChatResponse(
                content=[{"type": "text", "text": "retry ok"}],
                usage=ChatUsage(input_tokens=5, output_tokens=2, time=0.0),
            ),
        ],
    )
    manager = FakeProviderManager(FakeProvider(bottom_model))
    monkeypatch.setattr(
        model_factory.ProviderManager,
        "ensure_tenant_provider_storage",
        lambda _tenant_id: None,
    )
    monkeypatch.setattr(
        model_factory.ProviderManager,
        "get_instance",
        lambda _tenant_id=None: manager,
    )
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    monkeypatch.setattr(
        "swe.observability.instrumentation.default_emitter",
        lambda: emitter,
    )
    context = Observability().admit_run(
        scope=Scope("svc", "source", "tenant", "critical-agent"),
        enabled=True,
    )
    model, _formatter = model_factory.create_model_and_formatter(
        agent_id="critical-agent",
    )

    with bind_context(context), bind_llm_workload(LLM_WORKLOAD_CRON):
        result = await model([{"content": "private prompt"}])

    emitter.close()
    assert result.content[0]["text"] == "retry ok"
    assert len(bottom_model.calls) == 2
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    attempts = [
        record
        for record in records
        if record.get("operation") == "request_attempt"
    ]
    starts = [
        record for record in attempts if record["event_name"] == "span.started"
    ]
    ends = [
        record for record in attempts if record["event_name"] == "span.ended"
    ]
    retries = [
        record
        for record in records
        if record.get("event_type") == "model.retry_scheduled"
    ]
    assert len(retries) == 1
    retry = retries[0]
    assert len(starts) == len(ends) == 2
    assert [record["status"] for record in ends] == ["failed", "succeeded"]
    assert (
        ends[0]["error_type"] == retry["error_type"] == "EmptyModelOutputError"
    )
    assert retry["retries"] == 1
    assert starts[1]["links"] == [
        {
            "relation_type": "retry_of",
            "obs_span_id": starts[0]["obs_span_id"],
        },
    ]
    assert "private prompt" not in stream.getvalue()
    assert "retry ok" not in stream.getvalue()


def test_provider_model_factory_passes_model_generation_config(
    monkeypatch,
) -> None:
    bottom_model = DeterministicChatModel([])
    provider = FakeProvider(
        bottom_model,
        generation_kwargs={"temperature": 0.2, "max_tokens": 4_096},
    )
    manager = FakeProviderManager(provider)

    monkeypatch.setattr(
        model_factory.ProviderManager,
        "ensure_tenant_provider_storage",
        lambda _tenant_id: None,
    )
    monkeypatch.setattr(
        model_factory.ProviderManager,
        "get_instance",
        lambda _tenant_id=None: manager,
    )

    model_factory.create_model_and_formatter()

    assert provider.request_generation_kwargs == [
        {"temperature": 0.2, "max_tokens": 4_096},
    ]
