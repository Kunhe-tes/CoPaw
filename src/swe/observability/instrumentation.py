# -*- coding: utf-8 -*-
"""Small business-boundary instrumentation facade."""

from __future__ import annotations

import asyncio
import time
from contextvars import ContextVar
from typing import Any, Literal

from .config import capture_enabled
from .context import bind_context, current_context
from .emitter import JsonlEmitter, default_emitter
from .models import (
    MetadataEvent,
    ObservabilityContext,
    new_id,
    producer_id,
    utc_now,
)


class SpanHandle:
    def __init__(
        self,
        *,
        emitter: JsonlEmitter,
        context: ObservabilityContext,
        span_id: str,
        parent_span_id: str | None,
        span_type: str,
        operation: str,
        name: str,
        attributes: dict[str, Any],
    ) -> None:
        self._emitter = emitter
        self._context = context.with_updates(parent_obs_span_id=parent_span_id)
        self.span_id = span_id
        self._started_at = utc_now()
        self._started_clock = time.monotonic_ns()
        self._base = {
            "obs_span_id": span_id,
            "span_type": span_type,
            "operation": operation,
            "name": name,
            "kind": "INTERNAL",
            **{
                key: value
                for key, value in attributes.items()
                if key
                not in {
                    "obs_run_id",
                    "obs_attempt_id",
                    "obs_span_id",
                    "parent_obs_span_id",
                    "event_name",
                    "entity_id",
                    "entity_kind",
                    "phase_key",
                    "local_seq",
                    "span_type",
                    "operation",
                    "name",
                }
            },
        }
        self._ended = False
        self._context_binding = None
        self._event_sequences: dict[str, int] = {}

    def event(self, name: str, **attributes: Any) -> bool:
        if self._ended:
            return False
        phase_key = name[:64]
        local_seq = self._event_sequences.get(phase_key, 0)
        self._event_sequences[phase_key] = local_seq + 1
        return self._emitter.emit(
            MetadataEvent(
                event_name="span.event",
                obs_context=self._context,
                entity_kind="span",
                entity_id=self.span_id,
                phase_key=phase_key,
                local_seq=local_seq,
                attributes={
                    **self._base,
                    "event_kind": name[:64],
                    **attributes,
                },
            ),
        )

    def end(self, *, status: str, **attributes: Any) -> bool:
        if self._ended:
            return False
        self._ended = True
        ended_at = utc_now()
        elapsed_us = max(
            0,
            (time.monotonic_ns() - self._started_clock) // 1000,
        )
        supplied_metrics = attributes.get("metrics")
        metrics = {"duration_us": elapsed_us}
        if isinstance(supplied_metrics, dict):
            metrics.update(supplied_metrics)
        metrics["duration_us"] = elapsed_us
        optional = {
            key: value
            for key, value in attributes.items()
            if key
            not in {
                "obs_run_id",
                "obs_attempt_id",
                "obs_span_id",
                "parent_obs_span_id",
                "event_name",
                "entity_id",
                "entity_kind",
                "phase_key",
                "local_seq",
                "started_at",
                "ended_at",
                "status",
                "metrics",
                "quality",
            }
        }
        return self._emitter.emit(
            MetadataEvent(
                event_name="span.ended",
                obs_context=self._context,
                entity_kind="span",
                entity_id=self.span_id,
                phase_key="ended",
                local_seq=0,
                attributes={
                    **self._base,
                    "started_at": self._started_at,
                    "ended_at": ended_at,
                    "status": status,
                    "metrics": metrics,
                    "quality": {"start_observed": True, "end_observed": True},
                    **optional,
                },
            ),
        )

    def start(self) -> bool:
        return self._emitter.emit(
            MetadataEvent(
                event_name="span.started",
                obs_context=self._context,
                entity_kind="span",
                entity_id=self.span_id,
                phase_key="started",
                local_seq=0,
                attributes={**self._base, "started_at": self._started_at},
            ),
        )

    def __enter__(self) -> "SpanHandle":
        self._context_binding = bind_context(
            self._context.with_updates(parent_obs_span_id=self.span_id),
        )
        self._context_binding.__enter__()
        return self

    def __exit__(self, exc_type, exc, _tb) -> Literal[False]:
        if not self._ended:
            self.end(
                status=(
                    "cancelled"
                    if exc_type
                    and issubclass(
                        exc_type,
                        (asyncio.CancelledError, KeyboardInterrupt),
                    )
                    else "failed" if exc_type else "succeeded"
                ),
                has_error=bool(exc_type),
                error_type=exc_type.__name__[:96] if exc_type else None,
            )
        if self._context_binding is not None:
            self._context_binding.__exit__(exc_type, exc, _tb)
            self._context_binding = None
        return False


_current_model_span: ContextVar[SpanHandle | None] = ContextVar(
    "agentobs_current_model_span",
    default=None,
)


def record_model_retry(
    attempt: int,
    max_attempts: int,
    error_type: str,
    delay_seconds: float,
) -> None:
    span = _current_model_span.get()
    if span is None:
        return
    span.event(
        "retry",
        retries=attempt,
        loop_count=max_attempts,
        error_type=error_type,
        metrics={"delay_ms": max(0, int(delay_seconds * 1000))},
    )


