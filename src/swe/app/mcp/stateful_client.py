# -*- coding: utf-8 -*-
"""MCP stateful clients with proper cross-task lifecycle management.

This module provides drop-in replacements for AgentScope's MCP clients
that solve the CPU leak issue caused by cross-task context manager exits.

The issue occurs when using AgentScope's StatefulClientBase in uvicorn/FastAPI:
- connect() enters AsyncExitStack in task A (e.g., startup event)
- close() exits AsyncExitStack in task B (e.g., reload background task)
- anyio.CancelScope requires enter/exit in the same task
- Error is silently ignored, leaving MCP processes and streams uncleaned

Our solution: Run the entire context manager lifecycle in a single dedicated
background task, using event-based signaling for reload/stop operations.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Any, Literal

import httpx
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

from agentscope.mcp import StatefulClientBase

from ...constant import (
    MCP_CALL_TIMEOUT,
    MCP_MAX_TOTAL_TIMEOUT,
    MCP_PER_NOTIFICATION_TIMEOUT,
)

logger = logging.getLogger(__name__)


async def _cancel_lifecycle_task(
    lifecycle_task: asyncio.Task | None,
) -> None:
    """主动取消生命周期任务，避免超时清理被底层 I/O 反向卡住。"""
    if lifecycle_task is None:
        return

    lifecycle_task.cancel()
    try:
        await lifecycle_task
    except asyncio.CancelledError:
        current_task = asyncio.current_task()
        if current_task is not None and current_task.cancelling():
            raise


async def _finalize_lifecycle_task(
    lifecycle_task: asyncio.Task | None,
) -> None:
    """Ensure a lifecycle task is drained without masking the caller error."""
    if lifecycle_task is None:
        return

    if lifecycle_task.done():
        await asyncio.gather(lifecycle_task, return_exceptions=True)
        return

    await _cancel_lifecycle_task(lifecycle_task)


async def _call_with_timeout(
    coro,
    timeout: float,
    operation: str,
    client_name: str,
):
    """Execute an async coroutine with a timeout guard.

    Args:
        coro: The awaitable to execute.
        timeout: Maximum seconds to wait before raising TimeoutError.
        operation: Human-readable operation name for logging (e.g. "call_tool").
        client_name: MCP client name for logging.

    Returns:
        The result of the coroutine.

    Raises:
        asyncio.TimeoutError: If the coroutine exceeds *timeout*.
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(
            "MCP client '%s' %s timed out after %.0fs",
            client_name,
            operation,
            timeout,
        )
        raise


async def _call_with_timeout_refresh(
    coro,
    per_notification_timeout: float,
    max_total_timeout: float | None,
    operation: str,
    client_name: str,
    progress_event: asyncio.Event | None = None,
    on_progress_callback=None,
):
    """Execute an async coroutine with per-notification timeout refresh.

    Instead of a single overall timeout, resets the countdown each time
    *progress_event* is set (typically by a progress_callback from the
    MCP SDK).  If no event arrives within *per_notification_timeout*
    seconds, or if *max_total_timeout* elapses, the coroutine is
    cancelled and asyncio.TimeoutError is raised.

    When *progress_event* is None, falls back to _call_with_timeout.
    """
    if progress_event is None:
        return await _call_with_timeout(
            coro,
            per_notification_timeout,
            operation,
            client_name,
        )

    task = asyncio.ensure_future(coro)
    loop = asyncio.get_running_loop()

    # When the task completes, set the event so that any in-progress
    # wait_for(progress_event.wait(), ...) returns immediately instead of
    # waiting for the full per_notification_timeout.
    task.add_done_callback(lambda _t: progress_event.set())

    deadline = loop.time() + max_total_timeout if max_total_timeout else None
    try:
        while not task.done():
            try:
                await asyncio.wait_for(
                    progress_event.wait(),
                    timeout=per_notification_timeout,
                )
                progress_event.clear()
                if on_progress_callback is not None:
                    on_progress_callback()
                logger.debug(
                    "MCP client '%s' %s: progress notification received, "
                    "timeout refreshed",
                    client_name,
                    operation,
                )
            except asyncio.TimeoutError:
                task.cancel()
                logger.error(
                    "MCP client '%s' %s timed out after %.0fs "
                    "(no progress notification)",
                    client_name,
                    operation,
                    per_notification_timeout,
                )
                raise
            # Check hard ceiling
            if deadline and loop.time() > deadline:
                task.cancel()
                logger.error(
                    "MCP client '%s' %s exceeded max total timeout %.0fs",
                    client_name,
                    operation,
                    max_total_timeout,
                )
                raise asyncio.TimeoutError()
        return task.result()
    except asyncio.CancelledError:
        task.cancel()
        raise
    except asyncio.TimeoutError:
        raise
    except Exception:
        task.cancel()
        raise


