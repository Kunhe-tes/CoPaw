# -*- coding: utf-8 -*-
"""Fast verification proves committed structure without reading bodies."""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from swe.app.conversation_storage.bundle import BundleBlock, BundleStore
from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.conversation_storage.migration.verify import verify_import
from swe.app.conversation_storage.migration.verify_fast import (
    verify_fast_publications,
)
from swe.app.conversation_storage.migration.parallel import MigrationIO


def _inputs(
    tmp_path,
    *,
    body=b"body",
    record_plan=False,
    missing_block=False,
):
    migration_id = str(uuid4())
    scope = WorkspaceScope("tenant", "source", "agent", service_unit_id="svc")
    operation_key = "a" * 64
    bundles = BundleStore(tmp_path / "nas")
    bundles.root.mkdir()
    import_plan = {
        "version": 1,
        "migration_id": migration_id,
        "schema": "test_fast_verify",
        "rows": (
            [
                {
                    "table": "publications",
                    "values": (
                        {
                            "id": 1,
                            "checkpoint_revision": 2,
                            "checkpoint_offset": {
                                "block": "missing-checkpoint",
                                "part": "offset",
                            },
                        }
                        if missing_block
                        else {"id": 1, "checkpoint_revision": 2}
                    ),
                },
            ]
            if record_plan or missing_block
            else []
        ),
        "updates": [],
        "locks": {},
    }
    index = bundles.publish(
        operation_key,
        [
            BundleBlock(
                "import_plan",
                "import_plan",
                json.dumps(import_plan, separators=(",", ":")).encode(),
            ),
            BundleBlock("message:1", "message", body),
        ],
        scope=scope,
        metadata={"operation_key": operation_key},
    )
    assignment = {
        "target_id": 1,
        "operation_key": operation_key,
        "relative_path": index.relative_path,
        "scope": list(scope.values),
        "scope_kind": "workspace",
    }
    row = {
        "id": 1,
        "scope_kind": "workspace",
        "service_unit_key": b"svc",
        "tenant_key": b"tenant",
        "source_key": b"source",
        "agent_key": b"agent",
        "operation_key": operation_key.encode(),
        "relative_path": index.relative_path,
        "byte_length": index.byte_length,
        "state": "committed",
        "gc_state": "live",
        "durable_at": "durable",
    }

    class Database:
        config = SimpleNamespace(database="test_fast_verify")
        record_values = {
            "id": 1,
            "service_unit_key": b"svc",
            "checkpoint_revision": 2,
        }

        async def fetch_one(self, query, _params=None):
            assert query == "SELECT DATABASE() AS schema_name"
            return {"schema_name": "test_fast_verify"}

        async def fetch_all(self, query, params=None):
            if params and params[0] == b"svc":
                return [self.record_values] if record_plan else []
            assert "FROM swe_conversation_publications" in query
            assert params == (1,)
            return [row]

        @asynccontextmanager
        async def acquire(self):
            yield SimpleNamespace(
                max_allowed_packet=4 * 1024 * 1024,
                fetch_all=self.fetch_all,
            )

    boundary = {
        "snapshot_id": "snapshot",
        "captured_at": "2026-11-16T00:00:00Z",
        "old_image_digest": "old@sha256:" + "a" * 64,
        "evidence_refs": ["writers-stopped"],
    }
    manifest_data = {
        "migration_id": migration_id,
        "target": {
            "schema": "test_fast_verify",
            "nas_roots": {"svc": str(bundles.root.resolve())},
            "migration_id": migration_id,
        },
        "source_boundary": boundary,
        "workspaces": [
            {
                "service_unit_id": "svc",
                "tenant_id": "tenant",
                "source_id": "source",
                "agent_id": "agent",
                "root": str((tmp_path / "source").resolve()),
            },
        ],
        "services": [{"service_unit_id": "svc"}],
        "assignments": {"publication": {"publication": assignment}},
        "batches": {"publication": "committed"},
    }
    inventory = {
        "version": 2,
        "ready": True,
        "blockers": [],
        "source_boundary": boundary,
        "workspaces": [
            {
                "scope": list(scope.values),
                "root": str((tmp_path / "source").resolve()),
                "sessions": [],
                "chats": [],
            },
        ],
        "shares": [],
        "files": [],
    }
    manifest = SimpleNamespace(data=manifest_data, migration_id=migration_id)
    return Database(), bundles, manifest, inventory, row


@pytest.mark.asyncio
async def test_fast_verification_checks_bundle_structure_without_reading_body(
    tmp_path,
    monkeypatch,
):
    database, bundles, manifest, inventory, _row = _inputs(
        tmp_path,
        body=b"deliberately not compared",
    )

    def reject_body_read(*_args, **_kwargs):
        raise AssertionError("fast verification read a conversation body")

    monkeypatch.setattr(bundles, "read_extent", reject_body_read)
    result = await verify_import(
        database,
        bundles,
        manifest,
        inventory,
        SimpleNamespace(
            schema="test_fast_verify",
            migration_id=manifest.migration_id,
        ),
        verification_level="fast",
    )

    assert result["passed"] is True
    assert result["verification_level"] == "fast"


