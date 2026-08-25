# -*- coding: utf-8 -*-
"""Admission ordering for one query execution."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from agentscope.message import Msg
from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest

from swe.tracing.models import TraceStatus

from ..command_dispatch import _is_command, run_command_path


async def stream_admission(
    owner: Any,
    msgs: list[Any],
    *,
    request: AgentRequest,
    query: str | None,
    session_id: str,
    user_id: str,
) -> AsyncIterator[tuple[Msg, bool]]:
    """Resolve admission before command or normal query execution."""
    preflight = await owner._prepare_query_preflight(
        session_id=session_id,
        user_id=user_id,
        query=query,
        request=request,
    )
    if preflight.response is not None:
        yield preflight.response, True
        if preflight.cleanup_denied_memory:
            await owner._cleanup_denied_session_memory(
                session_id,
                user_id,
                denial_response=preflight.response,
            )
        return

    if not preflight.approval_consumed and query and _is_command(query):
        trace_id = await owner._start_query_trace(request, msgs)
        try:
            async for message, last in run_command_path(request, msgs, owner):
                yield message, last
        except asyncio.CancelledError:
            await owner._end_trace_if_needed(trace_id, TraceStatus.CANCELLED)
            raise
        except Exception as exc:
            await owner._end_trace_if_needed(
                trace_id,
                TraceStatus.ERROR,
                str(exc),
            )
            raise
        await owner._end_trace_if_needed(trace_id, TraceStatus.COMPLETED)
        return

    async for message, last in owner._stream_query_after_preflight(
        msgs,
        request=request,
        query=query,
        session_id=session_id,
        preflight=preflight,
    ):
        yield message, last
