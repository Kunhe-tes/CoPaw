# -*- coding: utf-8 -*-
"""Fast verification proves committed structure without reading bodies."""

import asyncio
import json
import io
from contextlib import asynccontextmanager, contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from swe.app.conversation_storage.bundle import BundleBlock, BundleStore
from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.conversation_storage.errors import IntegrityError
from swe.app.conversation_storage.migration.verify import verify_import
from swe.app.conversation_storage.migration.archive_verification import (
    read_archive_chunk,
)
from swe.app.conversation_storage.migration.verify_fast import (
    _read_publication_plan,
    _validate_message_blocks,
    _verify_archive_chunks,
    _verify_archive_dependencies_batch,
    _verify_chunk_directory,
    _verify_archive_dependencies,
    _validate_locator_pairs,
    verify_fast_publications,
)


def test_fast_archive_chunk_checks_range_and_chat(tmp_path):
    from swe.app.conversation_storage.message_bundle import (
        encode_message_directory,
    )

    bundles = BundleStore(tmp_path)
    operation = "b" * 64
    scope = WorkspaceScope("tenant", "source", "agent", service_unit_id="svc")
    entry = {
        "sequence": 8,
        "raw_id": "m",
        "layer": "archive",
        "source_occurrence": 7,
        "source_occurrence_no": 7,
        "visible": True,
        "chat_id": 3,
        "epoch": 1,
        "body": {
            "publication_id": "self",
            "block_name": "message_bodies",
            "position": 0,
        },
    }
    index = bundles.publish(
        operation,
        [
            BundleBlock(
                "message_directory",
                "message_directory",
                encode_message_directory([entry]),
            ),
        ],
        scope=scope,
        metadata={"operation_key": operation},
    )
    assignment = {
        "relative_path": index.relative_path,
        "operation_key": operation,
    }
    row = {
        "byte_length": index.byte_length,
        "relative_path": index.relative_path,
    }
    chunk = {
        "directory_block": "message_directory",
        "first_sequence": 8,
        "last_sequence": 8,
    }
    _verify_chunk_directory(
        SimpleNamespace(bundles=bundles),
        row,
        assignment,
        chunk,
        3,
        1,
        100000,
    )
    with pytest.raises(IntegrityError, match="association"):
        _verify_chunk_directory(
            SimpleNamespace(bundles=bundles),
            row,
            assignment,
            chunk,
            4,
            1,
            100000,
        )


def test_archive_chunk_read_opens_bundle_once(tmp_path, monkeypatch):
    from swe.app.conversation_storage.message_bundle import (
        encode_message_bodies,
        encode_message_directory,
    )

    bundles = BundleStore(tmp_path)
    operation = "c" * 64
    scope = WorkspaceScope("tenant", "source", "agent", service_unit_id="svc")
    body = {"id": "message"}
    entry = {
        "sequence": 1,
        "raw_id": "message",
        "layer": "archive",
        "source_occurrence": 0,
        "source_occurrence_no": 0,
        "visible": True,
        "body": {
            "publication_id": "self",
            "block_name": "message_bodies",
            "position": 0,
        },
    }
    index = bundles.publish(
        operation,
        [
            BundleBlock(
                "message_directory",
                "message_directory",
                encode_message_directory([entry]),
            ),
            BundleBlock(
                "message_bodies",
                "message_bodies",
                encode_message_bodies([body]),
            ),
        ],
        scope=scope,
        metadata={"operation_key": operation},
    )
    opened = []
    original = bundles.open_reader

    @contextmanager
    def counted(*args, **kwargs):
        opened.append(args)
        with original(*args, **kwargs) as reader:
            yield reader

    monkeypatch.setattr(bundles, "open_reader", counted)
    directory, bodies = read_archive_chunk(
        bundles,
        {
            "relative_path": index.relative_path,
            "byte_length": index.byte_length,
        },
        "message_directory",
        include_bodies=True,
        allowance=64 * 1024 * 1024,
    )
    assert directory[0]["sequence"] == 1
    assert directory[0]["category"] == "archive"
    assert bodies == (body,)
    assert len(opened) == 1


