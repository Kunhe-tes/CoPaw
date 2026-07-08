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
    _wait_for_lifecycle_signal,
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


class _ReadyContextManager:
    async def __aenter__(self):
        return object(), object()

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


class _ReadySession:
    def __init__(self, *_args, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    async def initialize(self) -> None:
        return None


class _ReloadBlocksOnSecondInitializeSession:
    initialize_count = 0
    second_initialize_started: asyncio.Event
    release_second_initialize: asyncio.Event

    def __init__(self, *_args, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    async def initialize(self) -> None:
        type(self).initialize_count += 1
        if type(self).initialize_count == 2:
            type(self).second_initialize_started.set()
            await type(self).release_second_initialize.wait()


async def _assert_client_idle_does_not_poll_sleep(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    import swe.app.mcp.stateful_client as stateful_client_module

    sleep_called = asyncio.Event()
    release_sleep = asyncio.Event()

    async def fake_sleep(_delay: float) -> None:
        sleep_called.set()
        await release_sleep.wait()

    with monkeypatch.context() as scoped_monkeypatch:
        scoped_monkeypatch.setattr(
            stateful_client_module,
            "ClientSession",
            _ReadySession,
        )
        scoped_monkeypatch.setattr(
            stateful_client_module.asyncio,
            "sleep",
            fake_sleep,
        )
        await client.connect(timeout=1.0)
        try:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(sleep_called.wait(), timeout=0.02)
        finally:
            release_sleep.set()
            await client.close()


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
async def test_stdio_reload_waits_for_reconnected_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import mcp.client.stdio as mcp_stdio
    import swe.app.mcp.stateful_client as stateful_client_module

    _ReloadBlocksOnSecondInitializeSession.initialize_count = 0
    _ReloadBlocksOnSecondInitializeSession.second_initialize_started = (
        asyncio.Event()
    )
    _ReloadBlocksOnSecondInitializeSession.release_second_initialize = (
        asyncio.Event()
    )
    monkeypatch.setattr(
        mcp_stdio,
        "stdio_client",
        lambda *_args, **_kwargs: _ReadyContextManager(),
    )
    monkeypatch.setattr(
        stateful_client_module,
        "ClientSession",
        _ReloadBlocksOnSecondInitializeSession,
    )

    client = StdIOStatefulClient(
        name="demo",
        command="python",
        args=["-c", "print('ready')"],
        env=None,
        cwd=None,
    )
    await client.connect(timeout=1.0)
    reload_task = asyncio.create_task(client.reload(timeout=1.0))

    try:
        await asyncio.wait_for(
            (
                _ReloadBlocksOnSecondInitializeSession.second_initialize_started.wait()
            ),
            timeout=1.0,
        )
        await asyncio.sleep(0)
        assert reload_task.done() is False
        _ReloadBlocksOnSecondInitializeSession.release_second_initialize.set()
        await reload_task
    finally:
        _ReloadBlocksOnSecondInitializeSession.release_second_initialize.set()
        await asyncio.gather(reload_task, return_exceptions=True)
        await client.close()


@pytest.mark.asyncio
async def test_lifecycle_signal_wait_preserves_caller_cancellation() -> None:
    reload_event = asyncio.Event()
    stop_event = asyncio.Event()
    wait_task = asyncio.create_task(
        _wait_for_lifecycle_signal(reload_event, stop_event),
    )

    await asyncio.sleep(0)
    wait_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await wait_task


@pytest.mark.asyncio
async def test_stdio_client_idle_wait_is_event_driven(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import mcp.client.stdio as mcp_stdio

    monkeypatch.setattr(
        mcp_stdio,
        "stdio_client",
        lambda *_args, **_kwargs: _ReadyContextManager(),
    )

    client = StdIOStatefulClient(
        name="demo",
        command="python",
        args=["-c", "print('ready')"],
        env=None,
        cwd=None,
    )

    await _assert_client_idle_does_not_poll_sleep(monkeypatch, client)


@pytest.mark.asyncio
async def test_http_client_idle_wait_is_event_driven(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import swe.app.mcp.stateful_client as stateful_client_module

    monkeypatch.setattr(
        stateful_client_module,
        "streamable_http_client",
        lambda *_args, **_kwargs: _ReadyContextManager(),
    )

    client = HttpStatefulClient(
        name="demo",
        transport="streamable_http",
        url="https://mcp.example.test/stream",
        headers=None,
    )

    await _assert_client_idle_does_not_poll_sleep(monkeypatch, client)


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
