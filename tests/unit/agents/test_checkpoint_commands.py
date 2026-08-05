# -*- coding: utf-8 -*-
"""Context Epoch lifecycle coverage for chat commands."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.agents.command_handler import CommandHandler


def _handler() -> tuple[CommandHandler, SimpleNamespace]:
    manager = SimpleNamespace(
        reset_context_epoch=AsyncMock(),
        add_async_summary_task=lambda **_kwargs: None,
    )
    handler = object.__new__(CommandHandler)
    handler.memory_manager = manager
    handler._enable_memory_manager = True
    handler._request_context = {"chat_id": "chat-1"}
    handler.memory = SimpleNamespace(
        clear_content=lambda: None,
        clear_compressed_summary=lambda: None,
    )
    handler._make_system_msg = AsyncMock(return_value=SimpleNamespace())
    return handler, manager


@pytest.mark.asyncio
async def test_new_resets_context_epoch() -> None:
    handler, manager = _handler()

    await handler._process_new([])

    manager.reset_context_epoch.assert_awaited_once_with(
        chat_id="chat-1",
        reason="new",
    )


@pytest.mark.asyncio
async def test_clear_resets_context_epoch() -> None:
    handler, manager = _handler()

    await handler._process_clear([])

    manager.reset_context_epoch.assert_awaited_once_with(
        chat_id="chat-1",
        reason="clear",
    )
