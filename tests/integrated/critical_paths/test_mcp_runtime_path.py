# -*- coding: utf-8 -*-
"""Critical-path checks for MCP connection and tool lifecycle."""

from __future__ import annotations

import pytest

from swe.app.mcp.stateful_client import HttpStatefulClient


@pytest.mark.asyncio
async def test_http_stateful_client_connects_lists_and_calls_loopback_mcp(
    loopback_mcp_server,
) -> None:
    client = HttpStatefulClient(
        name="critical",
        transport="streamable_http",
        url=loopback_mcp_server.url,
        headers={
            loopback_mcp_server.required_header_name: (
                loopback_mcp_server.required_header_value
            ),
        },
        timeout=5,
        sse_read_timeout=5,
    )

    await client.connect(timeout=5)
    try:
        tools = await client.list_tools(timeout=5)
        assert "echo" in [tool.name for tool in tools]

        result = await client.call_tool("echo", {"text": "hello"})
        assert result.isError is False
        assert result.content[0].text == "echo:hello"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_http_stateful_client_missing_required_header_is_availability_failure(
    loopback_mcp_server,
) -> None:
    client = HttpStatefulClient(
        name="critical",
        transport="streamable_http",
        url=loopback_mcp_server.url,
        headers={},
        timeout=5,
        sse_read_timeout=5,
    )

    with pytest.raises(Exception):
        await client.connect(timeout=5)
    await client.close()
