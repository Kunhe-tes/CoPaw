# -*- coding: utf-8 -*-
"""Cross-layer cutoff and all-service finalize barriers on small real inputs."""

import asyncio

import pytest

from swe.app.chat_sharing.store import ChatShareStore
from swe.app.conversation_storage.migration.discovery import (
    discover_services,
    freeze_discovery,
)
from swe.app.conversation_storage.migration.freshness import tenant_key
from swe.app.conversation_storage.migration.importer import (
    ParallelWorkspaceImporter,
)
from swe.app.conversation_storage.migration.manifest import SourceBoundary
from swe.app.conversation_storage.migration.parallel_import import (
    MigrationDomainRouter,
)
from swe.app.conversation_storage.migration.v3_manifest import V3Manifest
from swe.cli import conversation_storage_v3_cmd as command
from tests.integrated.conversation_storage.conftest import (
    SQL_ROOT,
    apply_sql_script,
)
from tests.integrated.conversation_storage.test_migration_lock_loss_mysql import (
    _source,
)


async def _prepare(db, tmp_path):
    await ChatShareStore(db).ensure_schema()
    for name in (
        "conversation_share_publication_extension.sql",
        "conversation_migration_control_tables.sql",
    ):
        await apply_sql_script(db, SQL_ROOT / name)
    services, roots = [], {}
    for service in ("A", "B"):
        source, nas = _source(tmp_path / service)
        roots[service] = (source, nas)
        services.append(
            {
                "service_unit_id": service,
                "source_root": str(source),
                "config_root": str(source),
                "original_root": str(nas),
                "nas_root": str(nas),
            },
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
        db.config.database,
    )
    work = tmp_path / "work"
    work.mkdir()
    return manifest, work, roots


def _restore_roots(roots):
    for source, _nas in roots.values():
        for path in source.rglob("*"):
            if path.is_dir():
                path.chmod(0o755)
        source.chmod(0o755)


async def _run(operation, manifest, work, **options):
    return await asyncio.to_thread(
        command.run_v3_command,
        operation,
        manifest.path,
        workers=1,
        io_workers=1,
        work_dir=work,
        **options,
    )


async def test_all_service_cutoffs_are_durable_before_first_workspace(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    db = conversation_test_database
    manifest, work, roots = await _prepare(db, tmp_path)
    monkeypatch.setattr(
        "swe.database.config.get_database_config",
        lambda: db.config,
    )
    expected = {
        tenant_key("A", "default"),
        tenant_key("B", "default"),
    }
    cutoffs, opens = {}, []
    original_open = MigrationDomainRouter._open
    original_finish = ParallelWorkspaceImporter._batch_finished

    async def checked_open(router, workspace):
        saved = V3Manifest.load(manifest.path).data[
            "tenant_sync_started_at_ns"
        ]
        assert set(saved) == expected
        assert all(
            type(value) is int and value > 0 for value in saved.values()
        )
        if not cutoffs:
            cutoffs.update(saved)
        assert saved == cutoffs
        opens.append(tuple(workspace["scope"]))
        return await original_open(router, workspace)

    async def stop_after_committed_batch(importer, position):
        await original_finish(importer, position)
        raise RuntimeError("stop after durable batch")

    monkeypatch.setattr(MigrationDomainRouter, "_open", checked_open)
    try:
        with monkeypatch.context() as interrupted:
            interrupted.setattr(
                ParallelWorkspaceImporter,
                "_batch_finished",
                stop_after_committed_batch,
            )
            with pytest.raises(RuntimeError, match="stop after durable batch"):
                await _run("import", manifest, work, apply=True)
        assert opens
        first_opens = len(opens)
        committed = await db.fetch_one(
            "SELECT COUNT(*) AS total FROM swe_conversation_publications WHERE state='committed'",
        )
        assert committed["total"] > 0
        await _run("resume", manifest, work, apply=True)
        assert len(opens) > first_opens
        assert (
            V3Manifest.load(manifest.path).data["tenant_sync_started_at_ns"]
            == cutoffs
        )
        assert {scope[0] for scope in opens} == {"A", "B"}
    finally:
        _restore_roots(roots)


# pylint: disable-next=too-many-statements
async def test_finalize_rechecks_source_after_fast_verification(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    db = conversation_test_database
    manifest, work, roots = await _prepare(db, tmp_path)
    monkeypatch.setattr(
        "swe.database.config.get_database_config",
        lambda: db.config,
    )
    try:
        await _run("import", manifest, work, apply=True)
        await apply_sql_script(
            db,
            SQL_ROOT / "conversation_share_service_unit_finalize.sql",
        )
        observed, rechecked = [], []
        original_recheck = command._recheck_spooled_inventory
        original_verify = command.verify_import

        async def record_recheck(
            manifest,
            expected,
            base,
            *,
            disk_limit,
            record_limit,
            protected,
            workers,
            io_workers,
            memory_bytes,
        ):
            result = await original_recheck(
                manifest,
                expected,
                base,
                disk_limit=disk_limit,
                record_limit=record_limit,
                protected=protected,
                workers=workers,
                io_workers=io_workers,
                memory_bytes=memory_bytes,
            )
            rechecked.append(result)
            return result

        async def verify_then_fault(*args, **kwargs):
            result = await original_verify(*args, **kwargs)
            observed.append(result["passed"])
            assert result["passed"]
            path = roots["B"][0] / "default_SRC/workspaces/agent1/agent.json"
            path.chmod(0o644)
            path.write_text('{"id":"changed-after-verify"}')
            path.chmod(0o444)
            return result

        monkeypatch.setattr(command, "verify_import", verify_then_fault)
        monkeypatch.setattr(
            command,
            "_recheck_spooled_inventory",
            record_recheck,
        )
        output = tmp_path / "completion-output"
        with pytest.raises(
            ValueError,
            match="source inventory changed",
        ):
            await _run(
                "finalize",
                manifest,
                work,
                apply=True,
                output_dir=output,
            )
        assert observed == [True]
        assert rechecked == [False]
        state = await db.fetch_one(
            "SELECT state FROM swe_conversation_migration_jobs WHERE migration_id=%s",
            (manifest.migration_id,),
        )
        assert state["state"] != "ready"
        assert not (output / "completion.json").exists()
        assert list(output.glob("*.runtime.json")) == []
    finally:
        _restore_roots(roots)
