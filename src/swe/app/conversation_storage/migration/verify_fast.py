# -*- coding: utf-8 -*-
"""Fast structural checks for committed migration publications."""

import asyncio
import json
from itertools import islice

from ..bundle import MAX_READ_BYTES, BundleStore
from ..chat_mutations import load_metadata_json
from ..errors import IntegrityError
from ..identity import WorkspaceScope
from ..message_bundle import (
    decode_archive_manifest,
    decode_message_bodies,
    decode_message_directory,
)
from ..reference_queries import iter_reference_rows
from .install_records import (
    IMMUTABLE,
    VERIFY_QUERIES,
    OfflineImportStore,
)

PUBLICATION_FIELDS = (
    "id,scope_kind,service_unit_key,tenant_key,source_key,agent_key,"
    "operation_key,relative_path,byte_length,state,gc_state,durable_at"
)


def _publication_identity(row, assignment):
    actual = (
        row["id"],
        row["scope_kind"],
        row["operation_key"].decode("ascii"),
        BundleStore.validate_publication_locator(row),
        row["state"],
        row["gc_state"],
        bool(row["durable_at"]),
    )
    expected = (
        assignment["target_id"],
        assignment["scope_kind"],
        assignment["operation_key"],
        assignment["relative_path"],
        "committed",
        "live",
        True,
    )
    if actual != expected:
        raise IntegrityError("committed publication identity differs")
    if WorkspaceScope.from_values(
        assignment["scope"],
    ) != WorkspaceScope.from_row(
        row,
    ):
        raise IntegrityError("committed publication source ownership differs")


def _read_publication_plan(
    store,
    row,
    assignment,
    migration_id,
    schema,
    memory_allowance,
):
    path = BundleStore.validate_publication_locator(row)
    if path != assignment["relative_path"]:
        raise IntegrityError("committed publication locator differs")
    with store.bundles.open_reader(
        path,
        expected_length=row["byte_length"],
        expected_operation_key=assignment["operation_key"],
    ) as reader:
        extent = reader.index.blocks.get("import_plan")
        if extent is None or extent.kind != "import_plan":
            raise IntegrityError("committed import plan block is missing")
        if not store.bundles.unbounded and extent.length * 8 > min(
            memory_allowance,
            MAX_READ_BYTES * 8,
        ):
            raise ValueError("fast verification plan exceeds memory allowance")
        raw = reader.read_extents(
            (extent,),
            max_bytes=(
                store.bundles.max_read_bytes
                if store.bundles.unbounded
                else min(memory_allowance, MAX_READ_BYTES)
            ),
        )[0]
        plan = load_metadata_json(raw)
        store._validate_plan(plan)
        if (
            plan["migration_id"] != migration_id
            or plan["schema"] != schema
            or reader.index.metadata.get("operation_key")
            != assignment["operation_key"]
        ):
            raise IntegrityError("committed import plan binding differs")
        required_blocks = {"import_plan"}
        expected = {}
        for item in (*plan["rows"], *plan["updates"]):
            values = item["values"]
            resolved = store._resolve(values, row, reader.index)
            _validate_locator_pairs(values, resolved, row, reader.index)
            table_rows = expected.setdefault(item["table"], {})
            if resolved["id"] in table_rows:
                raise IntegrityError(
                    "duplicate offline target mapping identity",
                )
            table_rows[resolved["id"]] = resolved
            for value in values.values():
                if isinstance(value, dict) and set(value) == {"block", "part"}:
                    required_blocks.add(value["block"])
        archive = _validate_message_blocks(reader, plan, row, memory_allowance)
        if not required_blocks.issubset(reader.index.blocks):
            raise IntegrityError(
                "committed publication block set is incomplete",
            )
        if not store.bundles.unbounded:
            record_count = sum(map(len, expected.values()))
            if record_count * 16384 > memory_allowance:
                raise ValueError(
                    "fast verification SQL evidence exceeds memory allowance",
                )
        return expected, len(plan["rows"]), len(plan["updates"]), archive


