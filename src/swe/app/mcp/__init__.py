# -*- coding: utf-8 -*-
"""MCP (Model Context Protocol) client management module.

This module provides hot-reloadable MCP client management,
completely independent from other app components.

It also provides drop-in replacements for AgentScope's MCP clients
that solve the CPU leak issue caused by cross-task context manager exits.
"""

import asyncio
import uuid
from typing import Any

from agentscope.mcp._client_base import MCPClientBase
from agentscope.mcp._mcp_function import MCPToolFunction
from agentscope.tool import ToolResponse
from mcp import ClientSession as _CS
from ...agents.tool_failure import build_structured_failure_output
from ...config.context import get_current_effective_tenant_id
from ...constant import (
    MCP_MAX_TOTAL_TIMEOUT,
    MCP_PER_NOTIFICATION_TIMEOUT,
)

from .manager import MCPClientManager
from .stateful_client import (
    HttpStatefulClient,
    StdIOStatefulClient,
    _call_with_timeout_refresh,
)
from .watcher import MCPConfigWatcher

# ---------------------------------------------------------------------------
# Helpers extracted from _patched_mcp_call to keep the main function flat.
# ---------------------------------------------------------------------------


def _build_on_progress(progress_event, progress_queue, watchdog_cb):
    """Return an ``_on_progress`` callback that resets the watchdog,
    sets *progress_event*, and enqueues the notification for the
    frontend-facing generator."""

    async def _on_progress(_progress, _total, _message):
        progress_event.set()
        if watchdog_cb is not None:
            watchdog_cb()
        await progress_queue.put((_progress, _total, _message))

    return _on_progress


def _launch_call_tool(
    session,
    tool_name: str,
    kwargs: dict,
    timeout,
    meta: dict,
    per_timeout: float,
    max_total: float | None,
    progress_event: asyncio.Event,
    watchdog_cb,
    progress_queue: asyncio.Queue,
) -> asyncio.Task:
    """Fire ``call_tool`` as a background task.

    When done the task puts either the ``CallToolResult`` or the raised
    exception into *progress_queue*.
    """

    async def _run():
        try:
            coro = session.call_tool(
                tool_name,
                arguments=kwargs,
                read_timeout_seconds=timeout,
                meta=meta,
            )
            result = await _call_with_timeout_refresh(
                coro,
                per_timeout,
                max_total,
                f"call_tool({tool_name})",
                tool_name,
                progress_event,
                on_progress_callback=watchdog_cb,
            )
            await progress_queue.put(result)
        except Exception as exc:
            await progress_queue.put(exc)

    return asyncio.ensure_future(_run())


async def _drain_progress(
    progress_queue,
    tool_name,
    result_box,
):
    """Yield intermediate ``ToolResponse`` chunks from *progress_queue*.

    The final ``CallToolResult`` is appended to *result_box* (a one-element
    list) so the caller can retrieve it after the generator is exhausted.
    """
    while True:
        item = await progress_queue.get()
        if isinstance(item, Exception):
            raise item
        if isinstance(item, ToolResponse):
            yield item
        elif isinstance(item, tuple):
            _p, _t, msg = item
            yield ToolResponse(
                content=msg or f"tool '{tool_name}' running",
                stream=True,
                is_last=False,
            )
        else:
            result_box.append(item)
            return


