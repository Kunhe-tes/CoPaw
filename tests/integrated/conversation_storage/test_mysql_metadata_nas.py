# -*- coding: utf-8 -*-
import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agentscope.message import Msg
from click.testing import CliRunner

from swe.app.conversation_storage import runtime
from swe.agents.memory.conversation_archive import ConversationArchiveStore
from swe.app.conversation_storage.errors import ConflictError
from swe.app.conversation_storage.tenant_admission import TenantNotPublished
from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.conversation_storage.migration import metadata
from swe.app.runner.models import ChatSpec
from swe.app.runner.session import SafeJSONSession
from swe.app.workspace.service_factories import create_chat_service
from swe.cli.conversation_storage_cmd import conversation_storage_group
from swe.config.context import encode_scope_id
from tests.integrated.conversation_storage.conftest import (
    SQL_ROOT,
    apply_sql_script,
)


@pytest.mark.asyncio
# pylint: disable-next=too-many-statements
async def test_metadata_cutover_keeps_nas_as_the_online_content_store(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    db = conversation_test_database
    await apply_sql_script(db, SQL_ROOT / "conversation_mysql_metadata.sql")
    await apply_sql_script(
        db,
        SQL_ROOT / "conversation_metadata_performance.sql",
    )
    scope = WorkspaceScope(
        "tenant",
        "source",
        "agent",
        service_unit_id="service",
    )
    root = tmp_path / "workspace"
    root.mkdir()
    state_dir = root / "sessions"
    state_dir.mkdir()
    original = state_dir / "user_session.json"
    original.write_text('{"schema_version":2,"revision":1,"example":"before"}')
    before = original.read_bytes()
    specs = [
        ChatSpec(
            id=str(uuid4()),
            session_id="session",
            user_id="user",
            channel="console",
            meta={
                "task_job_id": "task",
                "scenario_preset_snapshot": {"version": 1, "enabled": False},
            },
        )
        for _ in range(2)
    ]
    registry = root / "chats.json"
    registry.write_text(
        json.dumps(
            {
                "version": 1,
                "chats": [spec.model_dump(mode="json") for spec in specs],
            },
        ),
    )
    manifest = tmp_path / "manifest.json"
    metadata.prepare(
        [{"scope": scope.values, "root": str(root)}],
        db.config.database,
        manifest,
    )
    data, digest = metadata.read_manifest(manifest, db.config.database)
    archive = ConversationArchiveStore(root / "dialog")
    await archive.commit(specs[0].id, [Msg("user", "old archive", "user")])
    snapshot = {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(metadata, "BATCH_SIZE", 1)
    monkeypatch.setattr(metadata, "VERIFY_PAGE_SIZE", 1)
    batch = metadata._import_batch

    async def interrupt(repo, registry, root_key, registry_digest):
        assert await batch(repo, registry, root_key, registry_digest)
        raise RuntimeError("interrupted after a committed batch")

    monkeypatch.setattr(metadata, "_import_batch", interrupt)
    with pytest.raises(RuntimeError, match="committed batch"):
        await metadata.migrate(db, data, digest, apply=True)
    marker = await db.fetch_one(
        "SELECT imported_count FROM swe_conversation_metadata_workspaces",
    )
    assert marker["imported_count"] == 1

    monkeypatch.setenv(runtime.AUTHORITY_ENV, runtime.METADATA_AUTHORITY)
    monkeypatch.setenv("CMB_CAAS_SERVICEUNITID", scope.service_unit_id)
    await runtime.configure_runtime(db)
    try:
        runner = SimpleNamespace(
            set_chat_manager=lambda manager: setattr(
                runner,
                "chat_manager",
                manager,
            ),
        )
        workspace = SimpleNamespace(
            workspace_dir=root,
            tenant_id=encode_scope_id(scope.tenant_id, scope.source_id),
            source_id=scope.source_id,
            agent_id=scope.agent_id,
            _service_manager=SimpleNamespace(services={"runner": runner}),
        )
        with pytest.raises(TenantNotPublished):
            await runtime.require_tenant_published(workspace.tenant_id)
        with pytest.raises(TenantNotPublished):
            await runtime.workspace_metadata_repository(workspace)
        monkeypatch.setattr(metadata, "_import_batch", batch)
        for _ in range(2):
            assert (
                await metadata.migrate(
                    db,
                    data,
                    digest,
                    apply=True,
                    full_audit=True,
                )
            )["status"] == "ready"
        assert {
            path.relative_to(root): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        } == snapshot

        await runtime.require_tenant_published(workspace.tenant_id)
        await create_chat_service(workspace, None)
        manager = runner.chat_manager
        repo = manager._repo
        assert await repo.list_chats() == specs
        assert (await repo.list_summaries()).items[0].display_metadata == {
            "task_job_id": "task",
        }
        async with db.transaction():
            await db.fetch_one(
                "SELECT workspace_root FROM swe_conversation_metadata_workspaces "
                "WHERE service_unit_key=%s AND tenant_key=%s AND source_key=%s AND agent_key=%s FOR UPDATE",
                scope.sql_values,
            )
            await asyncio.wait_for(
                db.create_independent_task(
                    repo.ensure_session_path("session", "user", "console"),
                ),
                timeout=3,
            )
        with pytest.raises(ConflictError, match="filename"):
            await repo.ensure_session_path("session", "user", "zhaohu")
        session = SafeJSONSession(str(state_dir))
        async with session.execution("session", "user") as state:
            assert state.state["example"] == "before"
            await state.commit_state({**state.state, "example": "after"})
        assert json.loads(original.read_text())["example"] == "after"

        updated = specs[0].model_copy(update={"name": "renamed"})
        assert (
            await repo.update_chat_if_exists(updated, expected_chat=specs[0])
            == updated
        )
        assert (await manager._archive_store.read_page(specs[0].id)).messages[
            0
        ].get_text_content() == "old archive"
        await manager._archive_store.commit(
            specs[1].id,
            [Msg("user", "delete me", "user")],
        )
        assert await manager.delete_chats(
            [specs[1].id],
            expected_chats={specs[1].id: specs[1]},
        )
        assert not await repo.pending_resource_cleanup()
        assert not (
            await manager._archive_store.read_page(specs[1].id)
        ).messages
        assert original.is_file()
        assert await manager._archive_store.read_page(specs[0].id)
        output = tmp_path / "export"
        await metadata.export(db, data, digest, output)
        rows = json.loads((output / "0" / "chats.json").read_text())["chats"]
        assert [(row["id"], row["name"]) for row in rows] == [
            (updated.id, "renamed"),
        ]
        assert set(root.iterdir()) == {state_dir, registry, root / "dialog"}
    finally:
        runtime.reset_runtime()


@pytest.mark.asyncio
async def test_bulk_import_rolls_back_new_sessions_on_filename_conflict(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    db = conversation_test_database
    await apply_sql_script(db, SQL_ROOT / "conversation_mysql_metadata.sql")
    scope = WorkspaceScope("tenant", "source", "agent", service_unit_id="svc")
    root = tmp_path / "workspace"
    root.mkdir()
    specs = [
        ChatSpec(
            id=str(uuid4()),
            session_id=session_id,
            user_id="user",
            channel="console",
        )
        for session_id in ("new", "taken")
    ]
    (root / "chats.json").write_text(
        json.dumps(
            {
                "version": 1,
                "chats": [spec.model_dump(mode="json") for spec in specs],
            },
        ),
    )
    manifest = tmp_path / "manifest.json"
    metadata.prepare(
        [{"scope": scope.values, "root": str(root)}],
        db.config.database,
        manifest,
    )
    data, digest = metadata.read_manifest(manifest, db.config.database)
    batch = metadata._import_batch

    async def seed_conflicting_owner(
        repo,
        registry,
        root_key,
        registry_digest,
    ):
        await repo.claim_session("taken", "user", "zhaohu")
        return await batch(repo, registry, root_key, registry_digest)

    monkeypatch.setattr(metadata, "_import_batch", seed_conflicting_owner)
    result = await metadata.migrate(db, data, digest, apply=True)
    assert result["status"] == "partial_success"
    assert (
        "filename belongs to another identity" in result["failed"][0]["detail"]
    )
    assert await db.fetch_all(
        "SELECT external_session_key FROM swe_conversation_sessions",
    ) == [{"external_session_key": b"taken"}]
    assert not await db.fetch_one("SELECT id FROM swe_conversation_chats")
    assert await db.fetch_one(
        "SELECT imported_count FROM swe_conversation_metadata_workspaces",
    ) == {"imported_count": 0}
    assert await db.fetch_one(
        "SELECT published FROM swe_conversation_metadata_sources",
    ) == {"published": 0}


@pytest.mark.asyncio
async def test_metadata_cli_uses_a_published_sql_registry(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    db = conversation_test_database
    await apply_sql_script(db, SQL_ROOT / "conversation_mysql_metadata.sql")
    await apply_sql_script(
        db,
        SQL_ROOT / "conversation_metadata_performance.sql",
    )
    from swe.database import config

    monkeypatch.setattr(config, "get_database_config", lambda: db.config)
    root = tmp_path / "workspace"
    root.mkdir()
    spec = ChatSpec(id=str(uuid4()), session_id="legacy", user_id="user")
    original = {"version": 1, "chats": [spec.model_dump(mode="json")]}
    raw = json.dumps(original)
    (root / "chats.json").write_text(raw)
    mapping = tmp_path / "workspaces.json"
    mapping.write_text(
        json.dumps(
            [
                {
                    "root": str(root),
                    "scope": ["service", "tenant", "source", "agent"],
                },
            ],
        ),
    )
    manifest = str(tmp_path / "manifest.json")

    async def invoke(*args):
        result = await asyncio.to_thread(
            CliRunner().invoke,
            conversation_storage_group,
            list(args),
        )
        assert result.exit_code == 0, result.output
        return json.loads(result.output)

    assert (
        await invoke(
            "prepare",
            "--mode",
            "mysql-metadata",
            "--workspaces",
            str(mapping),
            "--manifest",
            manifest,
        )
    )["status"] == "prepared"
    assert (await invoke("migrate", "--manifest", manifest))[
        "status"
    ] == "preview"
    assert (
        await invoke(
            "migrate",
            "--manifest",
            manifest,
            "--apply",
            "--full-audit",
        )
    )["status"] == "ready"
    dest = tmp_path / "export"
    assert (
        await invoke(
            "export-metadata",
            "--manifest",
            manifest,
            "--destination",
            str(dest),
        )
    )["status"] == "exported"
    exported = json.loads((dest / "0" / "chats.json").read_text())
    assert ChatSpec.model_validate(exported["chats"][0]) == spec
    assert (root / "chats.json").read_text() == raw