async def test_fast_archive_dependency_requires_scoped_active_retention():
    from unittest.mock import AsyncMock

    scope = WorkspaceScope("tenant", "source", "agent", service_unit_id="svc")
    publication = {"id": 5, **scope.fields}
    archive = ({"chunks": [{"publication_id": 4}]}, {})
    assignments = {4: scope.values}
    database = SimpleNamespace(
        fetch_all=AsyncMock(
            return_value=[
                {
                    "publication_id": 4,
                    "member_key": 4,
                    "retention_key": b"dep:5",
                    **scope.fields,
                },
            ],
        ),
    )
    await _verify_archive_dependencies(
        database,
        publication,
        archive,
        assignments,
    )
    database.fetch_all.return_value = []
    with pytest.raises(IntegrityError, match="retention"):
        await _verify_archive_dependencies(
            database,
            publication,
            archive,
            assignments,
        )
    assignments[4] = ("svc", "other", "source", "agent")
    with pytest.raises(IntegrityError, match="ownership"):
        await _verify_archive_dependencies(
            database,
            publication,
            archive,
            assignments,
        )


async def test_fast_archive_reads_are_batched_and_bounded(monkeypatch):
    scope = WorkspaceScope("tenant", "source", "agent", service_unit_id="svc")
    identifiers = tuple(range(1000, 1130))
    assignments = {}
    rows = {}
    for identifier in identifiers:
        operation = f"{identifier:064x}"
        assignment = {
            "target_id": identifier,
            "scope_kind": "workspace",
            "scope": scope.values,
            "operation_key": operation,
            "relative_path": BundleStore.path_for(operation, scope),
        }
        assignments[identifier] = assignment
        rows[identifier] = {
            "id": identifier,
            "scope_kind": "workspace",
            "operation_key": operation.encode(),
            "relative_path": assignment["relative_path"],
            "byte_length": 100,
            "state": "committed",
            "gc_state": "live",
            "durable_at": True,
            **scope.fields,
        }

    sql_batches = []

    async def fetch_all(_query, params):
        sql_batches.append(len(params))
        return [rows[identifier] for identifier in params]

    class FakeIO:
        active = 0
        peak = 0

        async def call(self, function, *args, **kwargs):
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                await asyncio.sleep(0)
                return function(*args, **kwargs)
            finally:
                self.active -= 1

    monkeypatch.setattr(
        "swe.app.conversation_storage.migration.verify_fast."
        "_verify_chunk_directory",
        lambda *_args, **_kwargs: None,
    )
    archive = (
        {
            "epoch": 3,
            "chunks": [
                {"publication_id": identifier} for identifier in identifiers
            ],
        },
        {"chat_id": 7, "archive_first_order": 1},
    )
    io = FakeIO()
    await _verify_archive_chunks(
        SimpleNamespace(fetch_all=fetch_all),
        [(SimpleNamespace(bundles=object()), archive)],
        assignments,
        io,
        64 * 1024 * 1024,
        2,
    )
    assert sql_batches == [128, 2]
    assert io.peak == 2


async def test_fast_archive_dependencies_use_constant_sql_batches():
    scope = WorkspaceScope("tenant", "source", "agent", service_unit_id="svc")
    identifiers = tuple(range(1000, 1130))
    assignments = {identifier: scope.values for identifier in identifiers}
    archives = [
        (
            {"id": 3000 + index, **scope.fields},
            ({"chunks": [{"publication_id": identifier}]}, {}),
        )
        for index, identifier in enumerate(identifiers)
    ]
    sql_batches = []

    async def fetch_all(_query, params):
        sql_batches.append(len(params))
        return [
            {
                "publication_id": 1000
                + int(key.decode().split(":")[1])
                - 3000,
                "member_key": 1000 + int(key.decode().split(":")[1]) - 3000,
                "retention_key": key,
                **scope.fields,
            }
            for key in params
        ]

    await _verify_archive_dependencies_batch(
        SimpleNamespace(fetch_all=fetch_all),
        archives,
        assignments,
    )
    assert sql_batches == [128, 2]


