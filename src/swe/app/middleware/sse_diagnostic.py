# -*- coding: utf-8 -*-
"""Track active SSE responses for runtime diagnostics."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.types import Message, Receive, Scope, Send

from swe.app.runtime_diagnostic import RuntimeDiagnosticManager

ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class SSEDiagnosticMiddleware:
    """Count active SSE responses without buffering their streaming bodies."""

    def __init__(
        self,
        app: ASGIApp,
        manager: RuntimeDiagnosticManager,
    ) -> None:
        self.app = app
        self.manager = manager

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        opened = False

        async def send_wrapper(message: Message) -> None:
            nonlocal opened
            if not opened and _is_sse_response_start(message):
                self.manager.record_sse_opened()
                opened = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if opened:
                self.manager.record_sse_closed()


def _is_sse_response_start(message: dict[str, Any]) -> bool:
    if message["type"] != "http.response.start":
        return False

    for name, value in message.get("headers", []):
        if name.lower() != b"content-type":
            continue
        media_type = value.split(b";", maxsplit=1)[0].strip().lower()
        return media_type == b"text/event-stream"
    return False
