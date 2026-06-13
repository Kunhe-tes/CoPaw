# -*- coding: utf-8 -*-
"""Tests for SSE runtime diagnostic ASGI instrumentation."""

from __future__ import annotations

import pytest

from swe.app.middleware.sse_diagnostic import SSEDiagnosticMiddleware


class _Manager:
    def __init__(self) -> None:
        self.active = 0
        self.peak = 0
        self.opened = 0
        self.closed = 0

    def record_sse_opened(self) -> None:
        self.opened += 1
        self.active += 1
        self.peak = max(self.peak, self.active)

    def record_sse_closed(self) -> None:
        self.closed += 1
        self.active -= 1


async def _receive():
    return {"type": "http.disconnect"}


async def _send(_message) -> None:
    return None


def _scope() -> dict:
    return {"type": "http", "method": "GET", "path": "/stream", "headers": []}


@pytest.mark.asyncio
async def test_sse_response_increments_and_decrements_exactly_once() -> None:
    manager = _Manager()

    async def app(_scope, _receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/event-stream; charset=utf-8"),
                ],
            },
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"data: ok\n\n",
                "more_body": True,
            },
        )
        await send(
            {"type": "http.response.body", "body": b"", "more_body": False},
        )

    middleware = SSEDiagnosticMiddleware(app, manager=manager)
    await middleware(_scope(), _receive, _send)

    assert manager.opened == 1
    assert manager.closed == 1
    assert manager.active == 0
    assert manager.peak == 1


@pytest.mark.asyncio
async def test_sse_exception_decrements_exactly_once() -> None:
    manager = _Manager()

    async def app(_scope, _receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/event-stream")],
            },
        )
        raise RuntimeError("stream failed")

    middleware = SSEDiagnosticMiddleware(app, manager=manager)
    with pytest.raises(RuntimeError, match="stream failed"):
        await middleware(_scope(), _receive, _send)

    assert manager.opened == 1
    assert manager.closed == 1
    assert manager.active == 0


@pytest.mark.asyncio
async def test_non_sse_response_is_ignored() -> None:
    manager = _Manager()

    async def app(_scope, _receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/octet-stream")],
            },
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"file",
                "more_body": False,
            },
        )

    middleware = SSEDiagnosticMiddleware(app, manager=manager)
    await middleware(_scope(), _receive, _send)

    assert manager.opened == 0
    assert manager.closed == 0


@pytest.mark.asyncio
async def test_non_http_scope_is_ignored() -> None:
    manager = _Manager()
    called = False

    async def app(_scope, _receive, _send):
        nonlocal called
        called = True

    middleware = SSEDiagnosticMiddleware(app, manager=manager)
    await middleware({"type": "websocket"}, _receive, _send)

    assert called is True
    assert manager.opened == 0
