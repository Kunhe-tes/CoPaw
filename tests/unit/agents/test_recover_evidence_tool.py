# -*- coding: utf-8 -*-
"""Tests for request-bound Chat checkpoint evidence recovery."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.agents.tools.recover_evidence import create_recover_evidence_tool


@pytest.mark.asyncio
async def test_recovery_uses_bound_chat_epoch_and_caps_limit() -> None:
    manager = SimpleNamespace(recover_evidence=AsyncMock(return_value=[]))
    tool = create_recover_evidence_tool(
        manager,
        chat_id="7cf02fc9-1c4e-4531-b81d-6513cbfda154",
        epoch=2,
    )

    response = await tool(
        refs=["archive:known"],
        query="stack trace",
        kinds=["tool"],
        time_range="today",
        limit=99,
    )

    manager.recover_evidence.assert_awaited_once_with(
        chat_id="7cf02fc9-1c4e-4531-b81d-6513cbfda154",
        epoch=2,
        refs=["archive:known"],
        query="stack trace",
        kinds=["tool"],
        time_range="today",
        limit=10,
    )
    assert response.content[0]["text"] == "No matching evidence."


@pytest.mark.asyncio
async def test_recovery_does_not_expose_internal_exception_details() -> None:
    manager = SimpleNamespace(
        recover_evidence=AsyncMock(
            side_effect=RuntimeError("/private/archive/chat-1.jsonl"),
        ),
    )
    tool = create_recover_evidence_tool(
        manager,
        chat_id="7cf02fc9-1c4e-4531-b81d-6513cbfda154",
        epoch=2,
    )

    response = await tool(refs=["message:known"])

    assert response.content[0]["text"] == "Evidence recovery is unavailable."
