# -*- coding: utf-8 -*-
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from swe.app.conversation_storage.migration import metadata
from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.conversation_storage.metadata_repository import (
    MySQLMetadataRepository,
    session_filename,
)
from swe.app.runner.models import ChatsFile


@pytest.mark.asyncio
async def test_import_batch_uses_bulk_sql_and_preserves_registry_order():
    @asynccontextmanager
    async def transaction():
        yield db

    scope = WorkspaceScope("tenant", "source", "agent", service_unit_id="svc")
    root, digest = b"/nas/workspace", bytes(32)
    filename = session_filename("session", "user").encode()
    registry = ChatsFile.model_validate(
        {
            "chats": [
                {
                    "id": str(uuid4()),
                    "user_id": "user",
                    "channel": "console",
                    "session_id": "session",
                }
                for _ in range(102)
            ],
        },
    )
    inserted = []

    async def insert_prepared(template, rows):
        inserted.append((template, list(rows)))

    db = SimpleNamespace(
        transaction=transaction,
        fetch_one=AsyncMock(
            side_effect=[
                {"workspace_root": root},
                {"published": 0},
                {
                    "workspace_root": root,
                    "registry_digest": digest,
                    "imported_count": 2,
                },
                None,
                {"high": 5},
            ],
        ),
        fetch_all=AsyncMock(
            return_value=[
                {
                    "id": 9,
                    "user_key": b"user",
                    "channel_key": b"console",
                    "external_session_key": b"session",
                    "nas_filename": filename,
                },
            ],
        ),
        insert_prepared=insert_prepared,
        execute=AsyncMock(),
    )
    repo = MySQLMetadataRepository(db, scope, importing=True)
    assert await metadata._import_batch(repo, registry, root, digest)
    assert db.fetch_one.await_count == 5
    db.fetch_all.assert_awaited_once()
    db.execute.assert_awaited_once()
    assert db.execute.await_args.args[1] == (102, *scope.sql_values)
    assert len(inserted) == 2
    session_rows = inserted[0][1]
    assert len(session_rows) == 1
    assert session_rows[0][:-2] == (
        *scope.sql_values,
        b"user",
        b"console",
        b"session",
        filename,
    )
    assert session_rows[0][-2] == session_rows[0][-1]
    assert [row[:4] for row in inserted[1][1]] == [
        (9, chat.id.encode(), b"session", order)
        for order, chat in enumerate(registry.chats[2:], 6)
    ]


def _prepare(tmp_path, chats):
    root = tmp_path / "workspace"
    root.mkdir()
    registry = root / "chats.json"
    registry.write_text(json.dumps({"version": 1, "chats": chats}))
    manifest = tmp_path / "migration.json"
    metadata.prepare(
        [
            {
                "root": str(root),
                "scope": ["service", "tenant", "source", "agent"],
            },
        ],
        "test_schema",
        manifest,
    )
    return registry, manifest


@pytest.mark.asyncio
async def test_metadata_preview_is_read_only_and_checks_frozen_registry(
    tmp_path,
):
    registry, manifest = _prepare(tmp_path, [])
    data, digest = metadata.read_manifest(manifest, "test_schema")
    result = await metadata.migrate(None, data, digest, apply=False)
    assert result["status"] == "preview"
    assert list(registry.parent.iterdir()) == [registry]

    registry.write_text('{"version":1,"chats":[]}')
    result = await metadata.migrate(None, data, digest, apply=False)
    assert result["status"] == "partial_success"
    assert "changed after preparation" in result["failed"][0]["detail"]


def test_metadata_prepare_rejects_legacy_filename_collision(tmp_path):
    chats = [
        {
            "id": str(uuid4()),
            "user_id": "u",
            "channel": "console",
            "session_id": "x:y",
        },
        {
            "id": str(uuid4()),
            "user_id": "u",
            "channel": "console",
            "session_id": "x--y",
        },
    ]
    with pytest.raises(ValueError, match="multiple Session identities"):
        _prepare(tmp_path, chats)
    assert not (tmp_path / "migration.json").exists()


@pytest.mark.asyncio
async def test_changed_registry_does_not_reserve_source(tmp_path):
    registry, manifest = _prepare(tmp_path, [])
    data, digest = metadata.read_manifest(manifest, "test_schema")
    registry.write_text('{"version":1,"chats":[]}')
    database = SimpleNamespace(
        fetch_one=AsyncMock(return_value=None),
        execute=AsyncMock(),
    )
    result = await metadata.migrate(database, data, digest, apply=True)
    assert result["status"] == "partial_success"
    assert "changed after preparation" in result["failed"][0]["detail"]
    database.execute.assert_not_awaited()
