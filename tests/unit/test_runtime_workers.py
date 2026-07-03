# -*- coding: utf-8 -*-
"""Tests for runtime-state worker helpers."""

from __future__ import annotations

from contextvars import ContextVar

import pytest

from swe.runtime_workers import run_runtime_state_work

_scope = ContextVar("scope", default="")


@pytest.mark.asyncio
async def test_run_runtime_state_work_preserves_contextvars() -> None:
    _scope.set("tenant-a.source-b")

    def read_scope() -> str:
        return _scope.get()

    assert await run_runtime_state_work(read_scope) == "tenant-a.source-b"


@pytest.mark.asyncio
async def test_run_runtime_state_work_passes_args_and_kwargs() -> None:
    def combine(left: str, right: str, *, separator: str) -> str:
        return f"{left}{separator}{right}"

    result = await run_runtime_state_work(
        combine,
        "runtime",
        "state",
        separator="-",
    )

    assert result == "runtime-state"