def _validate_message_blocks(reader, plan, publication, allowance):
    blocks = reader.index.blocks
    directory = blocks.get("message_directory")
    bodies = blocks.get("message_bodies")
    if (directory is None) != (bodies is None):
        raise IntegrityError(
            "message directory and body blocks must be paired",
        )
    if directory is not None:
        if (
            directory.kind != "message_directory"
            or bodies.kind != "message_bodies"
        ):
            raise IntegrityError("message block kind differs")
        entries = decode_message_directory(
            _read_checked(reader, directory, allowance),
        )
        messages = decode_message_bodies(
            _read_checked(reader, bodies, allowance),
        )
        if len(entries) != len(messages):
            raise IntegrityError("message directory and body counts differ")
        for position, entry in enumerate(entries):
            if entry["body"] != {
                "publication_id": "self",
                "block_name": "message_bodies",
                "position": position,
            }:
                raise IntegrityError("message directory body locator differs")
        if entries and [e["sequence"] for e in entries] != list(
            range(
                entries[0]["sequence"],
                entries[0]["sequence"] + len(entries),
            ),
        ):
            raise IntegrityError("message directory sequence has gaps")
    extent = blocks.get("archive_manifest")
    if extent is None:
        return None
    if extent.kind != "archive_manifest":
        raise IntegrityError("archive manifest block kind differs")
    manifest = decode_archive_manifest(
        _read_checked(reader, extent, allowance),
    )
    updates = [
        item["values"]
        for item in (*plan["rows"], *plan["updates"])
        if item["table"] == "publications"
        and item["values"].get("id") == publication["id"]
        and "archive_first_order" in item["values"]
    ]
    if len(updates) != 1:
        raise IntegrityError("archive manifest publication plan is missing")
    values = updates[0]
    if (
        manifest["first_sequence"] != values["archive_first_order"]
        or manifest["last_sequence"] != values["archive_last_order"]
        or manifest["last_sequence"] - manifest["first_sequence"] + 1
        != values["archive_source_count"]
    ):
        raise IntegrityError("archive manifest publication range differs")
    dependencies = sorted(
        chunk["publication_id"]
        for chunk in manifest["chunks"]
        if chunk["publication_id"] != "self"
    )
    if dependencies != plan.get("dependencies", []):
        raise IntegrityError("archive manifest dependencies differ")
    return manifest, values


def _read_checked(reader, extent, allowance):
    if extent.length * 8 > allowance:
        raise ValueError(
            "fast verification message block exceeds memory allowance",
        )
    return reader.read_extents((extent,), max_bytes=allowance)[0]


def _validate_locator_pairs(values, resolved, publication, index):
    for key in values:
        if key.endswith("_length"):
            offset_key = key[: -len("_length")] + "_offset"
            if offset_key not in values:
                raise IntegrityError("publication locator block pair differs")
    for offset_key, offset_ref in values.items():
        if not offset_key.endswith("_offset"):
            continue
        length_key = offset_key[: -len("_offset")] + "_length"
        length_ref = values.get(length_key)
        if offset_ref is None and length_ref is None:
            continue
        valid_offset = (
            isinstance(offset_ref, dict)
            and set(offset_ref) == {"block", "part"}
            and offset_ref["part"] == "offset"
        )
        valid_length = (
            isinstance(length_ref, dict)
            and set(length_ref) == {"block", "part"}
            and length_ref["part"] == "length"
        )
        if (
            not valid_offset
            or not valid_length
            or offset_ref["block"] != length_ref["block"]
        ):
            raise IntegrityError("publication locator block pair differs")
        block = index.blocks.get(offset_ref["block"])
        offset, length = resolved[offset_key], resolved[length_key]
        _validate_locator_extent(offset, length, block)
        stem = offset_key[: -len("_offset")]
        publication_key = (
            "publication_id" if stem == "byte" else stem + "_publication_id"
        )
        _validate_locator_owner(publication_key, resolved, publication)


def _validate_locator_extent(offset, length, block):
    if block is None or type(offset) is not int or type(length) is not int:
        raise IntegrityError("publication locator exceeds its bundle block")
    if offset < block.offset or length < 0:
        raise IntegrityError("publication locator exceeds its bundle block")
    if offset + length > block.offset + block.length:
        raise IntegrityError("publication locator exceeds its bundle block")


def _validate_locator_owner(publication_key, resolved, publication):
    if publication_key not in resolved:
        return
    if resolved[publication_key] != publication["id"]:
        raise IntegrityError("publication locator owner differs")


def _position_scope(position):
    try:
        identity, _ = json.JSONDecoder().raw_decode(position)
    except (TypeError, ValueError):
        return None
    if isinstance(identity, list) and len(identity) >= 5:
        return tuple(identity[1:5])
    return None


def _batch_scope(position, assignment_scopes):
    scope = _position_scope(position)
    if scope is not None:
        assigned = assignment_scopes.get(position)
        if assigned is not None and assigned != scope:
            raise IntegrityError(
                "migration batch scope differs from publication assignment",
            )
        return scope
    candidate = position
    while candidate:
        scope = assignment_scopes.get(candidate)
        if scope is not None:
            return scope
        if "/" not in candidate:
            break
        candidate = candidate.rsplit("/", 1)[0]
    raise IntegrityError("migration batch position is invalid")


