# -*- coding: utf-8 -*-
"""Implementation shared by the test-only documented SDK fake."""

from __future__ import annotations

import functools
import inspect
import uuid
import contextvars
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Callable

from . import _records


class SpanKind(str, Enum):
    SERVER = "SERVER"
    INTERNAL = "INTERNAL"
    CLIENT = "CLIENT"


@dataclass(frozen=True)
class TraceFields:
    task_id: str
    user_id: str
    session_id: str
    agent_id: str
    agent_version: str


class Span:
    def __init__(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        trace_fields: TraceFields | None = None,
    ) -> None:
        parent = _records.current_span.get()
        self.record = {
            "name": name,
            "kind": kind.value,
            "span_id": uuid.uuid4().hex,
            "parent_span_id": parent["span_id"] if parent else None,
            "trace_fields": asdict(trace_fields) if trace_fields else None,
            "attributes": {},
        }
        self._token: contextvars.Token | None = None

    async def __aenter__(self):
        _records.spans.append(self.record)
        self._token = _records.current_span.set(self.record)
        return self

    async def __aexit__(self, _type, _value, _traceback):
        if self._token is not None:
            _records.current_span.reset(self._token)

    def set_attribute(self, key: str, value: Any) -> None:
        self.record["attributes"][key] = value


class GlobalTracer:
    def start_as_current_span(
        self,
        name: str,
        *,
        kind: SpanKind = SpanKind.INTERNAL,
        trace_fields: TraceFields | None = None,
    ) -> Span:
        return Span(name, kind=kind, trace_fields=trace_fields)


global_tracer = GlobalTracer()


def decorator(name: str, **config: Any) -> Callable:
    def decorate(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapped(*args: Any, **kwargs: Any):
            async with global_tracer.start_as_current_span(name):
                result = func(*args, **kwargs)
                if inspect.isawaitable(result):
                    return await result
                return result

        wrapped._trace_sdk_config = config
        return wrapped

    return decorate
