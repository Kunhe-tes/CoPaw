# -*- coding: utf-8 -*-
"""A stalled HTTP writer must release its replay subscription."""

import asyncio

import pytest

from swe.app.runner.sse_response import ReplayStreamingResponse


@pytest.mark.asyncio
@pytest.mark.parametrize("keepalive", [False, True])
async def test_send_timeout_closes_source_without_cancelling_business(
    keepalive,
):
    closed = asyncio.Event()

    async def source():
        try:
            yield "data: first\n\n"
            await asyncio.Event().wait()
        finally:
            closed.set()

    async def send(message):
        if message["type"] == "http.response.body":
            await asyncio.Event().wait()

    generator = source()
    if keepalive:
        from swe.app.routers.console import _stream_with_keepalive

        body = _stream_with_keepalive(generator, interval=0.1)
    else:
        body = generator
    response = ReplayStreamingResponse(body, send_timeout=0.01)
    await asyncio.wait_for(response.stream_response(send), 1)
    assert closed.is_set()