def _merge_expected_rows(expected_by_table, service_unit_key, expected):
    for table, rows in expected.items():
        grouped = expected_by_table.setdefault((service_unit_key, table), {})
        immutable = IMMUTABLE[table]
        for identity, row in rows.items():
            existing = grouped.get(identity)
            if existing is not None and any(
                existing.get(field) != row.get(field)
                for field in immutable
                if field in existing and field in row
            ):
                raise IntegrityError(
                    "conflicting offline target mapping identity",
                )
            grouped[identity] = {**(existing or {}), **row}


# pylint: disable-next=too-many-statements
async def verify_fast_publications(
    database,
    stores,
    manifest,
    target,
    *,
    io,
    io_workers,
    memory_bytes,
    expected_scopes=None,
):
    all_publication_assignments = manifest.data.get("assignments", {}).get(
        "publication",
        {},
    )
    assignment_scopes = {
        position: tuple(assignment.get("scope", ()))
        for position, assignment in all_publication_assignments.items()
    }
    publication_assignments = all_publication_assignments.items()
    if expected_scopes is not None:
        selected = []
        for position, assignment in publication_assignments:
            position_scope = _position_scope(position)
            assignment_scope = tuple(assignment.get("scope", ()))
            if position_scope is not None:
                if position_scope not in expected_scopes:
                    continue
                if assignment_scope != position_scope:
                    raise IntegrityError(
                        "publication assignment scope differs from position",
                    )
            elif assignment_scope not in expected_scopes:
                continue
            selected.append((position, assignment))
        publication_assignments = iter(selected)
    assignments = iter(publication_assignments)
    batches = manifest.data.get("batches", {})
    relevant_batches = batches.items()
    if expected_scopes is not None:
        scoped_batches = []
        for position, state in batches.items():
            scope = _batch_scope(position, assignment_scopes)
            if scope in expected_scopes:
                scoped_batches.append(state)
        relevant_batches = ((None, state) for state in scoped_batches)
    if any(
        state not in ("committed", "verified") for _, state in relevant_batches
    ):
        raise IntegrityError("migration contains an uncommitted import batch")

    stores_by_service = {}
    verified_publications = 0
    checked_rows = 0
    checked_updates = 0
    checked_records = 0
    seen_paths = set()
    # A valid message body block can be 8 MiB and decoded JSON needs headroom.
    # Limit concurrent decoders rather than rejecting valid importer output.
    verify_workers = max(
        1,
        min(io_workers, memory_bytes // (64 * 1024 * 1024)),
    )
    allowance = max(1, memory_bytes // verify_workers)
    assignment_scopes_by_id = {
        assignment["target_id"]: tuple(assignment.get("scope", ()))
        for assignment in all_publication_assignments.values()
    }
    assignments_by_id = {
        assignment["target_id"]: assignment
        for assignment in all_publication_assignments.values()
    }
    while chunk := list(islice(assignments, 128)):
        for _position, assignment in chunk:
            path = assignment.get("relative_path")
            if not isinstance(path, str) or path in seen_paths:
                raise IntegrityError(
                    "migration bundle path is missing or duplicated",
                )
            seen_paths.add(path)
        ids = [assignment["target_id"] for _, assignment in chunk]
        found = await database.fetch_all(
            "SELECT "
            + PUBLICATION_FIELDS
            + " FROM swe_conversation_publications WHERE id IN ("
            + ",".join(["%s"] * len(ids))
            + ")",
            tuple(ids),
        )
        rows = {}
        for row in found:
            if row["id"] in rows:
                raise IntegrityError(
                    "duplicate committed publication identity",
                )
            rows[row["id"]] = row
        if len(rows) != len(ids):
            raise IntegrityError("expected committed publication is missing")
        checks = []
        for position, assignment in chunk:
            row = rows.get(assignment["target_id"])
            if row is None:
                raise IntegrityError(
                    "expected committed publication is missing",
                )
            _publication_identity(row, assignment)
            scope = WorkspaceScope.from_values(assignment["scope"])
            store = stores_by_service.get(scope.service_unit_id)
            if store is None:
                store = OfflineImportStore(
                    database,
                    stores[scope.service_unit_id],
                    target,
                    service_unit_id=scope.service_unit_id,
                )
                stores_by_service[scope.service_unit_id] = store
            checks.append((position, store, row, assignment))

        for start in range(0, len(checks), verify_workers):
            batch = checks[start : start + verify_workers]
            results = await asyncio.gather(
                *(
                    io.call(
                        _read_publication_plan,
                        store,
                        row,
                        assignment,
                        manifest.migration_id,
                        target.schema,
                        allowance,
                    )
                    for _position, store, row, assignment in batch
                ),
            )
            expected_by_table = {}
            for check, result in zip(batch, results):
                service_unit_key = check[2]["service_unit_key"]
                expected, rows_count, updates_count, archive = result
                checked_rows += rows_count
                checked_updates += updates_count
                if archive is not None:
                    await _verify_archive_dependencies(
                        database,
                        check[2],
                        archive,
                        assignment_scopes_by_id,
                    )
                    await _verify_archive_chunks(
                        database,
                        check[1],
                        archive,
                        assignments_by_id,
                        io,
                        allowance,
                    )
                _merge_expected_rows(
                    expected_by_table,
                    service_unit_key,
                    expected,
                )
            batch_records = 0
            for (
                service_unit_key,
                table,
            ), expected in expected_by_table.items():
                if (
                    not store.bundles.unbounded
                    and (batch_records + len(expected)) * 16384 > memory_bytes
                ):
                    raise ValueError(
                        "fast verification SQL evidence exceeds memory allowance",
                    )
                async for identities, actual in iter_reference_rows(
                    database,
                    VERIFY_QUERIES[table],
                    expected,
                    service_unit_key,
                ):
                    for identity in identities:
                        OfflineImportStore._compare_record(
                            table,
                            expected[identity],
                            actual.get(identity),
                        )
                checked_records += len(expected)
                batch_records += len(expected)
        verified_publications += len(chunk)
    return {
        "publications": verified_publications,
        "planned_rows": checked_rows,
        "planned_updates": checked_updates,
        "checked_records": checked_records,
    }


async def _verify_archive_dependencies(
    database,
    publication,
    archive,
    assignments,
):
    archive, _ = archive
    expected = {
        chunk["publication_id"]
        for chunk in archive["chunks"]
        if chunk["publication_id"] != "self"
    }
    scope = WorkspaceScope.from_row(publication).values
    if any(assignments.get(identity) != scope for identity in expected):
        raise IntegrityError("archive chunk source ownership differs")
    rows = await database.fetch_all(
        "SELECT publication_id,member_key FROM swe_conversation_retentions "
        "WHERE service_unit_key=%s AND tenant_key=%s AND source_key=%s "
        "AND agent_key=%s AND retention_key=%s AND kind='dependency' "
        "AND state='active'",
        (
            publication["service_unit_key"],
            publication["tenant_key"],
            publication["source_key"],
            publication["agent_key"],
            f"dep:{publication['id']}".encode("ascii"),
        ),
    )
    if {row["publication_id"] for row in rows} != expected or any(
        row["member_key"] != row["publication_id"] for row in rows
    ):
        raise IntegrityError("archive retention dependencies differ")


async def _verify_archive_chunks(
    database,
    store,
    archive,
    assignments,
    io,
    allowance,
):
    manifest, values = archive
    for chunk in manifest["chunks"]:
        identity = chunk["publication_id"]
        assignment = assignments.get(identity)
        if assignment is None:
            raise IntegrityError("archive chunk publication is missing")
        rows = await database.fetch_all(
            "SELECT "
            + PUBLICATION_FIELDS
            + " FROM swe_conversation_publications WHERE id IN (%s)",
            (identity,),
        )
        if len(rows) != 1:
            raise IntegrityError("archive chunk publication is missing")
        _publication_identity(rows[0], assignment)
        await io.call(
            _verify_chunk_directory,
            store,
            rows[0],
            assignment,
            chunk,
            values["chat_id"],
            manifest["epoch"],
            allowance,
        )


def _verify_chunk_directory(
    store,
    publication,
    assignment,
    chunk,
    chat_id,
    epoch,
    allowance,
):
    with store.bundles.open_reader(
        assignment["relative_path"],
        expected_length=publication["byte_length"],
        expected_operation_key=assignment["operation_key"],
    ) as reader:
        extent = reader.index.blocks.get(chunk["directory_block"])
        if extent is None or extent.kind != "message_directory":
            raise IntegrityError("archive chunk directory is missing")
        entries = decode_message_directory(
            _read_checked(reader, extent, allowance),
        )
        first, last = chunk["first_sequence"], chunk["last_sequence"]
        if len(entries) != last - first + 1 or any(
            entry["sequence"] != first + position
            or entry.get("chat_id") != chat_id
            or entry.get("epoch") != epoch
            for position, entry in enumerate(entries)
        ):
            raise IntegrityError("archive chunk range or association differs")
