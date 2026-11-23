# -*- coding: utf-8 -*-
"""Fast structural checks for committed migration publications."""

import asyncio
import json
import hashlib
from functools import partial
from itertools import islice

from ..bundle import BundleStore
from ..chat_mutations import load_metadata_json
from ..errors import IntegrityError
from ..identity import WorkspaceScope
from ..message_bundle import (
    decode_archive_manifest,
    decode_message_bodies,
    decode_message_directory,
    encode_message_directory,
    encode_message_body,
    validate_runtime_occurrences,
)
from ..reference_queries import ReferenceQuery, iter_reference_rows
from ..session_projection import validate_projection_structure
from .archive_verification import (
    PUBLICATION_FIELDS,
    fetch_publications,
    read_archive_chunk,
    run_bounded_io,
)
from .install_records import (
    IMMUTABLE,
    VERIFY_QUERIES,
    OfflineImportStore,
)
from .disk_manifest import DiskMap

MESSAGE_BATCH_MARKER = "/messages:"


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


def _read_recovery_hashes(reader, memory_allowance):
    hashes_extent = reader.index.blocks.get("message_body_hashes")
    if (
        hashes_extent is not None
        and hashes_extent.kind != "message_body_hashes"
    ):
        raise IntegrityError(
            "session recovery message body hashes are missing",
        )
    body_hashes = (
        None
        if hashes_extent is None
        else load_metadata_json(
            _read_checked(reader, hashes_extent, memory_allowance),
        )
    )
    if hashes_extent is not None and (
        not isinstance(body_hashes, list)
        or any(
            not isinstance(value, str) or len(value) != 64
            for value in body_hashes
        )
    ):
        raise IntegrityError(
            "session recovery message body hashes are invalid",
        )
    return body_hashes


