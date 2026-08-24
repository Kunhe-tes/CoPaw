# -*- coding: utf-8 -*-
"""Live adapters used while the query execution implementation migrates."""

from __future__ import annotations

from typing import Any, AsyncIterator

from . import QueryFrame, QueryInvocation
from ..command_dispatch import _get_last_user_text


class LegacyQueryExecutionAdapter:
    """Run the current AgentRunner entry flow through QueryExecution."""

    def __init__(self, runner: Any) -> None:
        self._runner = runner

    async def stream(
        self,
        invocation: QueryInvocation,
    ) -> AsyncIterator[QueryFrame]:
        """Map the immutable invocation to the legacy mutable entry flow."""
        msgs = list(invocation.msgs)
        request = invocation.request
        async for message, last in self._runner._stream_query_entry(
            msgs,
            request=request,
            query=_get_last_user_text(msgs),
            session_id=getattr(request, "session_id", "") or "",
            user_id=getattr(request, "user_id", "") or "",
        ):
            yield QueryFrame(message=message, last=last)
