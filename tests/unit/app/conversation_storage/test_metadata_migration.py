# -*- coding: utf-8 -*-
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
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


@pytest.mark.asyncio
async def test_metadata_preview_reports_legacy_filename_collision(tmp_path):
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
    _, manifest = _prepare(tmp_path, chats)
    data, digest = metadata.read_manifest(manifest, "test_schema")
    report = await metadata.migrate(None, data, digest, apply=False)
    assert report["status"] == "partial_success"
    assert "multiple Session identities" in report["failed"][0]["detail"]


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


@pytest.mark.asyncio
async def test_full_audit_reports_malformed_archive_and_continues(tmp_path):
    chat_id = str(uuid4())
    workspaces = []
    for source in ("bad", "healthy"):
        root = tmp_path / source
        root.mkdir()
        workspaces.append(
            {
                "scope": ["service", "tenant", source, "agent"],
                "root": str(root),
            },
        )
    root = tmp_path / "bad"
    (root / "chats.json").write_text(
        json.dumps(
            {
                "version": 1,
                "chats": [
                    {
                        "id": chat_id,
                        "session_id": "session",
                        "user_id": "user",
                        "channel": "console",
                    },
                ],
            },
        ),
    )
    archive = root / "dialog" / chat_id
    archive.mkdir(parents=True)
    (archive / "manifest.json").write_text('{"boundaries":[{}]}')
    manifest = tmp_path / "manifest.json"
    metadata.prepare(workspaces, "test_schema", manifest)
    data, digest = metadata.read_manifest(manifest, "test_schema")
    report = await metadata.migrate(
        None,
        data,
        digest,
        apply=False,
        full_audit=True,
    )
    assert report["status"] == "partial_success"
    assert report["validated"] == [("service", "tenant", "healthy")]
    assert report["failed"][0]["root"] == str(root)


@pytest.mark.asyncio
async def test_resume_rejects_missing_workspace_even_without_source_row(
    tmp_path,
):
    workspaces = [
        {
            "root": str(tmp_path / agent),
            "scope": ["service", "tenant", "source", agent],
        }
        for agent in ("a", "b")
    ]
    original_path = tmp_path / "original.json"
    metadata.prepare(workspaces, "test_schema", original_path)
    original = metadata.read_manifest(original_path, "test_schema")
    (tmp_path / "a").mkdir()
    repaired_path = tmp_path / "repaired.json"
    metadata.prepare(workspaces[:1], "test_schema", repaired_path)
    repaired = metadata.read_manifest(repaired_path, "test_schema")
    db = SimpleNamespace(
        fetch_one=AsyncMock(return_value=None),
        execute=AsyncMock(),
    )

    report = await metadata.migrate(
        db,
        *repaired,
        apply=True,
        resume_from=original,
    )

    assert report["failed"][0]["detail"] == (
        "resume manifest changes source workspace membership"
    )
    assert report["published"] == []
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_progress_requires_matching_database_binding_and_audit(tmp_path):
    root, path = _prepare(tmp_path, [])
    manifest, digest = metadata.read_manifest(path, "test_schema")
    item = manifest["workspaces"][0]
    config = SimpleNamespace(
        host="localhost",
        port=3306,
        database="test_schema",
    )
    progress = metadata.WorkspaceProgress(path, digest, config)
    progress.record(item, 0, full_audit=False)
    progress = metadata.WorkspaceProgress(path, digest, config)
    scope = WorkspaceScope.from_values(item["scope"])
    binding = {
        "agent_key": scope.sql_values[-1],
        "workspace_root": str(root.parent).encode(),
        "registry_digest": bytes.fromhex(item["registry_sha256"]),
        "imported_count": 1,
    }
    db = SimpleNamespace(fetch_all=AsyncMock(return_value=[binding]))

    async def completed(*, full_audit=False):
        return await metadata._completed_workspaces(
            db,
            scope.sql_values[:3],
            [item],
            progress,
            full_audit=full_audit,
        )

    assert not await completed()
    binding["imported_count"] = 0
    assert set(await completed()) == {scope.sql_values[-1]}
    assert not await completed(full_audit=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["read", "write"])
async def test_progress_io_failure_does_not_block_publication(
    tmp_path,
    monkeypatch,
    failure,
):
    warning = Mock()
    monkeypatch.setattr(metadata.logger, "warning", warning)
    _, path = _prepare(tmp_path, [])
    manifest, digest = metadata.read_manifest(path, "test_schema")
    config = SimpleNamespace(
        host="localhost",
        port=3306,
        database="test_schema",
    )
    if failure == "read":
        path.with_name(path.name + ".progress.json").mkdir()
    else:

        def fail_write(*_args):
            raise PermissionError("read-only directory")

        monkeypatch.setattr(metadata, "atomic_json", fail_write)
    progress = metadata.WorkspaceProgress(path, digest, config)
    db = SimpleNamespace(
        fetch_one=AsyncMock(return_value=None),
        execute=AsyncMock(return_value=1),
    )
    import_workspace = AsyncMock(return_value=0)
    monkeypatch.setattr(metadata, "_import_workspace", import_workspace)
    report = await metadata.migrate(
        db,
        manifest,
        digest,
        apply=True,
        progress=progress,
    )

    import_workspace.assert_awaited_once()
    assert report["status"] == "ready"
    assert report["published"] == [("service", "tenant", "source")]
    assert report["failed"] == []
    assert any(
        call.args[0].startswith(f"Cannot {failure} migration progress")
        for call in warning.call_args_list
    )
