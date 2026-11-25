# -*- coding: utf-8 -*-
"""Task-local context binding for independent agent observability."""

from contextvars import ContextVar, Token
from typing import Iterator
from contextlib import contextmanager

from .models import ObservabilityContext

_CURRENT: ContextVar[ObservabilityContext | None] = ContextVar(
    "swe_agentobs_context",
    default=None,
)


def current_context() -> ObservabilityContext | None:
    return _CURRENT.get()


@contextmanager
def bind_context(context: ObservabilityContext | None) -> Iterator[None]:
    token: Token = _CURRENT.set(context)
    try:
        yield
    finally:
        _CURRENT.reset(token)
