# -*- coding: utf-8 -*-
import io
import json
import threading
import asyncio
from types import SimpleNamespace

import pytest

from swe.observability import (
    Observability,
    ObservabilityContext,
    Scope,
    bind_context,
    current_context,
)
from swe.observability.config import EmitterConfig
from swe.observability.emitter import JsonlEmitter
from swe.observability.instrumentation import (
    ObservabilityModelWrapper,
    Observability as ObservabilityFacade,
)


class BlockingStream(io.StringIO):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def write(self, value):
        self.entered.set()
        self.release.wait(1)
        return super().write(value)


def test_context_carrier_and_nested_binding_are_isolated():
    original = ObservabilityContext.new_run(
        capture_enabled=True,
        scope=Scope("svc", "src", "tenant", "agent"),
        business_ref={"chat_id": "chat"},
    )
    restored = ObservabilityContext.from_carrier(original.to_carrier())
    assert restored == original
    assert "body" not in original.to_carrier()
    with bind_context(original):
        assert current_context() == original
        with bind_context(None):
            assert current_context() is None
        assert current_context() == original
    assert current_context() is None
    invalid_carrier = original.to_carrier()
    invalid_carrier["capture_enabled"] = "false"
    with pytest.raises(ValueError, match="boolean"):
        ObservabilityContext.from_carrier(invalid_carrier)


@pytest.mark.asyncio
async def test_concurrent_context_bindings_do_not_cross_tasks():
    first = ObservabilityContext.new_run(
        capture_enabled=True,
        scope=Scope("svc", "one", "tenant", "agent"),
    )
    second = ObservabilityContext.new_run(
        capture_enabled=True,
        scope=Scope("svc", "two", "tenant", "agent"),
    )

    async def read(context):
        with bind_context(context):
            await asyncio.sleep(0)
            return current_context().scope.source_id

    assert await asyncio.gather(read(first), read(second)) == ["one", "two"]


def test_span_emits_self_contained_end_and_preserves_exception():
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    obs = Observability(emitter)
    context = obs.admit_run(
        scope=Scope("svc", "src", "tenant", "agent"),
        enabled=True,
    )
    attempt = obs.start_attempt(context)
    next_attempt = obs.start_attempt(attempt)
    assert next_attempt.attempt_index == 2
    assert next_attempt.predecessor_attempt_id == attempt.obs_attempt_id
    assert next_attempt.attempt_started_at
    assert (
        ObservabilityContext.from_carrier(
            next_attempt.to_carrier(),
        ).attempt_started_at
        == next_attempt.attempt_started_at
    )
    with pytest.raises(RuntimeError, match="business failure"):
        with bind_context(attempt):
            with obs.span("Tool", "execute", name="registered.tool") as span:
                assert span.event("retry")
                assert span.event("retry")
                raise RuntimeError("business failure")
    obs.end_run(context, status="failed")
    assert emitter.close() == 0
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    ended = next(
        record for record in records if record["event_name"] == "span.ended"
    )
    assert ended["started_at"]
    assert ended["ended_at"]
    assert ended["status"] == "failed"
    assert ended["error_type"] == "RuntimeError"
    assert "business failure" not in stream.getvalue()
    assert records[-1]["event_name"] == "run.ended"
    incremental = [
        record for record in records if record["event_name"] == "span.event"
    ]
    assert [record["local_seq"] for record in incremental] == [0, 1]
    assert records[-1]["producer_id"]


def test_run_end_uses_local_monotonic_duration(monkeypatch):
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    obs = Observability(emitter)
    context = obs.admit_run(
        scope=Scope("svc", "src", "tenant", "agent"),
        enabled=True,
    )
    started_ns = context.run_started_monotonic_ns
    monkeypatch.setattr(
        "swe.observability.instrumentation.time.monotonic_ns",
        lambda: started_ns + 2_500_000,
    )

    assert obs.end_run(context, status="succeeded")
    emitter.close()
    ended = json.loads(stream.getvalue().splitlines()[-1])
    assert ended["metrics"]["duration_us"] == 2500


def test_run_end_omits_uncomparable_cross_process_duration():
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    obs = Observability(emitter)
    context = obs.admit_run(
        scope=Scope("svc", "src", "tenant", "agent"),
        enabled=True,
    )
    carrier = context.to_carrier()
    carrier["run_clock_producer_id"] = "another-process"
    restored = ObservabilityContext.from_carrier(carrier)

    assert restored.run_started_monotonic_ns is None
    assert obs.end_run(restored, status="succeeded")
    emitter.close()
    ended = json.loads(stream.getvalue().splitlines()[-1])
    assert "metrics" not in ended


