# -*- coding: utf-8 -*-
"""Tests for the process-local liveness probe ASGI short-circuit."""

from __future__ import annotations

import json

import pytest

from swe.app.middleware.liveness_probe import LivenessProbeMiddleware


async def _receive():
    return {"type": "http.disconnect"}


@pytest.mark.asyncio
async def test_liveness_probe_returns_without_calling_downstream() -> None:
    called = False
    messages: list[dict] = []

    async def app(_scope, _receive, _send):
        nonlocal called
        called = True

    async def send(message):
        messages.append(message)

    middleware = LivenessProbeMiddleware(app)
    await middleware(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/health/health",
            "headers": [],
        },
        _receive,
        send,
    )

    assert called is False
    assert messages[0]["type"] == "http.response.start"
    assert messages[0]["status"] == 200
    assert messages[1]["type"] == "http.response.body"
    assert json.loads(messages[1]["body"]) == {"status": "ok"}


@pytest.mark.asyncio
async def test_non_liveness_request_calls_downstream() -> None:
    called = False

    async def app(_scope, _receive, send):
        nonlocal called
        called = True
        await send({"type": "http.response.start", "status": 204})
        await send({"type": "http.response.body", "body": b""})

    async def send(_message):
        return None

    middleware = LivenessProbeMiddleware(app)
    await middleware(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/version",
            "headers": [],
        },
        _receive,
        send,
    )

    assert called is True
