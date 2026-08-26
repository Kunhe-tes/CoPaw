# -*- coding: utf-8 -*-
"""Request-lazy MCP client backed by a short-lived discovery cache."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _DiscoveryEntry:
    tools: tuple[Any, ...]
    expires_at: float


class MCPToolDiscoveryCache:
    """Process-local cache for MCP tool schemas, never live sessions."""

    def __init__(
        self,
        ttl_seconds: float = 300.0,
        capacity: int = 512,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._capacity = capacity
        self._clock = clock
        self._entries: OrderedDict[str, _DiscoveryEntry] = OrderedDict()
        self._refreshes: dict[str, asyncio.Task[tuple[Any, ...]]] = {}

    async def get_or_discover(
        self,
        key: str,
        discover: Callable[[], Awaitable[list[Any]]],
    ) -> list[Any]:
        cached = self._entries.get(key)
        if cached is not None and cached.expires_at > self._clock():
            self._entries.move_to_end(key)
            return list(cached.tools)
        if cached is not None:
            self._entries.pop(key, None)

        task = self._refreshes.get(key)
        if task is None:
            task = asyncio.create_task(self._discover(key, discover))
            self._refreshes[key] = task
        return list(await asyncio.shield(task))

    async def put(self, key: str, tools: list[Any]) -> None:
        self._entries.pop(key, None)
        self._entries[key] = _DiscoveryEntry(
            tools=tuple(tools),
            expires_at=self._clock() + self._ttl_seconds,
        )
        while len(self._entries) > self._capacity:
            self._entries.popitem(last=False)

    async def _discover(
        self,
        key: str,
        discover: Callable[[], Awaitable[list[Any]]],
    ) -> tuple[Any, ...]:
        try:
            tools = await discover()
            await self.put(key, tools)
            return tuple(tools)
        finally:
            self._refreshes.pop(key, None)


class LazyMCPClient:
    """Expose cached MCP tools while opening a client only for real calls."""

    def __init__(
        self,
        *,
        name: str,
        discovery_key: str,
        create_client: Callable[[], Awaitable[Any]],
        discovery_cache: MCPToolDiscoveryCache,
        connect_timeout: float = 30.0,
        frozen_tools: list[dict[str, Any]] | None = None,
    ) -> None:
        self.name = name
        self._discovery_key = discovery_key
        self._create_client = create_client
        self._discovery_cache = discovery_cache
        self._connect_timeout = connect_timeout
        self._frozen_tools = _deserialize_frozen_tools(frozen_tools)
        self.on_progress_callback = None

    async def list_tools(self) -> list[Any]:
        if self._frozen_tools is not None:
            return list(self._frozen_tools)
        return await self._discovery_cache.get_or_discover(
            self._discovery_key,
            self._discover_tools,
        )

    async def call_tool(
        self,
        name: str,
        arguments: dict | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Any:
        client = await self._create_client()
        try:
            await client.connect(timeout=self._connect_timeout)
            return await client.call_tool(name, arguments or {}, meta=meta)
        except Exception as exc:
            logger.warning(
                "MCP lazy call failed: client=%s tool=%s error_type=%s",
                self.name,
                name,
                type(exc).__name__,
            )
            raise
        finally:
            await self._close_client(client)

    async def close(self) -> None:
        """Keep the request cleanup contract; lazy clients own no session."""

    def get_tool_function(self, tool: Any):
        """Build an AgentScope-compatible streaming callable for *tool*."""
        tool_name = tool.name

        async def _call(**kwargs: Any):
            client = await self._create_client()
            try:
                client.on_progress_callback = self.on_progress_callback
                await client.connect(timeout=self._connect_timeout)
                callable_tool = await client.get_callable_function(
                    tool_name,
                    wrap_tool_result=True,
                )
                callable_tool.on_progress_callback = self.on_progress_callback
                async for response in callable_tool(**kwargs):
                    yield response
            except Exception as exc:
                logger.warning(
                    "MCP lazy tool failed: client=%s tool=%s error_type=%s",
                    self.name,
                    tool_name,
                    type(exc).__name__,
                )
                raise
            finally:
                await self._close_client(client)

        _call.__name__ = tool_name
        return _call

    async def _discover_tools(self) -> list[Any]:
        client = await self._create_client()
        try:
            await client.connect(timeout=self._connect_timeout)
            return await client.list_tools()
        finally:
            await self._close_client(client)

    async def _close_client(self, client: Any) -> None:
        """Close a temporary client without hiding an active call failure."""
        try:
            await client.close()
        except asyncio.CancelledError:
            raise
        except Exception as error:  # pylint: disable=broad-except
            logger.warning(
                "MCP lazy close failed: client=%s error_type=%s",
                self.name,
                type(error).__name__,
            )


def _deserialize_frozen_tools(
    tools: list[dict[str, Any]] | None,
) -> tuple[Any, ...] | None:
    if tools is None:
        return None
    result: list[Any] = []
    for item in tools:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        result.append(
            SimpleNamespace(
                name=name,
                description=str(item.get("description") or ""),
                inputSchema=(
                    dict(item.get("inputSchema"))
                    if isinstance(item.get("inputSchema"), dict)
                    else {}
                ),
            ),
        )
    return tuple(result)


def mcp_tool_json_schema(tool: Any) -> dict[str, Any]:
    """Build the AgentScope function schema from an MCP tool descriptor."""
    input_schema = getattr(tool, "inputSchema", {}) or {}
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": getattr(tool, "description", "") or "",
            "parameters": input_schema,
        },
    }


_DEFAULT_DISCOVERY_CACHE = MCPToolDiscoveryCache()


def get_mcp_tool_discovery_cache() -> MCPToolDiscoveryCache:
    """Return the process-local cache used by request-lazy MCP clients."""
    return _DEFAULT_DISCOVERY_CACHE
