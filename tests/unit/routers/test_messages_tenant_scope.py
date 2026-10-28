# -*- coding: utf-8 -*-
"""Messages router scope-aware runtime lookup tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.app.routers.messages import SendMessageRequest, send_message
from swe.config.context import encode_scope_id


@pytest.mark.asyncio
async def test_send_message_prefers_request_scope_id() -> None:
    channel_manager = SimpleNamespace(send_text=AsyncMock(return_value=None))
    workspace = SimpleNamespace(channel_manager=channel_manager)
    manager = SimpleNamespace(get_agent=AsyncMock(return_value=workspace))
    http_request = SimpleNamespace(
        state=SimpleNamespace(
            tenant_id="tenant-a",
            source_id="source-a",
            scope_id=encode_scope_id("tenant-a", "source-a"),
        ),
        app=SimpleNamespace(
            state=SimpleNamespace(multi_agent_manager=manager),
        ),
    )

    response = await send_message(
        SendMessageRequest(
            channel="console",
            target_user="user-a",
            target_session="session-a",
            text="hello",
        ),
        http_request,
        x_agent_id="agent-a",
    )

    assert response.success is True
    manager.get_agent.assert_awaited_once_with(
        "agent-a",
        tenant_id=encode_scope_id("tenant-a", "source-a"),
    )
    channel_manager.send_text.assert_awaited_once()
