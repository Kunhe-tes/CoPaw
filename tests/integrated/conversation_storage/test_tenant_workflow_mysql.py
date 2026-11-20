# -*- coding: utf-8 -*-
"""Real two-stage CLI workflow in fixture-owned isolated MySQL schemas."""

import asyncio
import json
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from swe.app.chat_sharing.store import ChatShareStore
from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.conversation_storage.runtime import ConversationRuntime
from swe.app.conversation_storage.tenant_admission import TenantNotPublished
from swe.cli import conversation_storage_tenants as tenant_cli
from tests.integrated.conversation_storage.conftest import (
    SQL_ROOT,
    apply_sql_script,
)
from tests.integrated.conversation_storage.test_tenant_in_place_mysql import (
    _tenant,
)


def _command():
    from swe.cli.conversation_storage_discovery_cmd import (
        register_discovery_commands,
    )

    @click.group()
    def group():
        pass

    register_discovery_commands(group)
    return group


async def _invoke(arguments):
    result = await asyncio.to_thread(CliRunner().invoke, _command(), arguments)
    assert result.exit_code in (0, 2), result.output
    return result.exit_code, json.loads(result.stdout)


async def _write_online_alice(db, runtime, workspace, source_id="SRC"):
    folder_a = workspace.parent.parent
    for path in [folder_a, *folder_a.rglob("*")]:
        path.chmod(0o755 if path.is_dir() else 0o644)
    config_a = folder_a / "config.json"
    current = json.loads(config_a.read_text())
    new_root = folder_a / "workspaces" / "new-agent"
    new_root.mkdir()
    (new_root / "agent.json").write_text('{"id":"new-agent"}')
    current["agents"]["profiles"]["new-agent"] = {
        "id": "new-agent",
        "workspace_dir": str(new_root),
        "enabled": True,
    }
    config_a.write_text(json.dumps(current))
    runtime.for_workspace(
        SimpleNamespace(
            workspace_dir=new_root,
            agent_id="new-agent",
            conversation_scope=WorkspaceScope(
                "alice",
                source_id,
                "new-agent",
                service_unit_id="svc",
            ),
        ),
    )
    await db.execute(
        "UPDATE swe_conversation_chats SET title=%s WHERE tenant_key=%s AND source_key=%s",
        ("online title", b"alice", source_id.encode()),
    )
    existing = await db.fetch_one(
        "SELECT * FROM swe_conversation_chats WHERE tenant_key=%s AND source_key=%s",
        (b"alice", source_id.encode()),
    )
    new_chat = {key: value for key, value in existing.items() if key != "id"}
    new_chat.update(external_chat_key=b"online-chat", title="online new chat")
    await db.insert(
        "INSERT INTO swe_conversation_chats ("
        + ",".join(new_chat)
        + ") VALUES ("
        + ",".join(["%s"] * len(new_chat))
        + ")",
        tuple(new_chat.values()),
    )
    online = await db.fetch_all(
        "SELECT * FROM swe_conversation_chats WHERE tenant_key=%s AND source_key=%s ORDER BY id",
        (b"alice", source_id.encode()),
    )
    return config_a, current, online


async def _prepare_database(db, monkeypatch):
    await ChatShareStore(db).ensure_schema()
    for name in (
        "conversation_share_publication_extension.sql",
        "conversation_migration_control_tables.sql",
    ):
        await apply_sql_script(db, SQL_ROOT / name)
    monkeypatch.setattr(
        "swe.database.config.get_database_config",
        lambda: db.config,
    )
    monkeypatch.setattr(
        "swe.database.get_database_config",
        lambda: db.config,
    )


