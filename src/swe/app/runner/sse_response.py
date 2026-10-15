# -*- coding: utf-8 -*-
"""Bound stalled HTTP sends independently of an Agent producer's lifetime."""

import asyncio

from starlette.responses import StreamingResponse


class ReplayStreamingResponse(StreamingResponse):
    """End a negotiated subscription when its socket cannot make progress."""

    def __init__(
        self,
        content,
        *,
        send_timeout: float = 30,
        on_close=None,
        **kwargs,
    ):
        super().__init__(content, **kwargs)
        self.send_timeout = send_timeout
        self.on_close = on_close

    async def stream_response(self, send) -> None:
        async def bounded_send(message):
            await asyncio.wait_for(send(message), self.send_timeout)

        try:
            await super().stream_response(bounded_send)
        except asyncio.TimeoutError:
            # A stalled socket cannot receive a recovery control frame. Closing
            # its source detaches only this subscriber; the producer continues.
            pass
        finally:
            if self.on_close is not None:
                await self.on_close()
            close = getattr(self.body_iterator, "aclose", None)
            if close is not None:
                await close()