def test_fast_checks_directory_geometry_and_boundary_dependencies():
    from swe.app.conversation_storage.message_bundle import (
        encode_archive_manifest,
        encode_message_bodies,
        encode_message_directory,
    )

    body = {
        "publication_id": "self",
        "block_name": "message_bodies",
        "position": 0,
    }
    entry = {
        "sequence": 1,
        "raw_id": "m",
        "layer": "archive",
        "source_occurrence": 0,
        "source_occurrence_no": 0,
        "visible": True,
        "body": body,
    }
    manifest = {
        "format": "swe.archive-manifest.v1",
        "chat_id": "chat",
        "epoch": 1,
        "first_sequence": 1,
        "last_sequence": 1,
        "chunks": [
            {
                "publication_id": 4,
                "first_sequence": 1,
                "last_sequence": 1,
                "directory_block": "message_directory",
            },
        ],
    }
    payloads = {
        "message_directory": encode_message_directory([entry]),
        "message_bodies": encode_message_bodies([{"id": "m"}]),
        "archive_manifest": encode_archive_manifest(manifest),
    }
    blocks = {
        name: SimpleNamespace(kind=name, length=len(payload), name=name)
        for name, payload in payloads.items()
    }
    reader = SimpleNamespace(
        index=SimpleNamespace(blocks=blocks),
        read_extents=lambda extents, **_: (payloads[extents[0].name],),
    )
    plan = {
        "rows": [],
        "updates": [
            {
                "table": "publications",
                "values": {
                    "id": 5,
                    "archive_first_order": 1,
                    "archive_last_order": 1,
                    "archive_source_count": 1,
                },
            },
        ],
        "dependencies": [4],
    }
    allowance = max(block.length for block in blocks.values())
    _validate_message_blocks(reader, plan, {"id": 5}, allowance)
    entry["source_occurrence_no"] = 1
    payloads["message_directory"] = encode_message_directory([entry])
    with pytest.raises(IntegrityError, match="occurrence"):
        _validate_message_blocks(reader, plan, {"id": 5}, allowance)
    entry["source_occurrence_no"] = 0
    payloads["message_directory"] = encode_message_directory([entry])
    plan["dependencies"] = []
    with pytest.raises(IntegrityError, match="dependencies"):
        _validate_message_blocks(reader, plan, {"id": 5}, allowance)
    plan["dependencies"] = [4]
    body["position"] = 1
    payloads["message_directory"] = encode_message_directory([entry])
    with pytest.raises(IntegrityError, match="locator"):
        _validate_message_blocks(reader, plan, {"id": 5}, allowance)


@pytest.mark.parametrize(
    "change",
    [
        {"session_order": 2},
        {"source_occurrence": 1},
        {"source_occurrence_missing": True},
    ],
)
def test_fast_session_directory_validates_runtime_occurrence_identity(change):
    from swe.app.conversation_storage.message_bundle import (
        encode_message_bodies,
        encode_message_directory,
    )

    entry = {
        "sequence": 1,
        "session_order": 1,
        "raw_id": "m",
        "layer": "memory",
        "source_occurrence": 0,
        "source_occurrence_no": 0,
        "visible": True,
        "body": {
            "publication_id": "self",
            "block_name": "message_bodies",
            "position": 0,
        },
    }
    if change.get("source_occurrence_missing"):
        entry.pop("source_occurrence")
    else:
        entry.update(change)
    payloads = {
        "message_directory": encode_message_directory([entry]),
        "message_bodies": encode_message_bodies([{"id": "m"}]),
    }
    blocks = {
        name: SimpleNamespace(kind=name, length=len(payload), name=name)
        for name, payload in payloads.items()
    }
    reader = SimpleNamespace(
        index=SimpleNamespace(blocks=blocks),
        read_extents=lambda extents, **_: (payloads[extents[0].name],),
    )
    allowance = max(block.length for block in blocks.values())

    with pytest.raises(IntegrityError, match="occurrence"):
        _validate_message_blocks(
            reader,
            {"rows": [], "updates": []},
            {"id": 5},
            allowance,
        )