def _prepare_sources(tmp_path, failure_mode, *, same_tenant=False):
    source, nas, work = (tmp_path / n for n in ("source", "nas", "work"))
    nas.mkdir()
    work.mkdir()
    workspaces = (
        {name: _tenant(source, "alice", name) for name in ("alice", "bob")}
        if same_tenant
        else {
            name: _tenant(source, name) for name in ("alice", "bob", "charlie")
        }
    )
    config_b = workspaces["bob"].parent.parent / "config.json"
    original_b = config_b.read_bytes()
    session_b = (
        workspaces["bob"]
        / "sessions"
        / ("alice_s.json" if same_tenant else "bob_s.json")
    )
    if failure_mode == "config":
        config_b.write_text('{"agents":{"profiles":42}}')
    elif failure_mode == "running_turn":
        state = json.loads(session_b.read_text())
        state["turn_states"] = {"running-turn": {"status": "running"}}
        session_b.write_text(json.dumps(state))
    elif failure_mode == "invalid_chats":
        (workspaces["bob"] / "chats.json").write_text("invalid json")
    for path in source.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    source.chmod(0o555)
    service_file = tmp_path / "services.json"
    service_file.write_text(
        json.dumps(
            {
                "services": [
                    {
                        "service_unit_id": "svc",
                        **{
                            key: str(source)
                            for key in (
                                "source_root",
                                "original_root",
                                "config_root",
                                "snapshot_root",
                            )
                        },
                        "nas_root": str(nas),
                    },
                ],
            },
        ),
    )
    boundary = tmp_path / "boundary.json"
    boundary.write_text(
        json.dumps(
            {
                "snapshot_id": "stopped-workflow",
                "captured_at": "2026-11-15T00:00:00Z",
                "old_image_digest": "old@sha256:" + "a" * 64,
                "evidence_refs": ["stopped", "readonly"],
            },
        ),
    )
    manifest = tmp_path / "manifest.json"
    shares = tmp_path / "shares.json"
    shares.write_text("[]")
    output = tmp_path / "runtime"
    resource_args = [
        "--workers",
        "3",
        "--io-workers",
        "2",
        "--memory-budget-mib",
        "128",
        "--work-dir",
        str(work),
    ]
    return (
        source,
        nas,
        workspaces,
        config_b,
        original_b,
        session_b,
        manifest,
        output,
        resource_args,
        service_file,
        boundary,
        shares,
    )


def _observe_import_failure(monkeypatch):
    imported_failures = []
    from swe.app.conversation_storage.migration.tenant_errors import (
        TenantInputError,
    )

    original_run = tenant_cli.DirectImporter.run_parallel

    async def run_import(importer, *args, **kwargs):
        try:
            return await original_run(importer, *args, **kwargs)
        except TenantInputError as error:
            imported_failures.append(
                (importer.journal.active_tenant, str(error)),
            )
            raise

    monkeypatch.setattr(tenant_cli.DirectImporter, "run_parallel", run_import)
    return imported_failures


async def _assert_failed_tenant_has_no_commits(
    db,
    failure_mode,
    imported_failures,
):
    if failure_mode == "running_turn":
        assert imported_failures == [
            (
                ("svc", "bob", "SRC"),
                "unsettled legacy Turn blocks offline import",
            ),
        ]
    if failure_mode in ("running_turn", "invalid_chats"):
        bob_scope = ["svc", "bob", "SRC", "agent"]
        tickets = await db.fetch_all(
            "SELECT entry_kind,source_key,details_text FROM swe_conversation_migration_entries",
        )
        assert not any(
            json.loads(row["details_text"] or "{}").get("scope") == bob_scope
            for row in tickets
        )
        assert (
            await db.fetch_all(
                "SELECT id FROM swe_conversation_sessions WHERE tenant_key=%s",
                (b"bob",),
            )
            == []
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_mode",
    ["config", "running_turn", "invalid_chats"],
)
async def test_migrate_retry_keeps_failed_source_closed_and_skips_published_source(
    conversation_test_database,
    tmp_path,
    monkeypatch,
    failure_mode,
):
    db = conversation_test_database
    await _prepare_database(db, monkeypatch)
    (
        source,
        nas,
        workspaces,
        _config_b,
        _original_b,
        session_b,
        manifest,
        output,
        resource_args,
        service_file,
        boundary,
        shares,
    ) = _prepare_sources(tmp_path, failure_mode)
    code, prepared = await _invoke(
        [
            "prepare",
            "--services",
            str(service_file),
            "--boundary",
            str(boundary),
            "--manifest",
            str(manifest),
            "--shares-file",
            str(shares),
            "--tenant-isolation",
            "--in-place",
            *resource_args,
        ],
    )
    assert code == (2 if failure_mode == "config" else 0)
    assert prepared["failed"] == int(failure_mode == "config")
    assert await db.fetch_all("SELECT * FROM swe_conversation_chats") == []
    imported_failures = _observe_import_failure(monkeypatch)
    migrate_args = [
        "migrate",
        "--manifest",
        str(manifest),
        "--apply",
        *resource_args,
    ]
    code, migrated = await _invoke(migrate_args)
    assert code == 2
    assert migrated["published"] == 2 and migrated["failed"] == 1
    assert not output.exists()
    assert migrated["verification_level"] == "fast"
    receipts = await db.fetch_all(
        "SELECT verification_text FROM swe_conversation_migration_sources "
        "WHERE state='published'",
    )
    assert len(receipts) == 2
    assert all(
        json.loads(row["verification_text"])["verification_level"] == "fast"
        for row in receipts
    )
    await _assert_failed_tenant_has_no_commits(
        db,
        failure_mode,
        imported_failures,
    )
    runtime = ConversationRuntime(
        db,
        {
            "version": 3,
            "service_unit_id": "svc",
            "nas_root": str(nas),
            "migration_id": migrated["migration_id"],
        },
        b"cursor",
        service_unit_id="svc",
    )
    await runtime.admit("alice", "SRC")
    with pytest.raises(TenantNotPublished):
        await runtime.admit("bob", "SRC")
    config_a, current, online = await _write_online_alice(
        db,
        runtime,
        workspaces["alice"],
    )
    parsed = []
    real_inventory = tenant_cli._inventory

    async def inventory(view, spool, resources):
        parsed.append(view.key[1])
        assert view.key[1] != "alice", "published source was parsed again"
        return await real_inventory(view, spool, resources)

    monkeypatch.setattr(tenant_cli, "_inventory", inventory)
    code, resumed = await _invoke(migrate_args)
    assert code == 2 and resumed["pending_schema_finalize"] is False
    assert resumed["published"] == 2 and resumed["failed"] == 1
    assert "alice" not in parsed
    assert (
        await db.fetch_all(
            "SELECT * FROM swe_conversation_chats WHERE tenant_key=%s ORDER BY id",
            (b"alice",),
        )
        == online
    )
    assert config_a.read_text() == json.dumps(current)
    with pytest.raises(TenantNotPublished):
        await runtime.admit("bob", "SRC")