def _read_publication_plan(
    store,
    row,
    assignment,
    migration_id,
    schema,
    memory_allowance,
    *,
    position=None,
    message_batch=None,
    session_id=None,
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
        if (
            not store.bundles.unbounded
            and extent.length * 8 > memory_allowance
        ):
            raise ValueError("fast verification plan exceeds memory allowance")
        raw = reader.read_extents(
            (extent,),
            max_bytes=(
                store.bundles.max_read_bytes
                if store.bundles.unbounded
                else memory_allowance
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
        archive, message_span = _validate_message_blocks(
            reader,
            plan,
            row,
            memory_allowance,
            position=position if message_batch is None else None,
            batch=message_batch,
        )
        recovery = None
        if (
            session_id is not None
            and position is not None
            and position.endswith("/recovery")
        ):
            updates = [
                item["values"]
                for item in plan["updates"]
                if item["table"] == "sessions"
                and item["values"].get("id") == session_id
                and "history_high" in item["values"]
            ]
            extent = reader.index.blocks.get("recovery")
            if (
                len(updates) != 1
                or extent is None
                or extent.kind != "recovery"
            ):
                raise IntegrityError("session recovery evidence is missing")
            envelope = load_metadata_json(
                _read_checked(reader, extent, memory_allowance),
            )
            validate_projection_structure(envelope, named_references=True)
            directory = envelope.get("message_directory")
            if not isinstance(directory, list):
                raise IntegrityError(
                    "session recovery message directory is missing",
                )
            body_hashes = _read_recovery_hashes(reader, memory_allowance)
            recovery = (
                updates[0]["history_high"],
                _directory_hashes(
                    decode_message_directory(
                        encode_message_directory(directory),
                    ),
                ),
                body_hashes,
            )
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
        return (
            expected,
            len(plan["rows"]),
            len(plan["updates"]),
            archive,
            message_span,
            recovery,
        )


def _validate_message_blocks(
    reader,
    plan,
    publication,
    allowance,
    *,
    position=None,
    batch=None,
):
    blocks = reader.index.blocks
    directory = blocks.get("message_directory")
    bodies = blocks.get("message_bodies")
    batch = batch if batch is not None else _message_batch(position)
    if batch is not None and (directory is None or bodies is None):
        raise IntegrityError("session message batch blocks are missing")
    message_span = None
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
        validate_runtime_occurrences(entries)
        if batch is not None:
            prefix, start = batch
            if not entries or entries[0]["sequence"] != start + 1:
                raise IntegrityError(
                    "session message batch occurrence start differs",
                )
            normalized = [
                {
                    **entry,
                    "body": {
                        **entry["body"],
                        "publication_id": publication["id"],
                    },
                }
                for entry in entries
            ]
            message_span = (
                prefix,
                start,
                len(entries),
                _directory_hashes(normalized),
                [
                    hashlib.sha256(encode_message_body(body)).hexdigest()
                    for body in messages
                ],
            )
        for offset, entry in enumerate(entries):
            if entry["body"] != {
                "publication_id": "self",
                "block_name": "message_bodies",
                "position": offset,
            }:
                raise IntegrityError("message directory body locator differs")
            source_occurrence = entry.get("source_occurrence_no")
            if (
                source_occurrence != entry["sequence"] - 1
                or entry.get("source_occurrence") != source_occurrence
            ):
                raise IntegrityError(
                    "message directory occurrence numbering differs",
                )
        if entries and [e["sequence"] for e in entries] != list(
            range(
                entries[0]["sequence"],
                entries[0]["sequence"] + len(entries),
            ),
        ):
            raise IntegrityError("message directory sequence has gaps")
    extent = blocks.get("archive_manifest")
    if extent is None:
        return None, message_span
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
    return (manifest, values), message_span


def _read_checked(reader, extent, allowance):
    if extent.length > allowance:
        raise ValueError(
            "fast verification message block exceeds memory allowance",
        )
    return reader.read_extents((extent,), max_bytes=extent.length)[0]


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


def _batch_scope(position, get_scope):
    scope = _position_scope(position)
    if scope is not None:
        assigned = get_scope(position)
        if assigned is not None and assigned != scope:
            raise IntegrityError(
                "migration batch scope differs from publication assignment",
            )
        return scope
    candidate = position
    while candidate:
        scope = get_scope(candidate)
        if scope is not None:
            return scope
        if "/" not in candidate:
            break
        candidate = candidate.rsplit("/", 1)[0]
    raise IntegrityError("migration batch position is invalid")


def _assignment_scope(position, assignment):
    return _position_scope(position) or tuple(assignment.get("scope", ()))


def _publication_scope(publications, position):
    assignment = publications.get(position)
    return (
        tuple(assignment.get("scope", ())) if assignment is not None else None
    )


def _verification_tickets(manifest, scopes):
    assigned = manifest.data.get("assignments", {})
    publications = assigned.get("publication", {})
    sessions = assigned.get("session", {})
    batches = manifest.data.get("batches", {})
    if scopes is None:
        return publications.items(), sessions.items(), batches.items()
    if all(
        isinstance(mapping, DiskMap) for mapping in (publications, batches)
    ) and (isinstance(sessions, DiskMap) or not sessions):
        get_scope = partial(_publication_scope, publications)
        return (
            publications.grouped_items(scopes, _assignment_scope),
            (
                sessions.grouped_items(scopes, _assignment_scope)
                if isinstance(sessions, DiskMap)
                else ()
            ),
            batches.grouped_items(
                scopes,
                lambda position, _: _batch_scope(position, get_scope),
            ),
        )
    assignment_scopes = {
        position: tuple(assignment.get("scope", ()))
        for position, assignment in publications.items()
    }
    return (
        (
            (position, value)
            for position, value in publications.items()
            if _assignment_scope(position, value) in scopes
        ),
        (
            (position, value)
            for position, value in sessions.items()
            if _position_scope(position) in scopes
        ),
        (
            (position, state)
            for position, state in batches.items()
            if _batch_scope(position, assignment_scopes.get) in scopes
        ),
    )


def _message_batch(position):
    if not isinstance(position, str):
        return None
    marker = position.rfind(MESSAGE_BATCH_MARKER)
    if marker < 0:
        return None
    prefix = position[:marker]
    start_text = position[marker + len(MESSAGE_BATCH_MARKER) :]
    if (
        not prefix
        or not start_text.isascii()
        or not start_text.isdigit()
        or str(int(start_text)) != start_text
    ):
        raise IntegrityError("session message batch position is invalid")
    return prefix, int(start_text)


def _session_message_batch(position, sessions):
    marker = position.rfind(MESSAGE_BATCH_MARKER)
    if marker < 0 or position[:marker] not in sessions:
        return None
    return _message_batch(position)


def _directory_hashes(entries):
    return [
        hashlib.sha256(
            json.dumps(
                entry,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode(),
        ).hexdigest()
        for entry in entries
    ]


def _validate_message_batch_spans(
    spans,
    recoveries,
    sessions,
    frozen_hashes=None,
):
    for position in sessions:
        if position not in recoveries:
            raise IntegrityError("session recovery evidence is missing")
        high, directory, body_hashes = recoveries[position]
        expected = 0
        hashes = []
        actual_body_hashes = []
        for start, count, batch_hashes, batch_body_hashes in sorted(
            spans.get(position, []),
        ):
            if start != expected:
                raise IntegrityError("session message batch order differs")
            expected += count
            hashes.extend(batch_hashes)
            actual_body_hashes.extend(batch_body_hashes)
        if type(high) is not int or expected != high or len(directory) != high:
            raise IntegrityError("session message batch history high differs")
        if hashes != directory:
            raise IntegrityError(
                "session message batch recovery directory differs",
            )
        if body_hashes is None:
            if frozen_hashes is None:
                raise IntegrityError(
                    "old session recovery requires frozen source evidence",
                )
            body_hashes = frozen_hashes(position)
        if actual_body_hashes != body_hashes:
            raise IntegrityError(
                "session message batch body differs from recovery",
            )


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
    frozen_hashes=None,
    expected_sessions=None,
):
    publications, session_assignments, relevant_batches = (
        _verification_tickets(
            manifest,
            expected_scopes,
        )
    )
    sessions = {
        position: assignment["target_id"]
        for position, assignment in session_assignments
    }
    if len(set(sessions.values())) != len(sessions):
        raise IntegrityError("duplicate session assignment identity")
    if expected_sessions is not None:
        if set(sessions) != set(expected_sessions):
            raise IntegrityError(
                "session assignment set differs from inventory",
            )
        for position, scope in expected_sessions.items():
            positional = _position_scope(position)
            if positional is not None and positional != tuple(scope):
                raise IntegrityError(
                    "session assignment scope differs from inventory",
                )
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
    message_spans = DiskMap()
    recoveries = DiskMap()
    # A valid message body block can be 8 MiB and decoded JSON needs headroom.
    # Limit concurrent decoders rather than rejecting valid importer output.
    verify_workers = max(
        1,
        min(io_workers, memory_bytes // (64 * 1024 * 1024)),
    )
    allowance = max(1, memory_bytes // verify_workers)
    selected = dict(publications)
    assignments_by_id = {}
    assignment_scopes_by_id = {}
    for position, assignment in selected.items():
        scope = tuple(assignment.get("scope", ()))
        if (
            expected_scopes is not None
            and _assignment_scope(position, assignment) != scope
        ):
            raise IntegrityError(
                "publication assignment scope differs from position",
            )
        path = assignment.get("relative_path")
        if not isinstance(path, str) or path in seen_paths:
            raise IntegrityError(
                "migration bundle path is missing or duplicated",
            )
        seen_paths.add(path)
        identity = assignment["target_id"]
        if identity in assignments_by_id:
            raise IntegrityError("duplicate committed publication identity")
        assignments_by_id[identity] = assignment
        assignment_scopes_by_id[identity] = scope
    assignments = iter(selected.items())
    while chunk := list(islice(assignments, 128)):
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
            message_batch = _session_message_batch(position, sessions)
            recovery_position = (
                position[: -len("/recovery")]
                if position.endswith("/recovery")
                else None
            )
            owner = message_batch[0] if message_batch else recovery_position
            session_id = sessions.get(owner)
            if session_id is not None and row.get("session_id") != session_id:
                raise IntegrityError("session publication association differs")
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
            checks.append(
                (position, store, row, assignment, message_batch, session_id),
            )

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
                        position=(
                            position if message_batch or session_id else None
                        ),
                        message_batch=message_batch,
                        session_id=session_id,
                    )
                    for position, store, row, assignment, message_batch, session_id in batch
                ),
            )
            expected_by_table = {}
            archive_checks = []
            for check, result in zip(batch, results):
                service_unit_key = check[2]["service_unit_key"]
                (
                    expected,
                    rows_count,
                    updates_count,
                    archive,
                    message_span,
                    recovery,
                ) = result
                checked_rows += rows_count
                checked_updates += updates_count
                if message_span is not None:
                    prefix, start, count, hashes, body_hashes = message_span
                    message_spans[json.dumps([prefix, start])] = {
                        "session": prefix,
                        "span": [start, count, hashes, body_hashes],
                    }
                if recovery is not None:
                    recoveries[check[0][: -len("/recovery")]] = recovery
                if archive is not None:
                    archive_checks.append((check, archive))
                _merge_expected_rows(
                    expected_by_table,
                    service_unit_key,
                    expected,
                )
            if archive_checks:
                await _verify_archive_dependencies_batch(
                    database,
                    ((check[2], archive) for check, archive in archive_checks),
                    assignment_scopes_by_id,
                )
                await _verify_archive_chunks(
                    database,
                    ((check[1], archive) for check, archive in archive_checks),
                    assignments_by_id,
                    io,
                    allowance,
                    verify_workers,
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
    sessions_by_service = {}
    for position, identity in sessions.items():
        assignment = selected.get(position + "/recovery")
        if assignment is None:
            raise IntegrityError("session recovery evidence is missing")
        scope = tuple(assignment["scope"])
        if expected_sessions is not None and scope != tuple(
            expected_sessions[position],
        ):
            raise IntegrityError(
                "session assignment scope differs from inventory",
            )
        sessions_by_service.setdefault(scope[0].encode(), {})[
            identity
        ] = position
    for service, identities in sessions_by_service.items():
        async for requested, rows in iter_reference_rows(
            database,
            ReferenceQuery.MIGRATION_SESSION_HIGH,
            identities,
            service,
        ):
            for identity in requested:
                position = identities[identity]
                row = rows.get(identity)
                if (
                    row is None
                    or type(row.get("history_high")) is not int
                    or position not in recoveries
                    or row["history_high"] != recoveries[position][0]
                ):
                    raise IntegrityError(
                        "session database history high differs",
                    )
    try:
        for position, identity in sessions.items():
            spans = [
                value["span"]
                for _, value in message_spans.grouped_items(
                    [position],
                    lambda _key, value: value["session"],
                )
            ]
            _validate_message_batch_spans(
                {position: spans},
                (
                    {position: recoveries[position]}
                    if position in recoveries
                    else {}
                ),
                {position: identity},
                frozen_hashes,
            )
    finally:
        message_spans.close()
        recoveries.close()
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
    await _verify_archive_dependencies_batch(
        database,
        ((publication, archive),),
        assignments,
    )


async def _verify_archive_dependencies_batch(
    database,
    entries,
    assignments,
):
    expected_by_key = {}
    for publication, archive in entries:
        manifest, _ = archive
        expected = {
            chunk["publication_id"]
            for chunk in manifest["chunks"]
            if chunk["publication_id"] != "self"
        }
        scope = WorkspaceScope.from_row(publication)
        if any(
            WorkspaceScope.from_values(assignments.get(identity, ())) != scope
            for identity in expected
            if identity in assignments
        ) or any(identity not in assignments for identity in expected):
            raise IntegrityError("archive chunk source ownership differs")
        key = f"dep:{publication['id']}".encode("ascii")
        expected_by_key[key] = (publication, scope, expected)

    keys = tuple(expected_by_key)
    rows_by_key = {key: [] for key in keys}
    for start in range(0, len(keys), 128):
        batch = keys[start : start + 128]
        found = await database.fetch_all(
            "SELECT publication_id,member_key,service_unit_key,tenant_key,"
            "source_key,agent_key,retention_key "
            "FROM swe_conversation_retentions "
            "WHERE retention_key IN ("
            + ",".join(["%s"] * len(batch))
            + ") AND kind='dependency' AND state='active'",
            batch,
        )
        for row in found:
            key = row["retention_key"]
            if isinstance(key, str):
                key = key.encode()
            rows_by_key.setdefault(key, []).append(row)

    for key in keys:
        publication, scope, expected = expected_by_key[key]
        rows = rows_by_key.get(key, ())
        if WorkspaceScope.from_row(publication) != scope:
            raise IntegrityError("archive boundary source ownership differs")
        if any(WorkspaceScope.from_row(row) != scope for row in rows):
            raise IntegrityError("archive retention source ownership differs")
        if {row["publication_id"] for row in rows} != expected or any(
            row["member_key"] != row["publication_id"] for row in rows
        ):
            raise IntegrityError("archive retention dependencies differ")


def _archive_chunk_plan(manifest, values):
    return {
        chunk["publication_id"]: (
            chunk,
            values["chat_id"],
            manifest["epoch"],
        )
        for chunk in manifest["chunks"]
        if chunk["publication_id"] != "self"
    }


async def _verify_archive_chunks(
    database,
    checks,
    assignments,
    io,
    allowance,
    workers,
):
    plans = []
    identifiers = []
    for store, archive in checks:
        manifest, values = archive
        plan = _archive_chunk_plan(manifest, values)
        plans.append((store, plan))
        identifiers.extend(plan)
    rows = await fetch_publications(database, identifiers)
    calls = []
    for store, plan in plans:
        for identifier, (
            chunk,
            chat_id,
            epoch,
        ) in plan.items():
            assignment = assignments.get(identifier)
            row = rows.get(identifier)
            if assignment is None or row is None:
                raise IntegrityError(
                    "archive chunk publication is missing",
                )
            _publication_identity(row, assignment)
            calls.append(
                partial(
                    _verify_chunk_directory,
                    store,
                    row,
                    assignment,
                    chunk,
                    chat_id,
                    epoch,
                    allowance,
                ),
            )
    await run_bounded_io(io, calls, workers)


def _verify_chunk_directory(
    store,
    publication,
    assignment,
    chunk,
    chat_id,
    epoch,
    allowance,
):
    entries, _ = read_archive_chunk(
        store.bundles,
        publication,
        chunk["directory_block"],
        include_bodies=False,
        allowance=allowance,
        expected_operation_key=assignment["operation_key"],
    )
    first, last = chunk["first_sequence"], chunk["last_sequence"]
    if len(entries) != last - first + 1 or any(
        entry["sequence"] != first + position
        or entry.get("source_occurrence_no") != first + position - 1
        or entry.get("source_occurrence") != entry.get("source_occurrence_no")
        or entry.get("chat_id") != chat_id
        or entry.get("epoch") != epoch
        for position, entry in enumerate(entries)
    ):
        raise IntegrityError("archive chunk range or association differs")
