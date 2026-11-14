# -*- coding: utf-8 -*-
"""In-place tenant publication uses SQL while another tenant remains frozen."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from swe.app.chat_sharing.store import ChatShareStore
from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.conversation_storage.migration.discovery import (
    discover_services,
    freeze_discovery,
)
from swe.app.conversation_storage.migration.manifest import SourceBoundary
from swe.app.conversation_storage.runtime import ConversationRuntime
from swe.app.conversation_storage.tenant_admission import TenantNotPublished
from swe.cli import conversation_storage_tenants as tenant_cli
from swe.config.context import encode_scope_id
from tests.integrated.conversation_storage.conftest import (
    SQL_ROOT,
    apply_sql_script,
)


def _tenant(root, tenant):
    from swe.app.runner.models import ChatSpec, ChatsFile
    from uuid import uuid4

    folder = root / encode_scope_id(tenant, "SRC")
    workspace = folder / "workspaces" / "agent"
    workspace.mkdir(parents=True)
    (workspace / "sessions").mkdir()
    (workspace / "sessions" / f"{tenant}_s.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "revision": 1,
                "agent": {"memory": {"content": []}},
            },
        ),
    )
    (workspace / "agent.json").write_text('{"id":"agent"}')
    (workspace / "chats.json").write_text(
        ChatsFile(
            chats=[
                ChatSpec(
                    id=str(uuid4()),
                    session_id="s",
                    user_id=tenant,
                    channel="console",
                ),
            ],
        ).model_dump_json(),
    )
    profiles = {
        "agent": {
            "id": "agent",
            "workspace_dir": str(workspace),
            "enabled": True,
        },
    }
    (folder / "config.json").write_text(
        json.dumps({"agents": {"profiles": profiles}}),
    )
    return workspace


@pytest.mark.asyncio
# Complete A publication/new Agent/B retry chain shares one durable SQL job.
# pylint: disable-next=too-many-statements
async def test_in_place_online_tenant_does_not_poison_pending_tenant(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    db = conversation_test_database
    await ChatShareStore(db).ensure_schema()
    await apply_sql_script(
        db,
        SQL_ROOT / "conversation_share_publication_extension.sql",
    )
    await apply_sql_script(
        db,
        SQL_ROOT / "conversation_migration_control_tables.sql",
    )
    root, nas, work = (tmp_path / name for name in ("original", "nas", "work"))
    nas.mkdir()
    work.mkdir()
    workspaces = {
        tenant: _tenant(root, tenant) for tenant in ("alice", "bob", "charlie")
    }
    before_b = (workspaces["bob"] / "chats.json").read_bytes()
    for path in root.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    root.chmod(0o555)
    report = discover_services(
        [
            {
                "service_unit_id": "svc",
                "source_root": str(root),
                "original_root": str(root),
                "config_root": str(root),
                "snapshot_root": str(root),
                "nas_root": str(nas),
            },
        ],
        shares=[],
        tenant_isolation=True,
        in_place=True,
    )
    assert report["ready"], report["blockers"]
    manifest = freeze_discovery(
        report,
        tmp_path / "manifest.json",
        SourceBoundary(
            "frozen",
            "2026-11-13T00:00:00Z",
            "old@sha256:" + "a" * 64,
            ("stopped", "readonly"),
        ),
        db.config.database,
    )
    monkeypatch.setattr(
        "swe.database.config.get_database_config",
        lambda: db.config,
    )
    resources = {
        "workers": 2,
        "io_workers": 2,
        "memory_budget_mib": 128,
        "work_dir": str(work),
        "apply": True,
    }
    real_inventory = tenant_cli._inventory
    pending_failure = True
    online = False
    parsed = []

    async def inventory(view, spool, settings):
        tenant = view.key[1]
        parsed.append(tenant)
        if online and tenant in {"alice", "charlie"}:
            raise AssertionError("published source was parsed again")
        if tenant == "bob" and pending_failure:
            raise tenant_cli.TenantFailure("injected tenant data failure")
        try:
            return await real_inventory(view, spool, settings)
        except tenant_cli.TenantFailure as error:
            raise AssertionError(
                f"unexpected inventory failure for {tenant}: {error}",
            ) from error

    monkeypatch.setattr(tenant_cli, "_inventory", inventory)
    assert (
        await tenant_cli.run_tenants("import", manifest, None, **resources)
    )["failed"] == 1
    first = await tenant_cli.run_tenants(
        "finalize",
        manifest,
        tmp_path / "completion",
        **resources,
    )
    assert first["published"] == 2 and first["failed"] == 1
    runtime = ConversationRuntime(
        db,
        {
            "version": 3,
            "migration_id": manifest.migration_id,
            "service_unit_id": "svc",
            "nas_root": str(nas),
        },
        b"cursor",
        service_unit_id="svc",
    )
    with pytest.raises(TenantNotPublished):
        await runtime.admit("bob")
    await runtime.admit("alice")
    online = True
    folder_a = workspaces["alice"].parent.parent
    folder_a.chmod(0o755)
    for path in folder_a.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    config = folder_a / "config.json"
    current = json.loads(config.read_text())
    new_root = folder_a / "workspaces" / "new-agent"
    new_root.mkdir()
    (new_root / "agent.json").write_text('{"id":"new-agent"}')
    current["agents"]["profiles"]["new-agent"] = {
        "id": "new-agent",
        "workspace_dir": str(new_root),
        "enabled": True,
    }
    config.write_text(json.dumps(current))
    storage = runtime.for_workspace(
        SimpleNamespace(
            workspace_dir=new_root,
            agent_id="new-agent",
            conversation_scope=WorkspaceScope(
                "alice",
                "SRC",
                "new-agent",
                service_unit_id="svc",
            ),
        ),
    )
    assert storage.scope.agent_id == "new-agent"
    await db.execute(
        "UPDATE swe_conversation_chats SET title=%s WHERE tenant_key=%s",
        ("online title", b"alice"),
    )
    existing = await db.fetch_one(
        "SELECT * FROM swe_conversation_chats WHERE tenant_key=%s",
        (b"alice",),
    )
    new_chat = {key: value for key, value in existing.items() if key != "id"}
    new_chat["external_chat_key"] = b"online-chat"
    new_chat["title"] = "new online chat"
    await db.insert(
        "INSERT INTO swe_conversation_chats ("
        + ",".join(new_chat)
        + ") VALUES ("
        + ",".join(["%s"] * len(new_chat))
        + ")",
        tuple(new_chat.values()),
    )
    online_a = await db.fetch_all(
        "SELECT * FROM swe_conversation_chats WHERE tenant_key=%s",
        (b"alice",),
    )
    # Shared service directory mtime may change without changing B's input.
    root.chmod(0o755)
    marker = root / "ordinary-business-marker"
    marker.write_text("unrelated")
    pending_failure = False
    parsed.clear()
    resumed = await tenant_cli.run_tenants(
        "resume",
        manifest,
        None,
        **resources,
    )
    assert resumed["failed"] == 0, resumed
    final = await tenant_cli.run_tenants(
        "finalize",
        manifest,
        tmp_path / "completion",
        **resources,
    )
    assert final["published"] == 3
    assert parsed and set(parsed) == {"bob"}
    assert (
        await db.fetch_all(
            "SELECT * FROM swe_conversation_chats WHERE tenant_key=%s",
            (b"alice",),
        )
        == online_a
    )
    assert config.read_text() == json.dumps(current)
    assert (workspaces["bob"] / "chats.json").read_bytes() == before_b
    assert not (workspaces["bob"] / "chats.json").stat().st_mode & 0o222
    await runtime.admit("bob")


@pytest.mark.asyncio
# Full zero-data review, durable SQL CAS, publication and live A preservation.
# pylint: disable-next=too-many-statements
async def test_in_place_failed_config_review_preserves_published_tenant(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    db = conversation_test_database
    await ChatShareStore(db).ensure_schema()
    await apply_sql_script(
        db,
        SQL_ROOT / "conversation_share_publication_extension.sql",
    )
    await apply_sql_script(
        db,
        SQL_ROOT / "conversation_migration_control_tables.sql",
    )
    root, nas, work = (tmp_path / name for name in ("original", "nas", "work"))
    nas.mkdir()
    work.mkdir()
    workspace_a = _tenant(root, "alice")
    workspace_b = _tenant(root, "bob")
    config_b = workspace_b.parent.parent / "config.json"
    correct_b = config_b.read_bytes()
    config_b.write_text('{"agents":{"profiles":42}}')
    for path in root.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    root.chmod(0o555)
    report = discover_services(
        [
            {
                "service_unit_id": "svc",
                "source_root": str(root),
                "original_root": str(root),
                "config_root": str(root),
                "snapshot_root": str(root),
                "nas_root": str(nas),
            },
        ],
        shares=[],
        tenant_isolation=True,
        in_place=True,
    )
    failures = {item["tenant_id"]: item["state"] for item in report["tenants"]}
    assert failures == {"alice": "discovered", "bob": "failed"}, report[
        "blockers"
    ]
    reviewed = tmp_path / "reviewed-discovery.json"
    reviewed.write_text(json.dumps(report))
    manifest = freeze_discovery(
        report,
        tmp_path / "manifest.json",
        SourceBoundary(
            "frozen",
            "2026-11-13T00:00:00Z",
            "old@sha256:" + "a" * 64,
            ("stopped", "readonly"),
        ),
        db.config.database,
    )
    monkeypatch.setattr(
        "swe.database.config.get_database_config",
        lambda: db.config,
    )
    resources = {
        "workers": 2,
        "io_workers": 2,
        "memory_budget_mib": 128,
        "work_dir": str(work),
        "apply": True,
    }
    assert (
        await tenant_cli.run_tenants("import", manifest, None, **resources)
    )["failed"] == 1
    first = await tenant_cli.run_tenants(
        "finalize",
        manifest,
        tmp_path / "completion",
        **resources,
    )
    assert first["published"] == 1 and first["failed"] == 1
    folder_a = workspace_a.parent.parent
    folder_a.chmod(0o755)
    for path in folder_a.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    config_a = folder_a / "config.json"
    current_a = json.loads(config_a.read_text())
    new_agent = folder_a / "workspaces" / "new-agent"
    new_agent.mkdir()
    (new_agent / "agent.json").write_text('{"id":"new-agent"}')
    current_a["agents"]["profiles"]["new-agent"] = {
        "id": "new-agent",
        "workspace_dir": str(new_agent),
        "enabled": True,
    }
    config_a.write_text(json.dumps(current_a))
    await db.execute(
        "UPDATE swe_conversation_chats SET title=%s WHERE tenant_key=%s",
        ("A live title", b"alice"),
    )
    online_a = await db.fetch_all(
        "SELECT * FROM swe_conversation_chats WHERE tenant_key=%s",
        (b"alice",),
    )
    config_b.chmod(0o644)
    config_b.write_bytes(correct_b)
    config_b.chmod(0o444)
    result = await tenant_cli.run_tenants(
        "retry-review",
        manifest,
        None,
        reviewed_discovery=reviewed,
        **resources,
    )
    assert result["status"] == "success", result
    assert (
        next(
            item
            for item in manifest.data["tenants"]
            if item["tenant_id"] == "bob"
        )["state"]
        == "discovered"
    )
    states = await db.fetch_all(
        "SELECT tenant_key,state FROM swe_conversation_migration_tenants ORDER BY tenant_key",
    )
    assert {row["tenant_key"]: row["state"] for row in states} == {
        b"alice": "published",
        b"bob": "discovered",
    }
    resumed = await tenant_cli.run_tenants(
        "resume",
        manifest,
        None,
        **resources,
    )
    assert resumed["failed"] == 0, resumed
    final = await tenant_cli.run_tenants(
        "finalize",
        manifest,
        tmp_path / "completion",
        **resources,
    )
    assert final["published"] == 2, final
    assert (
        await db.fetch_all(
            "SELECT * FROM swe_conversation_chats WHERE tenant_key=%s",
            (b"alice",),
        )
        == online_a
    )
    assert config_a.read_text() == json.dumps(current_a)
    assert config_b.read_bytes() == correct_b
