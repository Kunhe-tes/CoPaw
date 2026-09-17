# -*- coding: utf-8 -*-
"""Trusted W+ identifiers propagated with one background Agent task."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class WPlusRuntimeContext:
    """Server-issued identifiers for the exact SOP run using the event tool."""

    sop_session_id: str
    run_id: str
    attempt_id: str
    command: str


_CURRENT_WPLUS_RUNTIME: ContextVar[WPlusRuntimeContext | None] = ContextVar(
    "current_wplus_runtime",
    default=None,
)


@contextmanager
def bind_wplus_runtime(
    context: WPlusRuntimeContext,
) -> Iterator[None]:
    """Bind identifiers while TaskTracker creates its context-copying task."""

    token = _CURRENT_WPLUS_RUNTIME.set(context)
    try:
        yield
    finally:
        _CURRENT_WPLUS_RUNTIME.reset(token)


def get_current_wplus_runtime() -> WPlusRuntimeContext | None:
    """Return the trusted identifiers captured by the current Agent task."""

    return _CURRENT_WPLUS_RUNTIME.get()