def test_fast_session_batch_requires_message_blocks():
    blocks = {
        "import_plan": SimpleNamespace(
            kind="import_plan",
            length=1,
            name="import_plan",
        ),
    }
    reader = SimpleNamespace(index=SimpleNamespace(blocks=blocks))

    with pytest.raises(IntegrityError, match="blocks are missing"):
        _validate_message_blocks(
            reader,
            {"rows": [], "updates": []},
            {"id": 5},
            1,
            position="session/messages:0",
        )


from swe.app.conversation_storage.migration.parallel import MigrationIO
from swe.app.conversation_storage.migration.progress import MigrationProgress


def _inputs(
    tmp_path,
    *,
    body=b"body",
    record_plan=False,
    missing_block=False,
    mismatched_pair=False,
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
                            **(
                                {
                                    "checkpoint_offset": {
                                        "block": "offset-checkpoint",
                                        "part": "offset",
                                    },
                                    "checkpoint_length": {
                                        "block": "length-checkpoint",
                                        "part": "length",
                                    },
                                }
                                if mismatched_pair
                                else {
                                    "checkpoint_revision": 2,
                                    "checkpoint_offset": {
                                        "block": "missing-checkpoint",
                                        "part": "offset",
                                    },
                                    "checkpoint_length": {
                                        "block": "missing-checkpoint",
                                        "part": "length",
                                    },
                                }
                            ),
                        }
                        if missing_block
                        else {"id": 1, "checkpoint_revision": 2}
                    ),
                },
            ]
            if record_plan or missing_block or mismatched_pair
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
            BundleBlock("offset-checkpoint", "checkpoint", b"offset"),
            BundleBlock("length-checkpoint", "checkpoint", b"length"),
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
        queries = []

        async def fetch_one(self, query, _params=None):
            assert query == "SELECT DATABASE() AS schema_name"
            return {"schema_name": "test_fast_verify"}

        async def fetch_all(self, query, params=None):
            self.queries.append(query)
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


def test_fast_plan_keeps_default_bundle_memory_limit(tmp_path):
    _database, bundles, manifest, _inventory, row = _inputs(
        tmp_path,
        record_plan=True,
    )
    assignment = manifest.data["assignments"]["publication"]["publication"]
    store = SimpleNamespace(
        bundles=bundles,
        _validate_plan=lambda _plan: None,
        _resolve=lambda *_args: {},
    )

    with pytest.raises(ValueError, match="memory allowance"):
        _read_publication_plan(
            store,
            row,
            assignment,
            manifest.migration_id,
            "test_fast_verify",
            memory_allowance=1,
        )


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
    progress = MigrationProgress(
        "verify",
        manifest.migration_id,
        stream=io.StringIO(),
    )
    with progress.activate():
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
    assert result["excluded_scopes"] == ["historical_shares"]
    assert not any("swe_chat_shares" in query for query in database.queries)
    assert (
        progress.snapshot()["bundle_bytes_read"]
        < bundles.inspect(
            next(bundles.root.rglob("*.bundle"))
            .relative_to(bundles.root)
            .as_posix(),
        ).byte_length
    )


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
async def test_fast_verification_rejects_locator_parts_from_different_blocks(
    tmp_path,
):
    _database, bundles, _manifest, _inventory, _row = _inputs(
        tmp_path,
        record_plan=True,
    )
    relative_path = next(bundles.root.rglob("*.bundle")).relative_to(
        bundles.root,
    )
    with bundles.open_reader(relative_path.as_posix()) as reader:
        values = {
            "checkpoint_offset": {
                "block": "offset-checkpoint",
                "part": "offset",
            },
            "checkpoint_length": {
                "block": "length-checkpoint",
                "part": "length",
            },
        }
        resolved = {"checkpoint_offset": 1, "checkpoint_length": 1}
        with pytest.raises(IntegrityError, match="block pair"):
            _validate_locator_pairs(values, resolved, {"id": 1}, reader.index)