@pytest.mark.asyncio
async def test_fast_verification_checks_planned_database_record_identity(
    tmp_path,
):
    database, bundles, manifest, inventory, _row = _inputs(
        tmp_path,
        record_plan=True,
    )

    result = await verify_import(
        database,
        bundles,
        manifest,
        inventory,
        SimpleNamespace(
            schema="test_fast_verify",
            migration_id=manifest.migration_id,
        ),
        verification_level="fast",
    )

    assert result["passed"] is True
    assert result["fast_summary"]["checked_records"] == 1


@pytest.mark.asyncio
async def test_fast_verification_rejects_missing_committed_publication(
    tmp_path,
):
    database, bundles, manifest, inventory, _row = _inputs(tmp_path)
    database.fetch_all = lambda *_args, **_kwargs: _empty_rows()

    result = await verify_import(
        database,
        bundles,
        manifest,
        inventory,
        SimpleNamespace(
            schema="test_fast_verify",
            migration_id=manifest.migration_id,
        ),
        verification_level="fast",
    )

    assert result["passed"] is False
    assert "publication" in result["blockers"][0]["detail"]


@pytest.mark.parametrize(
    "mutation",
    (
        lambda row: row.update(tenant_key=b"other-tenant"),
        lambda row: row.update(relative_path="bundles/invalid.bundle"),
    ),
)
@pytest.mark.asyncio
async def test_fast_verification_rejects_wrong_owner_or_locator(
    tmp_path,
    mutation,
):
    database, bundles, manifest, inventory, row = _inputs(tmp_path)
    mutation(row)

    result = await verify_import(
        database,
        bundles,
        manifest,
        inventory,
        SimpleNamespace(
            schema="test_fast_verify",
            migration_id=manifest.migration_id,
        ),
        verification_level="fast",
    )

    assert result["passed"] is False
    assert result["blockers"]


@pytest.mark.asyncio
async def test_fast_verification_rejects_missing_required_block(tmp_path):
    database, bundles, manifest, inventory, _row = _inputs(
        tmp_path,
        missing_block=True,
    )

    result = await verify_import(
        database,
        bundles,
        manifest,
        inventory,
        SimpleNamespace(
            schema="test_fast_verify",
            migration_id=manifest.migration_id,
        ),
        verification_level="fast",
    )

    assert result["passed"] is False
    assert "missing block" in result["blockers"][0]["detail"]


@pytest.mark.asyncio
async def test_fast_verification_rejects_truncated_bundle(tmp_path):
    database, bundles, manifest, inventory, row = _inputs(tmp_path)
    path = bundles.root / row["relative_path"]
    path.write_bytes(path.read_bytes()[:-1])

    result = await verify_import(
        database,
        bundles,
        manifest,
        inventory,
        SimpleNamespace(
            schema="test_fast_verify",
            migration_id=manifest.migration_id,
        ),
        verification_level="fast",
    )

    assert result["passed"] is False
    assert result["blockers"]


@pytest.mark.asyncio
async def test_fast_publication_reads_are_batched_and_bundle_checks_concurrent(
    tmp_path,
):
    migration_id = str(uuid4())
    bundles = BundleStore(tmp_path / "nas")
    bundles.root.mkdir()
    scope = WorkspaceScope("tenant", "source", "agent", service_unit_id="svc")
    assignments, rows = {}, {}
    for identity in range(1, 130):
        operation_key = f"{identity:064x}"
        import_plan = {
            "version": 1,
            "migration_id": migration_id,
            "schema": "test_fast_verify",
            "rows": [],
            "updates": [],
            "locks": {},
        }
        index = bundles.publish(
            operation_key,
            [
                BundleBlock(
                    "import_plan",
                    "import_plan",
                    json.dumps(import_plan, separators=(",", ":")).encode(),
                ),
            ],
            scope=scope,
            metadata={"operation_key": operation_key},
        )
        assignments["position-" + str(identity)] = {
            "target_id": identity,
            "operation_key": operation_key,
            "relative_path": index.relative_path,
            "scope": list(scope.values),
            "scope_kind": "workspace",
        }
        rows[identity] = {
            "id": identity,
            "scope_kind": "workspace",
            "service_unit_key": b"svc",
            "tenant_key": b"tenant",
            "source_key": b"source",
            "agent_key": b"agent",
            "operation_key": operation_key.encode(),
            "relative_path": index.relative_path,
            "byte_length": index.byte_length,
            "state": "committed",
            "gc_state": "live",
            "durable_at": "durable",
        }

    class Database:
        calls = []

        async def fetch_all(self, query, params):
            assert "FROM swe_conversation_publications" in query
            self.calls.append(len(params))
            return [rows[identity] for identity in params]

    database = Database()
    manifest = SimpleNamespace(
        migration_id=migration_id,
        data={
            "assignments": {"publication": assignments},
            "batches": {"position-" + str(i): "committed" for i in rows},
            "target": {"schema": "test_fast_verify"},
        },
    )
    async with MigrationIO(4) as io:
        result = await verify_fast_publications(
            database,
            {"svc": bundles},
            manifest,
            SimpleNamespace(
                schema="test_fast_verify",
                migration_id=migration_id,
            ),
            io=io,
            io_workers=4,
            memory_bytes=16 * 1024 * 1024,
        )

    assert database.calls == [128, 1]
    assert result["publications"] == 129


async def _empty_rows():
    return []