class StdIOStatefulClient(StatefulClientBase):
    """StdIO MCP client with proper cross-task lifecycle management.

    Drop-in replacement for agentscope.mcp.StdIOStatefulClient that solves
    the CPU leak issue by running the entire context manager lifecycle in
    a single dedicated background task.

    Key improvements:
    - Context manager enter/exit happens in the same asyncio task
    - Uses event-based signaling for reload/stop operations
    - Properly cleans up MCP subprocess and stdio streams
    - No CPU leak on reload
    - No zombie processes

    API-compatible with agentscope.mcp.StdIOStatefulClient for drop-in
    replacement.
    """

    def __init__(
        self,
        name: Any,
        command: Any,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        encoding: str = "utf-8",
        encoding_error_handler: Literal[
            "strict",
            "ignore",
            "replace",
        ] = "strict",
    ) -> None:
        """Initialize the StdIO MCP client.

        Args:
            name: Client identifier (unique across MCP servers)
            command: The executable to run to start the server
            args: Command line arguments to pass to the executable
            env: The environment to use when spawning the process
            cwd: The working directory to use when spawning the process
            encoding: The text encoding used when sending/receiving messages
            encoding_error_handler: The text encoding error handler

        Raises:
            TypeError: If name or command is not a string
        """
        if not isinstance(name, str):
            raise TypeError(f"name must be str, got {type(name).__name__}")
        if not isinstance(command, str):
            raise TypeError(
                f"command must be str, got {type(command).__name__}",
            )

        self.name = name
        self.server_params = StdioServerParameters(
            command=command,
            args=args or [],
            env=env,
            cwd=cwd,
            encoding=encoding,
            encoding_error_handler=encoding_error_handler,
        )

        # Lifecycle management
        self._lifecycle_task: asyncio.Task | None = None
        self._reload_event = asyncio.Event()
        self._ready_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._startup_waiter: asyncio.Future[None] | None = None

        # Session state
        self.session: ClientSession | None = None
        self.is_connected = False

        # Tool cache
        self._cached_tools = None

        # External callback invoked on each MCP progress notification.
        # Set by the agent layer to reset its watchdog timer.
        self.on_progress_callback = None

    async def _run_lifecycle(self) -> None:
        """Run MCP client lifecycle in a dedicated task.

        This ensures __aenter__ and __aexit__ are called in the same task,
        avoiding the cross-task cancel scope error.
        """
        from mcp.client.stdio import stdio_client

        while not self._stop_event.is_set():
            try:
                logger.debug(f"Connecting MCP client: {self.name}")

                # Enter context manager in THIS task
                async with AsyncExitStack() as stack:
                    context = await stack.enter_async_context(
                        stdio_client(self.server_params),
                    )
                    read_stream, write_stream = context[0], context[1]

                    # Initialize session
                    self.session = ClientSession(read_stream, write_stream)
                    await stack.enter_async_context(self.session)
                    await self.session.initialize()

                    # Mark as connected and signal ready
                    self.is_connected = True
                    self._ready_event.set()
                    if (
                        self._startup_waiter is not None
                        and not self._startup_waiter.done()
                    ):
                        self._startup_waiter.set_result(None)
                    logger.info(f"MCP client connected: {self.name}")

                    # Wait for reload or stop signal
                    while (
                        not self._reload_event.is_set()
                        and not self._stop_event.is_set()
                    ):
                        await asyncio.sleep(0.1)

                    # Clear state before exiting context
                    self.session = None
                    self.is_connected = False
                    self._cached_tools = None

                    if self._reload_event.is_set():
                        logger.info(f"Reloading MCP client: {self.name}")
                        self._reload_event.clear()
                        self._ready_event.clear()
                        # Context manager will exit here, then loop restarts
                    else:
                        logger.info(f"Stopping MCP client: {self.name}")
                        # Context manager will exit here, then loop exits

                # Context manager exits cleanly in THIS task

            except Exception as e:
                startup_failed = (
                    self._startup_waiter is not None
                    and not self._startup_waiter.done()
                    and not self.is_connected
                )
                logger.error(
                    f"Error in MCP client lifecycle for {self.name}: {e}",
                    exc_info=True,
                )
                self.session = None
                self.is_connected = False
                self._cached_tools = None
                self._ready_event.clear()
                if startup_failed:
                    self._startup_waiter.set_exception(e)
                    break
                await asyncio.sleep(1)

        logger.info(f"MCP client lifecycle task exited: {self.name}")

    async def connect(self, timeout: float = 30.0) -> None:
        """Connect to MCP server.

        Args:
            timeout: Connection timeout in seconds (default 30s)

        Raises:
            RuntimeError: If already connected
            asyncio.TimeoutError: If connection times out
        """
        if self.is_connected:
            raise RuntimeError(
                f"MCP client '{self.name}' is already connected. "
                f"Call close() before connecting again.",
            )

        # Start lifecycle task
        self._stop_event.clear()
        self._ready_event.clear()
        self._startup_waiter = asyncio.get_running_loop().create_future()
        self._lifecycle_task = asyncio.create_task(self._run_lifecycle())

        # Wait for initial connection
        try:
            await asyncio.wait_for(
                asyncio.shield(self._startup_waiter),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.error(
                f"Timeout waiting for MCP client '{self.name}' to connect",
            )
            self._stop_event.set()
            await _finalize_lifecycle_task(self._lifecycle_task)
            self._lifecycle_task = None
            self.session = None
            self.is_connected = False
            self._cached_tools = None
            self._ready_event.clear()
            if self._startup_waiter and not self._startup_waiter.done():
                self._startup_waiter.cancel()
            self._startup_waiter = None
            raise
        except Exception:
            self._stop_event.set()
            await _finalize_lifecycle_task(self._lifecycle_task)
            self._lifecycle_task = None
            self.session = None
            self.is_connected = False
            self._cached_tools = None
            self._ready_event.clear()
            self._startup_waiter = None
            raise
        self._startup_waiter = None

    async def close(self, ignore_errors: bool = True) -> None:
        """Close MCP client and clean up resources.

        Args:
            ignore_errors: Whether to ignore errors during cleanup

        Raises:
            RuntimeError: If not connected (unless ignore_errors=True)
        """
        if not self.is_connected:
            if not ignore_errors:
                raise RuntimeError(
                    f"MCP client '{self.name}' is not connected. "
                    f"Call connect() before closing.",
                )
            return

        try:
            # Signal stop and wait for lifecycle task to finish
            self._stop_event.set()
            if self._lifecycle_task:
                await self._lifecycle_task
                self._lifecycle_task = None
        except Exception as e:
            if not ignore_errors:
                raise
            logger.warning(
                f"Error closing MCP client '{self.name}': {e}",
            )

    async def reload(self, timeout: float = 30.0) -> None:
        """Reload the MCP client (reconnect).

        Args:
            timeout: Connection timeout in seconds (default 30s)

        Raises:
            RuntimeError: If not connected
            asyncio.TimeoutError: If reload times out
        """
        if not self.is_connected:
            raise RuntimeError(
                f"MCP client '{self.name}' is not connected. "
                f"Call connect() first.",
            )

        logger.info(f"Triggering reload for MCP client: {self.name}")
        self._reload_event.set()

        # Wait for new connection
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=timeout)
            logger.info(f"Reload completed for MCP client: {self.name}")
        except asyncio.TimeoutError:
            logger.error(
                f"Timeout waiting for MCP client '{self.name}' to reload",
            )
            raise

    async def list_tools(self, timeout: float = MCP_CALL_TIMEOUT):
        """Get all available tools from the server.

        Args:
            timeout: Maximum seconds to wait for the server response
                (default: ``MCP_CALL_TIMEOUT``).

        Returns:
            List of available MCP tools

        Raises:
            RuntimeError: If not connected
            asyncio.TimeoutError: If the call exceeds *timeout*
        """
        self._validate_connection()

        res = await _call_with_timeout(
            self.session.list_tools(),
            timeout=timeout,
            operation="list_tools",
            client_name=self.name,
        )

        # Cache the tools for later use
        self._cached_tools = res.tools
        return res.tools

    async def call_tool(
        self,
        name: str,
        arguments: dict | None = None,
        meta: dict[str, Any] | None = None,
    ):
        """Call a tool on the MCP server.

        Args:
            name: Tool name
            arguments: Tool arguments (optional)
            meta: Optional meta dict forwarded as _meta in JSON-RPC request
                (e.g. {"progressToken": "..."})

        Returns:
            Tool call result

        Raises:
            RuntimeError: If not connected
            asyncio.TimeoutError: If the call exceeds timeout
        """
        self._validate_connection()

        progress_event = asyncio.Event()
        progress_token = None

        if meta and "progressToken" in meta:
            progress_token = meta["progressToken"]

            async def _on_progress(_progress, _total, _message):
                progress_event.set()
                if self.on_progress_callback is not None:
                    self.on_progress_callback()

            # Inject into SDK's _progress_callbacks so _receive_loop
            # can dispatch progress notifications to our handler.
            # pylint: disable=protected-access
            self.session._progress_callbacks[progress_token] = _on_progress

        per_timeout = MCP_PER_NOTIFICATION_TIMEOUT
        max_total = MCP_MAX_TOTAL_TIMEOUT or None

        try:
            return await _call_with_timeout_refresh(
                self.session.call_tool(name, arguments or {}, meta=meta),
                per_notification_timeout=per_timeout,
                max_total_timeout=max_total,
                operation=f"call_tool({name})",
                client_name=self.name,
                progress_event=progress_event if progress_token else None,
                on_progress_callback=self.on_progress_callback,
            )
        finally:
            if progress_token:
                # Delay removal so _receive_loop can still dispatch
                # in-flight progress notifications that arrive after
                # the JSON-RPC response but before this finally runs.
                await asyncio.sleep(0.1)
                # pylint: disable=protected-access
                self.session._progress_callbacks.pop(progress_token, None)

    def _validate_connection(self) -> None:
        """Validate the connection to the MCP server.

        Raises:
            RuntimeError: If not connected or session not initialized
        """
        if not self.is_connected:
            raise RuntimeError(
                f"MCP client '{self.name}' is not connected. "
                f"Call connect() first.",
            )

        if not self.session:
            raise RuntimeError(
                f"MCP client '{self.name}' session is not initialized. "
                f"Call connect() first.",
            )


