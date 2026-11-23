# -*- coding: utf-8 -*-
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.app.conversation_storage.errors import ConflictError
from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.conversation_storage.metadata_repository import (
    MySQLMetadataRepository,
)


@pytest.mark.asyncio
async def test_delete_checks_locked_chat_and_clears_draft():
    @asynccontextmanager
    async def transaction():
        yield

    db = SimpleNamespace(
        transaction=transaction,
        execute=AsyncMock(return_value=1),
    )
    repo = MySQLMetadataRepository(
        db,
        WorkspaceScope("t", "s", "a", service_unit_id="svc"),
    )
    repo._assert_writes_allowed = AsyncMock()
    repo._locked_chat = AsyncMock(
        return_value=({}, {"id": 8, "session_id": 4}),
    )
    repo._spec = lambda row: "authorized"
    assert await repo.delete_chats(
        ["chat"],
        expected_chats={"chat": "authorized"},
    )
    assert db.execute.await_count == 2
    assert db.execute.await_args_list[1].args[1] == (4, 8)

    db.execute.reset_mock()
    with pytest.raises(ConflictError, match="changed since authorization"):
        await repo.delete_chats(["chat"], expected_chats={"chat": "stale"})
    db.execute.assert_not_awaited()