async def _call_with_progress(
    session,
    tool_name: str,
    kwargs: dict,
    timeout,
    meta: dict,
    per_timeout: float,
    max_total: float | None,
    progress_event: asyncio.Event,
    watchdog_cb,
    progress_queue: asyncio.Queue,
    wrap_tool_result: bool,
):
    """Run ``call_tool`` in a background task, yield all chunks.

    Yields intermediate progress ``ToolResponse`` chunks while the tool
    executes, then yields the final result (or wrapped result).
    """
    task = _launch_call_tool(
        session,
        tool_name,
        kwargs,
        timeout,
        meta,
        per_timeout,
        max_total,
        progress_event,
        watchdog_cb,
        progress_queue,
    )
    result_box: list = []
    try:
        async for chunk in _drain_progress(
            progress_queue,
            tool_name,
            result_box,
        ):
            yield chunk
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    # Yield the final result.
    res = result_box[0]
    if wrap_tool_result:
        as_content = MCPClientBase._convert_mcp_content_to_as_blocks(
            res.content,
        )
        content: Any = as_content
        if getattr(res, "isError", False):
            content = build_structured_failure_output(
                error_type="mcp_tool_error",
                content=as_content,
            )
        yield ToolResponse(
            content=content,
            metadata=res.meta,
            stream=True,
            is_last=True,
        )
    else:
        yield res


# ---------------------------------------------------------------------------
# Monkey-patch
# ---------------------------------------------------------------------------

# Monkey-patch MCPToolFunction.__call__ to auto-inject _meta with progressToken.
# progressToken is generated from X-Tenant-Id (from request context) + UUID,
# and forwarded as meta to the MCP SDK's ClientSession.call_tool.
#
# This is an **async generator** so that call_tool_function() dispatches it
# through _async_generator_wrapper.  Each yielded ToolResponse triggers
# ReActAgent._acting -> self.print(), which pushes events into the agent
# message queue and ultimately to the frontend SSE stream.  Without this,
# the entire call_tool() duration produces zero frontend-visible events.
#
# NOTE: We bypass the original __call__ entirely because its signature
# (`**kwargs`) would swallow `meta` into the arguments dict instead of
# passing it as a keyword-only param to `session.call_tool(meta=...)`.
_original_mcp_call = MCPToolFunction.__call__


async def _patched_mcp_call(self: MCPToolFunction, **kwargs: Any):  # type: ignore[override]
    kwargs.pop("_meta", None)

    scope_id = get_current_effective_tenant_id() or "default"
    progress_token = f"{scope_id}@{uuid.uuid4()}"
    meta = {"progressToken": progress_token}

    progress_event = asyncio.Event()
    progress_queue: asyncio.Queue = asyncio.Queue()
    watchdog_cb = getattr(self, "on_progress_callback", None)
    on_progress = _build_on_progress(
        progress_event,
        progress_queue,
        watchdog_cb,
    )

    per_timeout = MCP_PER_NOTIFICATION_TIMEOUT
    max_total = MCP_MAX_TOTAL_TIMEOUT or None

    # Common keyword arguments for _call_with_progress.
    call_kw = {
        "tool_name": self.name,
        "kwargs": kwargs,
        "timeout": self.timeout,
        "meta": meta,
        "per_timeout": per_timeout,
        "max_total": max_total,
        "progress_event": progress_event,
        "watchdog_cb": watchdog_cb,
        "progress_queue": progress_queue,
        "wrap_tool_result": self.wrap_tool_result,
    }

    if self.client_gen:
        async with self.client_gen() as cli:
            read_stream, write_stream = cli[0], cli[1]
            async with _CS(read_stream, write_stream) as session:
                await session.initialize()
                session._progress_callbacks[progress_token] = on_progress
                try:
                    async for chunk in _call_with_progress(session, **call_kw):
                        yield chunk
                finally:
                    await asyncio.sleep(0.1)
                    session._progress_callbacks.pop(progress_token, None)
    else:
        session = self.session
        session._progress_callbacks[progress_token] = on_progress
        try:
            async for chunk in _call_with_progress(session, **call_kw):
                yield chunk
        finally:
            await asyncio.sleep(0.1)
            session._progress_callbacks.pop(progress_token, None)


MCPToolFunction.__call__ = _patched_mcp_call  # type: ignore[method-assign]

__all__ = [
    "HttpStatefulClient",
    "MCPClientManager",
    "MCPConfigWatcher",
    "StdIOStatefulClient",
]