@pytest.mark.parametrize(
    "offset_ref,length_ref",
    [
        (4, 8),
        (
            {"block": "offset-checkpoint", "part": "length"},
            {"block": "offset-checkpoint", "part": "offset"},
        ),
        (None, {"block": "offset-checkpoint", "part": "length"}),
    ],
)
def test_fast_verification_rejects_malformed_locator_pair(
    tmp_path,
    offset_ref,
    length_ref,
):
    _database, bundles, _manifest, _inventory, _row = _inputs(
        tmp_path,
        record_plan=True,
    )
    relative_path = next(bundles.root.rglob("*.bundle")).relative_to(
        bundles.root,
    )
    with bundles.open_reader(relative_path.as_posix()) as reader:
        values = {"checkpoint_length": length_ref}
        if offset_ref is not None:
            values["checkpoint_offset"] = offset_ref
        with pytest.raises(IntegrityError, match="block pair"):
            _validate_locator_pairs(
                values,
                {"checkpoint_offset": 1, "checkpoint_length": 1},
                {"id": 1},
                reader.index,
            )


@pytest.mark.asyncio
async def test_fast_verification_rejects_duplicate_bundle_path_assignment(
    tmp_path,
):
    database, bundles, manifest, inventory, _row = _inputs(tmp_path)
    manifest.data["assignments"]["publication"]["duplicate"] = manifest.data[
        "assignments"
    ]["publication"]["publication"]

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
    assert "duplicated" in result["blockers"][0]["detail"]


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