@pytest.mark.asyncio
async def test_model_wrapper_records_usage_without_payload(monkeypatch):
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    monkeypatch.setattr(
        "swe.observability.instrumentation.default_emitter",
        lambda: emitter,
    )

    class Model:
        stream = False

        async def __call__(self, *_args, **_kwargs):
            from swe.observability.instrumentation import record_model_retry

            record_model_retry(1, 2, "TimeoutError", 0.01)
            return SimpleNamespace(
                content=[{"type": "text", "text": "private answer"}],
                usage=SimpleNamespace(input_tokens=3, output_tokens=4),
            )

    context = Observability().admit_run(
        scope=Scope("svc", "src", "tenant", "agent"),
        enabled=True,
    )
    with bind_context(context):
        await ObservabilityModelWrapper(
            Model(),
            provider_key="provider",
            model_key="model",
        )([])
    emitter.close()
    payload = stream.getvalue()
    assert "private answer" not in payload
    ended = next(
        json.loads(line)
        for line in payload.splitlines()
        if '"event_name":"span.ended"' in line
    )
    assert ended["span_type"] == "LLM"
    assert ended["metrics"]["input_tokens"] == 3
    assert ended["metrics"]["output_tokens"] == 4
    retry = next(
        json.loads(line)
        for line in payload.splitlines()
        if '"event_name":"span.event"' in line
    )
    assert retry["event_kind"] == "retry"
    assert retry["error_type"] == "TimeoutError"


@pytest.mark.asyncio
async def test_model_wrapper_records_first_nonempty_stream_chunk(monkeypatch):
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    monkeypatch.setattr(
        "swe.observability.instrumentation.default_emitter",
        lambda: emitter,
    )

    class Model:
        stream = True

        async def __call__(self, *_args, **_kwargs):
            async def chunks():
                yield SimpleNamespace(content=[])
                yield SimpleNamespace(
                    content=[{"type": "text", "text": "visible"}],
                    usage=SimpleNamespace(input_tokens=2, output_tokens=1),
                )

            return chunks()

    context = Observability().admit_run(
        scope=Scope("svc", "src", "tenant", "agent"),
        enabled=True,
    )
    with bind_context(context):
        chunks = await ObservabilityModelWrapper(
            Model(),
            provider_key="provider",
            model_key="model",
        )([])
        async for _chunk in chunks:
            pass
    emitter.close()
    ended = next(
        json.loads(line)
        for line in stream.getvalue().splitlines()
        if '"event_name":"span.ended"' in line
    )
    assert ended["metrics"]["first_chunk_us"] >= 0
    assert ended["metrics"]["usage_known"] is True


def test_cancellation_is_recorded_and_propagated():
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    obs = Observability(emitter)
    context = obs.admit_run(
        scope=Scope("svc", "src", "tenant", "agent"),
        enabled=True,
    )
    attempt = obs.start_attempt(context)
    with pytest.raises(asyncio.CancelledError):
        with bind_context(attempt):
            with obs.span("Agent", "execute"):
                raise asyncio.CancelledError()
    emitter.close()
    ended = next(
        json.loads(line)
        for line in stream.getvalue().splitlines()
        if '"event_name":"span.ended"' in line
    )
    assert ended["status"] == "cancelled"


def test_projection_drops_body_fields_and_bounds_values():
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    assert emitter.emit(
        {
            "schema_version": 1,
            "event_id": "event",
            "event_name": "span.event",
            "occurred_at": "now",
            "producer_id": "test",
            "entity_kind": "span",
            "entity_id": "span",
            "phase_key": "step",
            "local_seq": 0,
            "obs_run_id": "run",
            "run_started_at": "now",
            "capture_enabled": True,
            "scope": {
                "service_unit_id": "service",
                "source_id": "source",
                "tenant_id": "tenant",
                "agent_id": "agent",
            },
            "operation": "tool",
            "arguments": {"secret": "private"},
            "prompt": "private prompt",
            "name": "singlewordprompt",
        },
    )
    emitter.close()
    record = json.loads(stream.getvalue())
    assert "arguments" not in record
    assert "prompt" not in record
    assert record["name"] is None


def test_nested_metrics_survive_projection_and_optional_metadata_truncates():
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    event = {
        "schema_version": 1,
        "event_id": "event",
        "event_name": "span.ended",
        "occurred_at": "now",
        "producer_id": "test-producer",
        "entity_kind": "span",
        "entity_id": "span",
        "phase_key": "ended",
        "local_seq": 0,
        "obs_run_id": "run",
        "run_started_at": "now",
        "capture_enabled": True,
        "scope": {
            "service_unit_id": "service",
            "source_id": "source",
            "tenant_id": "tenant",
            "agent_id": "agent",
        },
        "metrics": {"duration_us": 123, "usage_known": False},
        "quality": {"start_observed": False, "end_observed": True},
        "model": {"provider_key": "provider", "request_model_key": "model"},
        "business_ref": {"chat_id": "chat"},
    }
    assert emitter.emit(event)
    emitter.close()
    record = json.loads(stream.getvalue())
    assert record["metrics"] == {"duration_us": 123, "usage_known": False}
    assert record["quality"]["end_observed"] is True

    truncated_stream = io.StringIO()
    truncated_emitter = JsonlEmitter(
        EmitterConfig(max_event_bytes=600),
        stream=truncated_stream,
    )
    assert truncated_emitter.emit(
        {
            **event,
            "events": [{"event_name": "event" * 50} for _ in range(32)],
        },
    )
    truncated_emitter.close()
    truncated = json.loads(truncated_stream.getvalue())
    assert truncated["metadata_truncated"] is True
    assert "events" not in truncated


