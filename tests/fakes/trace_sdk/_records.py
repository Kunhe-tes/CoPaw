# -*- coding: utf-8 -*-
"""Test-only span records for the documented ``trace_sdk`` fake."""

from __future__ import annotations

import contextvars
from typing import Any

spans: list[dict[str, Any]] = []
current_span: contextvars.ContextVar[dict[str, Any] | None] = (
    contextvars.ContextVar(
        "fake_trace_sdk_current_span",
        default=None,
    )
)
shutdown_calls = 0


def reset() -> None:
    global shutdown_calls
    spans.clear()
    current_span.set(None)
    shutdown_calls = 0