def _message_batch_inputs(tmp_path, batches, *, substitute_body=False):
    from swe.app.conversation_storage.message_bundle import (
        encode_message_bodies,
        encode_message_directory,
    )

    migration_id = str(uuid4())
    bundles = BundleStore(tmp_path / "nas")
    bundles.root.mkdir()
    scope = WorkspaceScope("tenant", "source", "agent", service_unit_id="svc")
    assignments, rows, states = {}, {}, {}
    recovery_directory = []
    recovery_hashes = []
    for identity, (position, entries) in enumerate(batches.items(), start=1):
        operation_key = f"{identity:064x}"
        import_plan = {
            "version": 1,
            "migration_id": migration_id,
            "schema": "test_fast_verify",
            "rows": [],
            "updates": [],
            "locks": {},
        }
        bodies = [
            {
                "id": "message-" + str(entry["sequence"]),
                "role": "user",
                "content": str(entry["sequence"]),
            }
            for entry in entries
        ]
        directory = [
            {
                **entry,
                "raw_id": body["id"],
                "layer": "memory",
                "visible": True,
                "body": {
                    "publication_id": "self",
                    "block_name": "message_bodies",
                    "position": offset,
                },
            }
            for offset, (entry, body) in enumerate(zip(entries, bodies))
        ]
        from hashlib import sha256
        from swe.app.conversation_storage.message_bundle import (
            encode_message_body,
        )

        recovery_hashes.extend(
            sha256(encode_message_body(body)).hexdigest() for body in bodies
        )
        if substitute_body:
            bodies[0]["content"] = "another session's message"
        recovery_directory.extend(
            [
                {
                    **entry,
                    "body": {**entry["body"], "publication_id": identity},
                }
                for entry in directory
            ],
        )
        index = bundles.publish(
            operation_key,
            [
                BundleBlock(
                    "import_plan",
                    "import_plan",
                    json.dumps(import_plan, separators=(",", ":")).encode(),
                ),
                BundleBlock(
                    "message_directory",
                    "message_directory",
                    encode_message_directory(directory),
                ),
                BundleBlock(
                    "message_bodies",
                    "message_bodies",
                    encode_message_bodies(bodies),
                ),
            ],
            scope=scope,
            metadata={"operation_key": operation_key},
        )
        assignments[position] = {
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
            "session_id": 42,
        }
        states[position] = "committed"

    identity = len(rows) + 1
    operation_key = f"{identity:064x}"
    high = len(recovery_directory)
    plan = {
        "version": 1,
        "migration_id": migration_id,
        "schema": "test_fast_verify",
        "rows": [],
        "updates": [
            {"table": "sessions", "values": {"id": 42, "history_high": high}},
        ],
        "locks": {},
    }
    index = bundles.publish(
        operation_key,
        [
            BundleBlock(
                "import_plan",
                "import_plan",
                json.dumps(plan).encode(),
            ),
            BundleBlock(
                "recovery",
                "recovery",
                json.dumps(
                    {
                        "format": "swe-recovery-projection",
                        "version": 1,
                        "state": {},
                        "lists": [],
                        "turns": [],
                        "message_directory": recovery_directory,
                    },
                ).encode(),
            ),
            BundleBlock(
                "message_body_hashes",
                "message_body_hashes",
                json.dumps(recovery_hashes).encode(),
            ),
        ],
        scope=scope,
        metadata={"operation_key": operation_key},
    )
    assignments["session/recovery"] = {
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
        "session_id": 42,
    }
    states["session/recovery"] = "committed"

    class Database:
        publication_rows = rows
        max_allowed_packet = 16 * 1024 * 1024

        def acquire(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def fetch_all(self, _query, params):
            if "swe_conversation_sessions" in _query:
                return [
                    {
                        "id": 42,
                        "history_high": high,
                        "service_unit_key": b"svc",
                    },
                ]
            return [rows[identity] for identity in params]

    manifest = SimpleNamespace(
        migration_id=migration_id,
        data={
            "assignments": {
                "publication": assignments,
                "session": {"session": {"target_id": 42}},
            },
            "batches": states,
            "target": {"schema": "test_fast_verify"},
        },
    )
    return Database(), bundles, manifest


async def _run_fast_message_batches(database, bundles, manifest, **options):
    async with MigrationIO(2) as io:
        return await verify_fast_publications(
            database,
            {"svc": bundles},
            manifest,
            SimpleNamespace(
                schema="test_fast_verify",
                migration_id=manifest.migration_id,
            ),
            io=io,
            io_workers=2,
            memory_bytes=16 * 1024 * 1024,
            **options,
        )


@pytest.mark.parametrize("damage", [None, "format", "body"])
async def test_fast_legacy_bundle_requires_matching_frozen_bodies(
    tmp_path,
    monkeypatch,
    damage,
):
    from hashlib import sha256
    from swe.app.conversation_storage.message_bundle import encode_message_body

    publish = BundleStore.publish
    expected = []

    def without_hashes(store, key, blocks, **kwargs):
        retained = []
        for block in blocks:
            if block.name == "message_body_hashes":
                expected.extend(json.loads(block.content))
                continue
            if damage == "format" and block.name == "recovery":
                envelope = json.loads(block.content)
                del envelope["format"]
                block = BundleBlock(
                    block.name,
                    block.kind,
                    json.dumps(envelope).encode(),
                )
            retained.append(block)
        return publish(store, key, retained, **kwargs)

    monkeypatch.setattr(BundleStore, "publish", without_hashes)
    batches = {
        "session/messages:0": [
            {"sequence": 1, "source_occurrence": 0, "source_occurrence_no": 0},
        ],
    }
    database, bundles, manifest = _message_batch_inputs(tmp_path, batches)
    if damage == "body":
        expected[:] = [
            sha256(encode_message_body({"id": "different"})).hexdigest(),
        ]
    verify = _run_fast_message_batches(
        database,
        bundles,
        manifest,
        frozen_hashes=lambda _: expected,
    )
    if damage:
        with pytest.raises(
            IntegrityError,
            match="projection envelope|batch body differs",
        ):
            await verify
    else:
        assert (await verify)["publications"] == 2
        with pytest.raises(IntegrityError, match="frozen source evidence"):
            await _run_fast_message_batches(database, bundles, manifest)


async def test_fast_session_message_batches_accept_global_occurrences(
    tmp_path,
):
    batches = {
        "session/messages:0": [
            {
                "sequence": 1,
                "session_order": 1,
                "source_occurrence": 0,
                "source_occurrence_no": 0,
            },
            {
                "sequence": 2,
                "session_order": 2,
                "source_occurrence": 1,
                "source_occurrence_no": 1,
            },
        ],
        "session/messages:2": [
            {
                "sequence": 3,
                "session_order": 3,
                "source_occurrence": 2,
                "source_occurrence_no": 2,
            },
        ],
    }
    database, bundles, manifest = _message_batch_inputs(tmp_path, batches)

    result = await _run_fast_message_batches(database, bundles, manifest)

    assert result["publications"] == 3


@pytest.mark.parametrize(
    "batches",
    [
        {
            "session/messages:1": [
                {"sequence": 2, "session_order": 2},
            ],
        },
        {
            "session/messages:0": [
                {"sequence": 1, "session_order": 1},
            ],
            "session/messages:1": [
                {"sequence": 1, "session_order": 1},
            ],
        },
        {
            "session/messages:0": [
                {"sequence": 1, "session_order": 1},
            ],
            "session/messages:2": [
                {"sequence": 3, "session_order": 3},
            ],
        },
    ],
)
async def test_fast_session_message_batches_require_global_occurrences(
    tmp_path,
    batches,
):
    for entries in batches.values():
        for entry in entries:
            entry["source_occurrence"] = entry["sequence"] - 1
            entry["source_occurrence_no"] = entry["sequence"] - 1
    _database, bundles, manifest = _message_batch_inputs(tmp_path, batches)

    with pytest.raises(IntegrityError, match="occurrence|order"):
        await _run_fast_message_batches(_database, bundles, manifest)


async def _empty_rows():
    return []


async def test_fast_rejects_missing_last_message_batch(tmp_path):
    batches = {
        f"session/messages:{i}": [
            {
                "sequence": i + 1,
                "session_order": i + 1,
                "source_occurrence": i,
                "source_occurrence_no": i,
            },
        ]
        for i in range(2)
    }
    database, bundles, manifest = _message_batch_inputs(tmp_path, batches)
    del manifest.data["assignments"]["publication"]["session/messages:1"]
    with pytest.raises(IntegrityError, match="history high"):
        await _run_fast_message_batches(database, bundles, manifest)


async def test_fast_rejects_message_publication_from_another_session(tmp_path):
    batches = {
        "session/messages:0": [
            {
                "sequence": 1,
                "session_order": 1,
                "source_occurrence": 0,
                "source_occurrence_no": 0,
            },
        ],
    }
    database, bundles, manifest = _message_batch_inputs(tmp_path, batches)
    database.publication_rows[1]["session_id"] = 43
    with pytest.raises(IntegrityError, match="association"):
        await _run_fast_message_batches(database, bundles, manifest)


def test_fast_classifies_only_direct_session_message_positions():
    from swe.app.conversation_storage.migration.verify_fast import (
        _session_message_batch,
    )

    sessions = {"session": 42}
    assert _session_message_batch("session/messages:0", sessions) == (
        "session",
        0,
    )
    assert (
        _session_message_batch(
            "artifact/source-artifact:0/messages:0",
            sessions,
        )
        is None
    )
    assert (
        _session_message_batch("session/turn:abc/messages:0", sessions) is None
    )
    assert (
        _session_message_batch("session/turn:abc/messages:bad", sessions)
        is None
    )


def test_fast_rejects_directory_from_another_session():
    from swe.app.conversation_storage.migration.verify_fast import (
        _validate_message_batch_spans,
    )

    with pytest.raises(IntegrityError, match="recovery directory"):
        _validate_message_batch_spans(
            {"session": [(0, 1, [b"other"], ["body"])]},
            {"session": (1, [b"expected"], ["body"])},
            {"session": 42},
        )


async def test_fast_rejects_replaced_message_body_with_same_directory(
    tmp_path,
):
    batches = {
        "session/messages:0": [
            {
                "sequence": 1,
                "session_order": 1,
                "source_occurrence": 0,
                "source_occurrence_no": 0,
            },
        ],
    }
    database, bundles, manifest = _message_batch_inputs(
        tmp_path,
        batches,
        substitute_body=True,
    )
    with pytest.raises(IntegrityError, match="body differs"):
        await _run_fast_message_batches(database, bundles, manifest)