class ObservabilityModelWrapper:
    """Record one logical model call without retaining model payloads."""

    def __init__(
        self,
        model: Any,
        *,
        provider_key: str,
        model_key: str,
    ) -> None:
        self._model = model
        self._provider_key = provider_key
        self._model_key = model_key

    def __getattr__(self, name: str) -> Any:
        return getattr(self._model, name)

    @property
    def stream(self):
        return self._model.stream

    @stream.setter
    def stream(self, value):
        self._model.stream = value

    async def __call__(self, messages, *args, **kwargs):
        context = current_context()
        if context is None or not context.capture_enabled:
            return await self._model(messages, *args, **kwargs)
        handle = Observability().span(
            "LLM",
            "chat",
            name="model.call",
            kind="CLIENT",
            provider_key=self._provider_key,
            request_model_key=self._model_key,
            streaming=bool(getattr(self._model, "stream", False)),
        )
        if handle is None:
            return await self._model(messages, *args, **kwargs)
        started = time.monotonic_ns()
        token = _current_model_span.set(handle)
        try:
            result = await self._model(messages, *args, **kwargs)
            if _is_async_iterable(result):
                return self._consume_stream(result, handle, started)
            response_metadata = _model_response_metadata(result)
            if "model_key_source" not in response_metadata:
                response_metadata["model_key_source"] = "request_fallback"
            handle.end(
                status="succeeded",
                metrics=_usage_metrics(result),
                **response_metadata,
            )
            return result
        except asyncio.CancelledError:
            handle.end(status="cancelled", technical_status="cancelled")
            raise
        except Exception as exc:
            handle.end(
                status="failed",
                technical_status="error",
                has_error=True,
                error_type=type(exc).__name__,
            )
            raise
        finally:
            _current_model_span.reset(token)

    async def _consume_stream(self, stream, handle: SpanHandle, started: int):
        first_chunk_us = None
        first_visible_text_us = None
        latest_metrics: dict[str, Any] = {}
        response_metadata: dict[str, Any] = {}
        token = _current_model_span.set(handle)
        try:
            async for chunk in stream:
                if first_chunk_us is None and _has_model_output(chunk):
                    first_chunk_us = max(
                        0,
                        (time.monotonic_ns() - started) // 1000,
                    )
                if first_visible_text_us is None and _has_visible_model_text(
                    chunk,
                ):
                    first_visible_text_us = max(
                        0,
                        (time.monotonic_ns() - started) // 1000,
                    )
                latest_metrics = _usage_metrics(chunk) or latest_metrics
                response_metadata.update(_model_response_metadata(chunk))
                yield chunk
            metrics = dict(latest_metrics)
            if first_chunk_us is not None:
                metrics["first_chunk_us"] = first_chunk_us
            if first_visible_text_us is not None:
                metrics["first_visible_text_us"] = first_visible_text_us
            if "model_key_source" not in response_metadata:
                response_metadata["model_key_source"] = "request_fallback"
            handle.end(
                status="succeeded",
                metrics=metrics,
                **response_metadata,
            )
        except asyncio.CancelledError:
            handle.end(status="cancelled", technical_status="cancelled")
            raise
        except Exception as exc:
            handle.end(
                status="failed",
                technical_status="error",
                has_error=True,
                error_type=type(exc).__name__,
            )
            raise
        finally:
            _current_model_span.reset(token)


def _has_model_output(value: Any) -> bool:
    content = getattr(value, "content", None)
    if content is None and isinstance(value, dict):
        content = value.get("content")
    return bool(content)


def _has_visible_model_text(value: Any) -> bool:
    content = getattr(value, "content", None)
    if content is None and isinstance(value, dict):
        content = value.get("content")
    if not isinstance(content, (list, tuple)):
        return False
    return any(
        (
            isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
            and bool(block["text"].strip())
        )
        or (
            getattr(block, "type", None) == "text"
            and isinstance(getattr(block, "text", None), str)
            and bool(block.text.strip())
        )
        for block in content
    )


def _is_async_iterable(value: Any) -> bool:
    try:
        return hasattr(value, "__aiter__")
    except Exception:
        return False


def _usage_metrics(value: Any) -> dict[str, Any]:
    usage = getattr(value, "usage", None)
    if usage is None and isinstance(value, dict):
        usage = value.get("usage")
    if usage is None:
        return {}
    metrics = {"usage_known": True}
    for output_key, input_key in (
        ("input_tokens", "input_tokens"),
        ("output_tokens", "output_tokens"),
    ):
        token_value = getattr(usage, input_key, None)
        if token_value is None and isinstance(usage, dict):
            token_value = usage.get(input_key)
        if isinstance(token_value, int) and token_value >= 0:
            metrics[output_key] = token_value
    return metrics


