# -*- coding: utf-8 -*-
"""Regression tests for request-lazy MCP clients."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.agents.react_agent import SWEAgent
from swe.app.mcp.lazy_client import (
    LazyMCPClient,
    MCPToolDiscoveryCache,
    mcp_tool_json_schema,
)


def _tool(name: str = "weather") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        description="Return the weather.",
        inputSchema={"type": "object", "properties": {}},
    )


@pytest.mark.asyncio
async def test_lazy_client_reuses_discovery_without_connecting_again():
    cache = MCPToolDiscoveryCache(ttl_seconds=60)
    discovery_client = SimpleNamespace(
        connect=AsyncMock(),
        list_tools=AsyncMock(return_value=[_tool()]),
        close=AsyncMock(),
    )
    create_client = AsyncMock(return_value=discovery_client)
    client = LazyMCPClient(
        name="weather-mcp",
        discovery_key="tenant:user:weather:v1",
        create_client=create_client,
        discovery_cache=cache,
    )

    assert [tool.name for tool in await client.list_tools()] == ["weather"]
    assert [tool.name for tool in await client.list_tools()] == ["weather"]

    assert create_client.await_count == 1
    discovery_client.connect.assert_awaited_once()
    discovery_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_lazy_client_connects_only_when_the_tool_is_called():
    cache = MCPToolDiscoveryCache(ttl_seconds=60)
    await cache.put("tenant:user:weather:v1", [_tool()])
    call_client = SimpleNamespace(
        connect=AsyncMock(),
        call_tool=AsyncMock(
            return_value=SimpleNamespace(
                content=[{"type": "text", "text": "sunny"}],
                meta={"source": "weather"},
                isError=False,
            ),
        ),
        close=AsyncMock(),
    )
    create_client = AsyncMock(return_value=call_client)
    client = LazyMCPClient(
        name="weather-mcp",
        discovery_key="tenant:user:weather:v1",
        create_client=create_client,
        discovery_cache=cache,
    )

    assert [tool.name for tool in await client.list_tools()] == ["weather"]
    assert create_client.await_count == 0

    result = await client.call_tool("weather", {"city": "Shanghai"})

    assert result.content == [{"type": "text", "text": "sunny"}]
    call_client.connect.assert_awaited_once()
    call_client.call_tool.assert_awaited_once_with(
        "weather",
        {"city": "Shanghai"},
        meta=None,
    )
    call_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_lazy_call_preserves_tool_error_when_close_also_fails():
    cache = MCPToolDiscoveryCache(ttl_seconds=60)
    call_client = SimpleNamespace(
        connect=AsyncMock(),
        call_tool=AsyncMock(side_effect=RuntimeError("tool failed")),
        close=AsyncMock(side_effect=RuntimeError("close failed")),
    )
    client = LazyMCPClient(
        name="weather-mcp",
        discovery_key="tenant:user:weather:v1",
        create_client=AsyncMock(return_value=call_client),
        discovery_cache=cache,
    )

    with pytest.raises(RuntimeError, match="tool failed"):
        await client.call_tool("weather")

    call_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_lazy_call_returns_success_when_close_fails():
    cache = MCPToolDiscoveryCache(ttl_seconds=60)
    call_client = SimpleNamespace(
        connect=AsyncMock(),
        call_tool=AsyncMock(return_value=SimpleNamespace(content=[])),
        close=AsyncMock(side_effect=RuntimeError("close failed")),
    )
    client = LazyMCPClient(
        name="weather-mcp",
        discovery_key="tenant:user:weather:v1",
        create_client=AsyncMock(return_value=call_client),
        discovery_cache=cache,
    )

    result = await client.call_tool("weather")

    assert result.content == []
    call_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_agent_registers_cached_lazy_tool_without_connecting_until_call():
    cache = MCPToolDiscoveryCache(ttl_seconds=60)
    tool = _tool()
    await cache.put("tenant:user:weather:v1", [tool])

    class CallableTool:
        on_progress_callback = None

        async def __call__(self, **_kwargs):
            yield SimpleNamespace(
                content=[{"type": "text", "text": "sunny"}],
            )

    callable_tool = CallableTool()
    call_client = SimpleNamespace(
        connect=AsyncMock(),
        close=AsyncMock(),
        get_callable_function=AsyncMock(return_value=callable_tool),
    )
    create_client = AsyncMock(return_value=call_client)
    lazy_client = LazyMCPClient(
        name="weather-mcp",
        discovery_key="tenant:user:weather:v1",
        create_client=create_client,
        discovery_cache=cache,
    )

    class Toolkit:
        def __init__(self):
            self.tools: dict[str, SimpleNamespace] = {}

        def register_tool_function(self, tool_func, **kwargs):
            self.tools[kwargs["func_name"]] = SimpleNamespace(
                original_func=tool_func,
                mcp_name=None,
            )

    agent = object.__new__(SWEAgent)
    agent._mcp_clients = [lazy_client]
    agent._source_tool_versions = ()
    agent._agent_config = SimpleNamespace(
        tools=SimpleNamespace(builtin_tools={}),
    )
    agent.toolkit = Toolkit()
    agent._reset_watchdog = lambda: None

    await agent.register_mcp_clients()

    assert create_client.await_count == 0
    assert agent.toolkit.tools["weather"].mcp_name == "weather-mcp"

    response_stream = await agent.toolkit.tools["weather"].original_func()
    responses = [response async for response in response_stream]

    assert responses[0].content == [{"type": "text", "text": "sunny"}]
    call_client.connect.assert_awaited_once()
    call_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_lazy_clients_share_one_inflight_discovery_for_the_same_scope():
    cache = MCPToolDiscoveryCache(ttl_seconds=60)
    discovery_started = asyncio.Event()
    allow_discovery = asyncio.Event()

    async def discover():
        discovery_started.set()
        await allow_discovery.wait()
        return [_tool()]

    first = asyncio.create_task(
        cache.get_or_discover("tenant:user:weather:v1", discover),
    )
    await discovery_started.wait()
    second = asyncio.create_task(
        cache.get_or_discover("tenant:user:weather:v1", discover),
    )
    allow_discovery.set()

    first_tools, second_tools = await asyncio.gather(first, second)

    assert [tool.name for tool in first_tools] == ["weather"]
    assert [tool.name for tool in second_tools] == ["weather"]


@pytest.mark.asyncio
async def test_discovery_cache_evicts_oldest_entry_at_capacity():
    cache = MCPToolDiscoveryCache(ttl_seconds=60, capacity=1)
    await cache.put("first", [_tool("first")])
    await cache.put("second", [_tool("second")])
    discover_first = AsyncMock(return_value=[_tool("first")])

    assert [
        tool.name
        for tool in await cache.get_or_discover("second", AsyncMock())
    ] == [
        "second",
    ]
    assert [
        tool.name
        for tool in await cache.get_or_discover("first", discover_first)
    ] == ["first"]
    discover_first.assert_awaited_once()


def test_mcp_tool_json_schema_preserves_complete_input_schema():
    tool = SimpleNamespace(
        name="search",
        description="Search indexed documents.",
        inputSchema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    )

    schema = mcp_tool_json_schema(tool)

    assert schema["function"]["parameters"] == tool.inputSchema
