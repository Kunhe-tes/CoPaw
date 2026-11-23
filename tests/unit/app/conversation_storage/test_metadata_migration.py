# -*- coding: utf-8 -*-
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from swe.app.conversation_storage.migration import metadata


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