@pytest.mark.asyncio
async def test_same_tenant_source_retry_preserves_published_sibling(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    """A tenant-wide admission or retry would corrupt this live sibling."""
    db = conversation_test_database
    await _prepare_database(db, monkeypatch)
    (
        _source,
        nas,
        workspaces,
        _config,
        _original,
        session_b,
        manifest,
        output,
        resources,
        services,
        boundary,
        shares,
    ) = _prepare_sources(tmp_path, "running_turn", same_tenant=True)
    code, prepared = await _invoke(
        [
            "prepare",
            "--services",
            str(services),
            "--boundary",
            str(boundary),
            "--manifest",
            str(manifest),
            "--shares-file",
            str(shares),
            "--tenant-isolation",
            "--in-place",
            *resources,
        ],
    )
    assert code == 0 and prepared["failed"] == 0
    arguments = [
        "migrate",
        "--manifest",
        str(manifest),
        "--apply",
        *resources,
    ]
    code, first = await _invoke(arguments)
    assert code == 2 and first["published"] == 1 and first["failed"] == 1
    runtime = ConversationRuntime(
        db,
        {
            "version": 3,
            "service_unit_id": "svc",
            "nas_root": str(nas),
            "migration_id": first["migration_id"],
        },
        b"cursor",
        service_unit_id="svc",
    )
    await runtime.admit("alice", "alice")
    for source_id in (None, "bob", "unknown"):
        with pytest.raises(TenantNotPublished):
            await runtime.admit("alice", source_id)
    assert (
        await db.fetch_all(
            "SELECT id FROM swe_conversation_chats WHERE tenant_key=%s AND source_key=%s",
            (b"alice", b"bob"),
        )
        == []
    )

    workspace_a = workspaces["alice"]
    config_a, current, online = await _write_online_alice(
        db,
        runtime,
        workspace_a,
        source_id="alice",
    )
    assert len(online) == 2
    query = "SELECT * FROM swe_conversation_chats WHERE tenant_key=%s AND source_key=%s ORDER BY id"
    # Poison the old live input: a re-read must fail instead of passing unnoticed.
    old_session_a = workspace_a / "sessions" / "alice_s.json"
    old_session_a.write_text(
        "live input no longer is a frozen migration session",
    )
    state = json.loads(session_b.read_text())
    state.pop("turn_states")
    session_b.chmod(0o644)
    session_b.write_text(json.dumps(state))
    session_b.chmod(0o444)
    parsed = []
    real_inventory = tenant_cli._inventory

    async def inventory(view, spool, settings):
        parsed.append(view.key)
        assert view.key == (
            "svc",
            "alice",
            "bob",
        ), "published sibling was parsed again"
        return await real_inventory(view, spool, settings)

    monkeypatch.setattr(tenant_cli, "_inventory", inventory)
    code, resumed = await _invoke(arguments)
    assert code == 2 and resumed["pending_schema_finalize"] is True
    assert resumed["published"] == 2 and resumed["failed"] == 0
    assert parsed and set(parsed) == {("svc", "alice", "bob")}
    assert await db.fetch_all(query, (b"alice", b"alice")) == online
    assert config_a.read_text() == json.dumps(current)
    assert (
        old_session_a.read_text()
        == "live input no longer is a frozen migration session"
    )
    await runtime.admit("alice", "bob")
    with pytest.raises(TenantNotPublished):
        await runtime.admit("alice", "unknown")
    await apply_sql_script(
        db,
        SQL_ROOT / "conversation_tenant_publication_finalize.sql",
    )
    code, finalized = await _invoke(arguments)
    assert code == 0
    assert finalized["state"] == "ready"
    assert finalized["published"] == 2 and finalized["failed"] == 0
