# -*- coding: utf-8 -*-
"""ASGI short-circuit for the process liveness probe."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.types import Receive, Scope, Send

ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_LIVENESS_PATH = "/api/health/health"
_LIVENESS_BODY = b'{"status":"ok"}'


class LivenessProbeMiddleware:
    """Return the liveness response before business middleware runs."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if (
            scope["type"] == "http"
            and scope.get("path") == _LIVENESS_PATH
            and scope.get("method") in {"GET", "HEAD"}
        ):
            body = b"" if scope.get("method") == "HEAD" else _LIVENESS_BODY
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (
                            b"content-length",
                            str(len(_LIVENESS_BODY)).encode("ascii"),
                        ),
                    ],
                },
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": body,
                },
            )
            return

        await self.app(scope, receive, send)