def test_event_attributes_cannot_replace_envelope_identity():
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    obs = Observability(emitter)
    context = obs.admit_run(
        scope=Scope("svc", "src", "tenant", "agent"),
        enabled=True,
    )
    with bind_context(context):
        span = obs.span(
            "Agent",
            "execute",
            obs_run_id="attacker",
            event_name="run.ended",
        )
        span.end(
            status="succeeded",
            started_at="forged",
            metrics={"duration_us": 0},
            quality={"start_observed": False},
        )
    emitter.close()
    start, end = [
        json.loads(line) for line in stream.getvalue().splitlines()[1:]
    ]
    assert start["obs_run_id"] == context.obs_run_id
    assert start["event_name"] == "span.started"
    assert start["span_type"] == "Agent"
    assert end["obs_run_id"] == context.obs_run_id
    assert end["started_at"] != "forged"
    assert end["metrics"]["duration_us"] > 0
    assert end["quality"]["start_observed"] is True


def test_stdout_write_failure_is_contained():
    class BrokenStream:
        def write(self, _value):
            raise OSError("private failure detail")

        def flush(self):
            raise OSError("private failure detail")

    emitter = JsonlEmitter(EmitterConfig(), stream=BrokenStream())
    assert emitter.emit(
        {
            "schema_version": 1,
            "event_id": "event",
            "event_name": "observer.health",
            "occurred_at": "now",
            "producer_id": "test",
            "entity_kind": "observer",
            "entity_id": "observer",
            "phase_key": "health",
            "local_seq": 0,
        },
    )
    assert emitter.close() == 0
    assert emitter.dropped_count == 1


def test_shutdown_budget_is_clamped_to_one_second():
    config = EmitterConfig(shutdown_timeout=50)
    assert config.shutdown_timeout == 1


def test_emitter_initialization_failure_degrades_to_noop(monkeypatch):
    def fail_creation():
        raise RuntimeError("writer unavailable")

    monkeypatch.setattr(
        "swe.observability.instrumentation.default_emitter",
        fail_creation,
    )
    obs = Observability()
    context = obs.admit_run(
        scope=Scope("svc", "src", "tenant", "agent"),
        enabled=True,
    )
    assert context.capture_enabled
    assert obs.end_run(context, status="succeeded") is False


def test_plain_text_array_values_and_unregistered_enums_are_removed():
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=stream)
    assert emitter.emit(
        {
            "schema_version": 1,
            "event_id": "event",
            "event_name": "observer.health",
            "occurred_at": "now",
            "producer_id": "test",
            "entity_kind": "observer",
            "entity_id": "observer",
            "phase_key": "health",
            "local_seq": 0,
            "span_type": "user supplied sentence",
            "events": ["private body"],
        },
    )
    emitter.close()
    record = json.loads(stream.getvalue())
    assert record["span_type"] is None
    assert record["events"] is None


def test_required_protocol_overflow_is_dropped_without_invalid_json():
    stream = io.StringIO()
    emitter = JsonlEmitter(EmitterConfig(max_event_bytes=20), stream=stream)
    event = {
        "schema_version": 1,
        "event_id": "event",
        "event_name": "observer.health",
        "occurred_at": "now",
        "producer_id": "test",
        "entity_kind": "observer",
        "entity_id": "observer",
        "phase_key": "health",
        "local_seq": 0,
    }
    assert not emitter.emit(event)
    assert emitter.close() == 0
    assert stream.getvalue() == ""


def test_disabled_run_does_not_construct_default_emitter(monkeypatch):
    def fail_if_created():
        raise AssertionError("disabled instrumentation created an emitter")

    monkeypatch.setattr(
        "swe.observability.instrumentation.default_emitter",
        fail_if_created,
    )
    obs = ObservabilityFacade()
    context = obs.admit_run(
        scope=Scope("svc", "src", "tenant", "agent"),
        enabled=False,
    )
    with bind_context(context):
        assert obs.span("LLM", "call", messages=["private"]) is None
    assert not obs.end_run(context, status="succeeded")


def test_missing_required_protocol_fields_are_dropped():
    emitter = JsonlEmitter(EmitterConfig(), stream=io.StringIO())
    assert not emitter.emit({"event_name": "observer.health"})
    assert emitter.dropped_count == 1
    assert emitter.close() == 0


def test_queue_budget_counts_in_flight_event_and_shutdown_is_bounded():
    stream = BlockingStream()
    emitter = JsonlEmitter(
        EmitterConfig(max_queue_events=1, max_queue_bytes=2048),
        stream=stream,
    )
    event = {
        "schema_version": 1,
        "event_id": "event",
        "event_name": "observer.health",
        "occurred_at": "now",
        "producer_id": "test",
        "entity_kind": "observer",
        "entity_id": "observer",
        "phase_key": "health",
        "local_seq": 0,
    }
    assert emitter.emit(event)
    assert stream.entered.wait(1)
    assert not emitter.emit({**event, "event_id": "event-2"})
    assert emitter.dropped_count == 1
    remaining = emitter.close(timeout=0.01)
    assert remaining == 1
    stream.release.set()