def _model_response_metadata(value: Any) -> dict[str, Any]:
    metadata = getattr(value, "metadata", None)
    if not isinstance(metadata, dict):
        return {}
    response_model = metadata.get("model")
    finish_reason = metadata.get("finish_reason")
    result = {}
    if isinstance(response_model, str) and response_model.strip():
        result["response_model_key"] = response_model[:256]
        result["model_key_source"] = "response"
    if isinstance(finish_reason, str) and finish_reason.strip():
        result["finish_reason"] = finish_reason[:64]
    return result


class Observability:
    """Independent facade; disabled calls avoid copying attributes or payloads."""

    def __init__(self, emitter: JsonlEmitter | None = None) -> None:
        self._provided_emitter = emitter

    def _emitter_for(
        self,
        context: ObservabilityContext,
    ) -> JsonlEmitter | None:
        if not context.capture_enabled:
            return None
        try:
            return self._provided_emitter or default_emitter()
        except Exception:
            return None

    def admit_run(
        self,
        *,
        scope,
        business_ref: dict[str, str] | None = None,
        enabled: bool | None = None,
    ) -> ObservabilityContext:
        context = self.prepare_run(
            scope=scope,
            business_ref=business_ref,
            enabled=enabled,
        )
        self.accept_run(context)
        return context

    def prepare_run(
        self,
        *,
        scope,
        business_ref: dict[str, str] | None = None,
        enabled: bool | None = None,
    ) -> ObservabilityContext:
        return ObservabilityContext.new_run(
            capture_enabled=capture_enabled() if enabled is None else enabled,
            scope=scope,
            business_ref=business_ref,
        )

    def accept_run(self, context: ObservabilityContext) -> bool:
        emitter = self._emitter_for(context)
        if emitter is not None:
            return emitter.emit(
                MetadataEvent(
                    event_name="run.accepted",
                    obs_context=context,
                    entity_kind="run",
                    entity_id=context.obs_run_id,
                    phase_key="accepted",
                    local_seq=0,
                    attributes={
                        "started_at": context.run_started_at,
                        "status": "accepted",
                    },
                ),
            )
        return False

    def start_attempt(
        self,
        context: ObservabilityContext,
    ) -> ObservabilityContext:
        attempt = context.new_attempt()
        emitter = self._emitter_for(attempt)
        if emitter is not None:
            emitter.emit(
                MetadataEvent(
                    event_name="attempt.started",
                    obs_context=attempt,
                    entity_kind="attempt",
                    entity_id=attempt.obs_attempt_id or "",
                    phase_key="started",
                    local_seq=0,
                    attributes={"started_at": attempt.attempt_started_at},
                ),
            )
        return attempt

    def span(
        self,
        span_type: str,
        operation: str,
        *,
        name: str | None = None,
        parent_span_id: str | None = None,
        **attributes: Any,
    ) -> SpanHandle | None:
        context = current_context()
        if context is None:
            return None
        emitter = self._emitter_for(context)
        if emitter is None:
            return None
        span_id = new_id()
        handle = SpanHandle(
            emitter=emitter,
            context=context,
            span_id=span_id,
            parent_span_id=parent_span_id or context.parent_obs_span_id,
            span_type=span_type,
            operation=operation,
            name=name or operation,
            attributes=attributes,
        )
        handle.start()
        return handle

    def end_attempt(
        self,
        context: ObservabilityContext,
        *,
        status: str,
    ) -> bool:
        emitter = self._emitter_for(context)
        if emitter is None or context.obs_attempt_id is None:
            return False
        return emitter.emit(
            MetadataEvent(
                event_name="attempt.ended",
                obs_context=context,
                entity_kind="attempt",
                entity_id=context.obs_attempt_id,
                phase_key="ended",
                local_seq=0,
                attributes={
                    "status": status,
                    "started_at": context.attempt_started_at,
                    "ended_at": utc_now(),
                },
            ),
        )

    def end_run(self, context: ObservabilityContext, *, status: str) -> bool:
        emitter = self._emitter_for(context)
        if emitter is None:
            return False
        metrics = {}
        if (
            context.run_started_monotonic_ns is not None
            and context.run_clock_producer_id == producer_id()
        ):
            metrics["duration_us"] = max(
                0,
                (time.monotonic_ns() - context.run_started_monotonic_ns)
                // 1000,
            )
        return emitter.emit(
            MetadataEvent(
                event_name="run.ended",
                obs_context=context,
                entity_kind="run",
                entity_id=context.obs_run_id,
                phase_key="ended",
                local_seq=0,
                attributes={
                    "started_at": context.run_started_at,
                    "ended_at": utc_now(),
                    "status": status,
                    "terminal_fact_source": "business_settlement",
                    **({"metrics": metrics} if metrics else {}),
                },
            ),
        )

    def run_state(self, context: ObservabilityContext, *, status: str) -> bool:
        emitter = self._emitter_for(context)
        if emitter is None:
            return False
        return emitter.emit(
            MetadataEvent(
                event_name="run.state",
                obs_context=context,
                entity_kind="run",
                entity_id=context.obs_run_id,
                phase_key=f"state:{status}",
                local_seq=0,
                attributes={"status": status},
            ),
        )
