# -*- coding: utf-8 -*-
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.app.conversation_storage.errors import ConflictError
from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.conversation_storage.metadata_repository import (
    MySQLMetadataRepository,
    session_filename,
)


@pytest.mark.asyncio
async def test_session_candidate_lookup_treats_oversized_id_as_missing():
    db = SimpleNamespace(fetch_all=AsyncMock())
    repo = MySQLMetadataRepository(
        db,
        WorkspaceScope("t", "s", "a", service_unit_id="svc"),
    )
    assert (
        await repo.filter_chats_by_session("会" * 342, "user", "console") == []
    )
    db.fetch_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_session_path_uses_only_a_published_lookup():
    filename = session_filename("session", "user").encode()
    db = SimpleNamespace(
        fetch_one=AsyncMock(return_value={"nas_filename": filename}),
    )
    repo = MySQLMetadataRepository(
        db,
        WorkspaceScope("t", "s", "a", service_unit_id="svc"),
    )
    repo.claim_session = AsyncMock()
    await repo.ensure_session_path("session", "user", "console")
    db.fetch_one.assert_awaited_once()
    statement, _ = db.fetch_one.await_args.args
    assert "published=1" in statement
    assert "FOR UPDATE" not in statement
    repo.claim_session.assert_not_awaited()

    db.fetch_one.return_value = {"nas_filename": b"other.json"}
    with pytest.raises(ConflictError, match="filename"):
        await repo.ensure_session_path("session", "user", "console")
    repo.claim_session.assert_not_awaited()

    db.fetch_one.return_value = None
    await repo.ensure_session_path("session", "user", "console")
    repo.claim_session.assert_awaited_once_with("session", "user", "console")


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
