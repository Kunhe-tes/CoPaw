# -*- coding: utf-8 -*-
"""Small business-boundary instrumentation facade."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Literal

from .config import capture_enabled
from .context import bind_context, current_context
from .emitter import JsonlEmitter, default_emitter
from .models import MetadataEvent, ObservabilityContext, new_id, utc_now


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
                    "metrics": {"duration_us": elapsed_us},
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
        context = ObservabilityContext.new_run(
            capture_enabled=capture_enabled() if enabled is None else enabled,
            scope=scope,
            business_ref=business_ref,
        )
        emitter = self._emitter_for(context)
        if emitter is not None:
            emitter.emit(
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
        return context

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
                },
            ),
        )