class HttpStatefulClient(StatefulClientBase):
    """HTTP/SSE MCP client with proper cross-task lifecycle management.

    Drop-in replacement for agentscope.mcp.HttpStatefulClient that solves
    the CPU leak issue by running the entire context manager lifecycle in
    a single dedicated background task.

    Supports both streamable HTTP and SSE transports.
    """

    def __init__(
        self,
        name: Any,
        transport: Any,
        url: Any,
        headers: dict[str, str] | None = None,
        timeout: float = 30,
        sse_read_timeout: float = 60 * 5,
        **client_kwargs: Any,
    ) -> None:
        """Initialize the HTTP MCP client.

        Args:
            name: Client identifier (unique across MCP servers)
            transport: The transport type ("streamable_http" or "sse")
            url: The URL to the MCP server
            headers: Additional headers to include in the HTTP request
            timeout: The timeout for the HTTP request in seconds
            sse_read_timeout: The timeout for reading SSE in seconds
            **client_kwargs: Additional keyword arguments for the client

        Raises:
            TypeError: If name, transport, or url is not a string
            ValueError: If transport is not "streamable_http" or "sse"
        """
        if not isinstance(name, str):
            raise TypeError(f"name must be str, got {type(name).__name__}")
        if not isinstance(transport, str):
            raise TypeError(
                f"transport must be str, got {type(transport).__name__}",
            )
        if transport not in ["streamable_http", "sse"]:
            raise ValueError(
                f"transport must be 'streamable_http' or 'sse', "
                f"got {transport!r}",
            )
        if not isinstance(url, str):
            raise TypeError(f"url must be str, got {type(url).__name__}")

        self.name = name
        self.transport = transport
        self.url = url
        self.headers = headers
        self.timeout = timeout
        self.sse_read_timeout = sse_read_timeout
        self.client_kwargs = client_kwargs

        # Lifecycle management
        self._lifecycle_task: asyncio.Task | None = None
        self._reload_event = asyncio.Event()
        self._ready_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._startup_waiter: asyncio.Future[None] | None = None

        # Session state
        self.session: ClientSession | None = None
        self.is_connected = False

        # Tool cache
        self._cached_tools = None

        # External callback invoked on each MCP progress notification.
        # Set by the agent layer to reset its watchdog timer.
        self.on_progress_callback = None

    async def _run_lifecycle(self) -> None:
        """Run MCP client lifecycle in a dedicated task."""
        while not self._stop_event.is_set():
            try:
                logger.debug(f"Connecting MCP client: {self.name}")

                # Enter context manager in THIS task
                async with AsyncExitStack() as stack:
                    # Select client based on transport
                    if self.transport == "streamable_http":
                        # Create httpx.AsyncClient with headers and timeout
                        timeout_seconds = (
                            self.timeout.total_seconds()
                            if isinstance(self.timeout, timedelta)
                            else self.timeout
                        )
                        sse_read_timeout_seconds = (
                            self.sse_read_timeout.total_seconds()
                            if isinstance(self.sse_read_timeout, timedelta)
                            else self.sse_read_timeout
                        )

                        # Configure httpx client with MCP-recommended timeouts
                        http_client = httpx.AsyncClient(
                            headers=self.headers or {},
                            timeout=httpx.Timeout(
                                connect=timeout_seconds,
                                read=sse_read_timeout_seconds,
                                write=timeout_seconds,
                                pool=timeout_seconds,
                            ),
                            **self.client_kwargs,
                        )

                        # Add http_client to exit stack for proper cleanup
                        await stack.enter_async_context(http_client)

                        context = await stack.enter_async_context(
                            streamable_http_client(
                                url=self.url,
                                http_client=http_client,
                            ),
                        )
                    else:
                        context = await stack.enter_async_context(
                            sse_client(
                                url=self.url,
                                headers=self.headers,
                                timeout=self.timeout,
                                sse_read_timeout=self.sse_read_timeout,
                                **self.client_kwargs,
                            ),
                        )

                    read_stream, write_stream = context[0], context[1]

                    # Initialize session
                    self.session = ClientSession(read_stream, write_stream)
                    await stack.enter_async_context(self.session)
                    await self.session.initialize()

                    # Mark as connected and signal ready
                    self.is_connected = True
                    self._ready_event.set()
                    if (
                        self._startup_waiter is not None
                        and not self._startup_waiter.done()
                    ):
                        self._startup_waiter.set_result(None)
                    logger.info(f"MCP client connected: {self.name}")

                    # Wait for reload or stop signal
                    while (
                        not self._reload_event.is_set()
                        and not self._stop_event.is_set()
                    ):
                        await asyncio.sleep(0.1)

                    # Clear state before exiting context
                    self.session = None
                    self.is_connected = False
                    self._cached_tools = None

                    if self._reload_event.is_set():
                        logger.info(f"Reloading MCP client: {self.name}")
                        self._reload_event.clear()
                        self._ready_event.clear()
                    else:
                        logger.info(f"Stopping MCP client: {self.name}")

                # Context manager exits cleanly in THIS task

            except Exception as e:
                startup_failed = (
                    self._startup_waiter is not None
                    and not self._startup_waiter.done()
                    and not self.is_connected
                )
                logger.error(
                    f"Error in MCP client lifecycle for {self.name}: {e}",
                    exc_info=True,
                )
                self.session = None
                self.is_connected = False
                self._cached_tools = None
                self._ready_event.clear()
                if startup_failed:
                    self._startup_waiter.set_exception(e)
                    break
                await asyncio.sleep(1)

        logger.info(f"MCP client lifecycle task exited: {self.name}")

    async def connect(self, timeout: float = 30.0) -> None:
        """Connect to MCP server.

        Args:
            timeout: Connection timeout in seconds

        Raises:
            RuntimeError: If already connected
            asyncio.TimeoutError: If connection times out
        """
        if self.is_connected:
            raise RuntimeError(
                f"MCP client '{self.name}' is already connected. "
                f"Call close() before connecting again.",
            )

        self._stop_event.clear()
        self._ready_event.clear()
        self._startup_waiter = asyncio.get_running_loop().create_future()
        self._lifecycle_task = asyncio.create_task(self._run_lifecycle())

        try:
            await asyncio.wait_for(
                asyncio.shield(self._startup_waiter),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.error(
                f"Timeout waiting for MCP client '{self.name}' to connect",
            )
            self._stop_event.set()
            await _finalize_lifecycle_task(self._lifecycle_task)
            self._lifecycle_task = None
            self.session = None
            self.is_connected = False
            self._cached_tools = None
            self._ready_event.clear()
            if self._startup_waiter and not self._startup_waiter.done():
                self._startup_waiter.cancel()
            self._startup_waiter = None
            raise
        except Exception:
            self._stop_event.set()
            await _finalize_lifecycle_task(self._lifecycle_task)
            self._lifecycle_task = None
            self.session = None
            self.is_connected = False
            self._cached_tools = None
            self._ready_event.clear()
            self._startup_waiter = None
            raise
        self._startup_waiter = None

    async def close(self, ignore_errors: bool = True) -> None:
        """Close MCP client and clean up resources.

        Args:
            ignore_errors: Whether to ignore errors during cleanup

        Raises:
            RuntimeError: If not connected (unless ignore_errors=True)
        """
        if not self.is_connected:
            if not ignore_errors:
                raise RuntimeError(
                    f"MCP client '{self.name}' is not connected. "
                    f"Call connect() before closing.",
                )
            return

        try:
            self._stop_event.set()
            if self._lifecycle_task:
                await self._lifecycle_task
                self._lifecycle_task = None
        except Exception as e:
            if not ignore_errors:
                raise
            logger.warning(
                f"Error closing MCP client '{self.name}': {e}",
            )

    async def list_tools(self, timeout: float = MCP_CALL_TIMEOUT):
        """Get all available tools from the server.

        Args:
            timeout: Maximum seconds to wait for the server response
                (default: ``MCP_CALL_TIMEOUT``).

        Returns:
            List of available MCP tools

        Raises:
            RuntimeError: If not connected
            asyncio.TimeoutError: If the call exceeds *timeout*
        """
        self._validate_connection()

        res = await _call_with_timeout(
            self.session.list_tools(),
            timeout=timeout,
            operation="list_tools",
            client_name=self.name,
        )
        self._cached_tools = res.tools
        return res.tools

    async def call_tool(
        self,
        name: str,
        arguments: dict | None = None,
        meta: dict[str, Any] | None = None,
    ):
        """Call a tool on the MCP server.

        Args:
            name: Tool name
            arguments: Tool arguments (optional)
            meta: Optional meta dict forwarded as _meta in JSON-RPC request
                (e.g. {"progressToken": "..."})

        Returns:
            Tool call result

        Raises:
            RuntimeError: If not connected
            asyncio.TimeoutError: If the call exceeds timeout
        """
        self._validate_connection()

        progress_event = asyncio.Event()
        progress_token = None

        if meta and "progressToken" in meta:
            progress_token = meta["progressToken"]

            async def _on_progress(_progress, _total, _message):
                progress_event.set()
                if self.on_progress_callback is not None:
                    self.on_progress_callback()

            # Inject into SDK's _progress_callbacks so _receive_loop
            # can dispatch progress notifications to our handler.
            # pylint: disable=protected-access
            self.session._progress_callbacks[progress_token] = _on_progress

        per_timeout = MCP_PER_NOTIFICATION_TIMEOUT
        max_total = MCP_MAX_TOTAL_TIMEOUT or None

        try:
            return await _call_with_timeout_refresh(
                self.session.call_tool(name, arguments or {}, meta=meta),
                per_notification_timeout=per_timeout,
                max_total_timeout=max_total,
                operation=f"call_tool({name})",
                client_name=self.name,
                progress_event=progress_event if progress_token else None,
                on_progress_callback=self.on_progress_callback,
            )
        finally:
            if progress_token:
                # Delay removal so _receive_loop can still dispatch
                # in-flight progress notifications that arrive after
                # the JSON-RPC response but before this finally runs.
                await asyncio.sleep(0.1)
                # pylint: disable=protected-access
                self.session._progress_callbacks.pop(progress_token, None)

    def _validate_connection(self) -> None:
        """Validate the connection to the MCP server.

        Raises:
            RuntimeError: If not connected or session not initialized
        """
        if not self.is_connected:
            raise RuntimeError(
                f"MCP client '{self.name}' is not connected. "
                f"Call connect() first.",
            )

        if not self.session:
            raise RuntimeError(
                f"MCP client '{self.name}' session is not initialized. "
                f"Call connect() first.",
            )
