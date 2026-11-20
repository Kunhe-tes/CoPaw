# -*- coding: utf-8 -*-
"""CLI verification preserves data and records audit evidence."""

import asyncio
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from swe.app.chat_sharing.store import ChatShareStore
from swe.app.conversation_storage.migration.discovery import (
    SHARE_FIELDS,
    discover_services,
    freeze_discovery,
)
from swe.app.conversation_storage.migration.manifest import SourceBoundary
from swe.cli import conversation_storage_v3_cmd as commands
from swe.cli.conversation_storage_cmd import conversation_storage_group
from tests.integrated.conversation_storage.conftest import (
    SQL_ROOT,
    TABLES,
    apply_sql_script,
)
from tests.integrated.conversation_storage.test_migration_lock_loss_mysql import (
    _source,
)

SNAPSHOT_TABLES = (
    *TABLES,
    "swe_chat_shares",
    "swe_conversation_migration_entries",
)
JOB_MUTABLE_COLUMNS = ("verification_text", "updated_at")


async def _snapshot(database):
    # Compare every returned column, including bodies, counters and timestamps.
    # Sorting by repr supplies stable order without assuming a shared SQL PK.
    return {
        table: sorted(
            await database.fetch_all("SELECT * FROM " + table),
            key=lambda row: repr(sorted(row.items())),
        )
        for table in SNAPSHOT_TABLES
    }


async def _migration_job(database):
    return await database.fetch_one(
        "SELECT * FROM swe_conversation_migration_jobs",
    )


def _without_mutable_job_fields(row):
    return {
        key: value
        for key, value in row.items()
        if key not in JOB_MUTABLE_COLUMNS
    }


async def _import_fixture(database, tmp_path):
    await ChatShareStore(database).ensure_schema()
    for name in (
        "conversation_share_publication_extension.sql",
        "conversation_migration_control_tables.sql",
    ):
        await apply_sql_script(database, SQL_ROOT / name)
    services = []
    sources = []
    for index in range(2):
        source, nas = _source(tmp_path / str(index))
        sources.append(source)
        token = "readonly-share-" + str(index)
        for path in source.rglob("*"):
            path.chmod(0o555 if path.is_dir() else 0o444)
        source.chmod(0o555)
        chats = json.loads(
            (source / "default_SRC/workspaces/agent0/chats.json").read_text(),
        )
        session_path = (
            source
            / "default_SRC/workspaces/agent0/sessions/alice_session0.json"
        )
        state = json.loads(session_path.read_text())
        message = state["agent"]["memory"]["content"][0]
        state["turn_states"] = {
            message["id"]: {
                "chat_id": chats["chats"][0]["id"],
                "status": "completed",
                "message": message,
                "admission_order": 0,
            },
        }
        session_path.chmod(0o644)
        session_path.write_text(json.dumps(state))
        session_path.chmod(0o444)
        await database.execute(
            "INSERT INTO swe_chat_shares "
            "(token,chat_id,creator_id,tenant_id,snapshot_key,created_at,access_count,last_access_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                token,
                chats["chats"][0]["id"],
                "alice",
                "default",
                "default/chat_shares/" + token + ".json",
                "2026-11-01 00:00:00",
                17 + index,
                "2026-11-02 00:00:00",
            ),
        )
        services.append(
            {
                "service_unit_id": "READONLY-" + str(index),
                "source_root": str(source),
                "config_root": str(source),
                "snapshot_root": str(source),
                "original_root": str(nas),
                "nas_root": str(nas),
            },
        )
    original_shares = await database.fetch_all(
        "SELECT "
        + ",".join(SHARE_FIELDS)
        + " FROM swe_chat_shares ORDER BY token",
    )
    report = discover_services(services)
    assert report["ready"], report["blockers"]
    manifest = freeze_discovery(
        report,
        tmp_path / "manifest.json",
        SourceBoundary(
            "snapshot",
            "2026-11-02T00:00:00Z",
            "old@sha256:" + "a" * 64,
            ("stopped", "readonly"),
        ),
        database.config.database,
    )
    work = tmp_path / "work"
    work.mkdir()
    await asyncio.to_thread(
        commands.run_v3_command,
        "import",
        manifest.path,
        apply=True,
        workers=2,
        io_workers=2,
        work_dir=work,
    )
    return manifest.path, work, sources, original_shares


@pytest.mark.asyncio
async def test_cli_verify_preserves_data_and_records_audit_evidence(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    database = conversation_test_database
    monkeypatch.setattr(
        "swe.database.config.get_database_config",
        lambda: database.config,
    )
    manifest_path, work, sources, original_shares = await _import_fixture(
        database,
        tmp_path,
    )
    before = await _snapshot(database)
    assert all(before[table] for table in SNAPSHOT_TABLES)
    before_job = await _migration_job(database)
    assert before_job is not None
    manifest_bytes = Path(manifest_path).read_bytes()
    manifest_data = json.loads(manifest_bytes)
    assert not manifest_data.get("source_change_blockers")
    try:
        result = await asyncio.to_thread(
            CliRunner().invoke,
            conversation_storage_group,
            [
                "verify",
                "--manifest",
                str(manifest_path),
                "--workers",
                "2",
                "--io-workers",
                "2",
                "--work-dir",
                str(work),
            ],
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["passed"] is True
        assert await _snapshot(database) == before
        after_job = await _migration_job(database)
        assert after_job is not None
        assert _without_mutable_job_fields(
            after_job,
        ) == _without_mutable_job_fields(
            before_job,
        )
        evidence = json.loads(after_job["verification_text"])
        assert evidence["verification_level"] == "fast"
        assert evidence["verification_results"]["fast"]["passed"] is True
        assert Path(manifest_path).read_bytes() == manifest_bytes
        assert json.loads(Path(manifest_path).read_bytes()) == manifest_data
        current_shares = await database.fetch_all(
            "SELECT "
            + ",".join(SHARE_FIELDS)
            + " FROM swe_chat_shares ORDER BY token",
        )
        assert current_shares == original_shares
    finally:
        for source in sources:
            for path in source.rglob("*"):
                if path.is_dir():
                    path.chmod(0o755)
            source.chmod(0o755)
