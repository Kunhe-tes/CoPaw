# -*- coding: utf-8 -*-
"""Tests for MCP connect timeout cleanup on hanging startup."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

import httpx
import pytest

from swe.app.mcp.stateful_client import (
    HttpStatefulClient,
    StdIOStatefulClient,
    _cancel_lifecycle_task,
)


@asynccontextmanager
async def _hanging_context_manager(*args, **kwargs):
    """模拟底层 transport 启动阶段卡住，直到被取消。"""
    del args, kwargs
    await asyncio.sleep(3600)
    yield None


class _FailingContextManager:
    """模拟 transport 在启动阶段立即失败。"""

    async def __aenter__(self):
        raise httpx.ConnectError("connection failed")

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


def _failing_context_manager(*args, **kwargs):
    del args, kwargs
    return _FailingContextManager()


@pytest.mark.asyncio
async def test_http_connect_timeout_cleans_up_hanging_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import swe.app.mcp.stateful_client as stateful_client_module

    monkeypatch.setattr(
        stateful_client_module,
        "streamable_http_client",
        _hanging_context_manager,
    )

    client = HttpStatefulClient(
        name="demo",
        transport="streamable_http",
        url="https://mcp.example.test/stream",
        headers=None,
    )

    started_at = time.perf_counter()
    with pytest.raises(asyncio.TimeoutError):
        await client.connect(timeout=0.05)

    elapsed = time.perf_counter() - started_at
    # Full-suite event loop contention can add noticeable scheduling delay
    # after the connect timeout fires; we only need to guard against hangs.
    assert elapsed < 0.5
    assert client._lifecycle_task is None or client._lifecycle_task.done()
    assert client.session is None
    assert client.is_connected is False


@pytest.mark.asyncio
async def test_http_connect_propagates_startup_errors_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import swe.app.mcp.stateful_client as stateful_client_module

    monkeypatch.setattr(
        stateful_client_module,
        "streamable_http_client",
        _failing_context_manager,
    )

    client = HttpStatefulClient(
        name="demo",
        transport="streamable_http",
        url="https://mcp.example.test/stream",
        headers=None,
    )

    started_at = time.perf_counter()
    with pytest.raises(httpx.ConnectError):
        await client.connect(timeout=30.0)

    elapsed = time.perf_counter() - started_at
    assert elapsed < 0.2
    assert client._lifecycle_task is None or client._lifecycle_task.done()
    assert client.session is None
    assert client.is_connected is False


@pytest.mark.asyncio
async def test_stdio_connect_timeout_cleans_up_hanging_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import mcp.client.stdio as mcp_stdio

    monkeypatch.setattr(
        mcp_stdio,
        "stdio_client",
        _hanging_context_manager,
    )

    client = StdIOStatefulClient(
        name="demo",
        command="python",
        args=["-c", "print('never reached')"],
        env=None,
        cwd=None,
    )

    started_at = time.perf_counter()
    with pytest.raises(asyncio.TimeoutError):
        await client.connect(timeout=0.05)

    elapsed = time.perf_counter() - started_at
    # Full-suite event loop contention can add noticeable scheduling delay
    # after the connect timeout fires; we only need to guard against hangs.
    assert elapsed < 0.5
    assert client._lifecycle_task is None or client._lifecycle_task.done()
    assert client.session is None
    assert client.is_connected is False


@pytest.mark.asyncio
async def test_stdio_connect_propagates_startup_errors_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import mcp.client.stdio as mcp_stdio

    monkeypatch.setattr(
        mcp_stdio,
        "stdio_client",
        _failing_context_manager,
    )

    client = StdIOStatefulClient(
        name="demo",
        command="python",
        args=["-c", "print('never reached')"],
        env=None,
        cwd=None,
    )

    started_at = time.perf_counter()
    with pytest.raises(httpx.ConnectError):
        await client.connect(timeout=30.0)

    elapsed = time.perf_counter() - started_at
    assert elapsed < 0.2
    assert client._lifecycle_task is None or client._lifecycle_task.done()
    assert client.session is None
    assert client.is_connected is False


@pytest.mark.asyncio
async def test_cancel_lifecycle_task_preserves_caller_cancellation() -> None:
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()

    async def slow_teardown_task() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            await release_cleanup.wait()

    lifecycle_task = asyncio.create_task(slow_teardown_task())
    cleanup_task = asyncio.create_task(
        _cancel_lifecycle_task(lifecycle_task),
    )

    await cleanup_started.wait()
    cleanup_task.cancel()
    release_cleanup.set()

    with pytest.raises(asyncio.CancelledError):
        await cleanup_task
