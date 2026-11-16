# -*- coding: utf-8 -*-
"""Fast structural checks for committed migration publications."""

import asyncio
from itertools import islice

from ..bundle import MAX_READ_BYTES, BundleStore
from ..chat_mutations import load_metadata_json
from ..errors import IntegrityError
from ..identity import WorkspaceScope
from ..reference_queries import iter_reference_rows
from .install_records import (
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
        if extent.length * 8 > min(memory_allowance, MAX_READ_BYTES * 8):
            raise ValueError(
                "fast verification plan exceeds memory allowance",
            )
        raw = reader.read_extents(
            (extent,),
            max_bytes=min(memory_allowance, MAX_READ_BYTES),
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
            table_rows = expected.setdefault(item["table"], {})
            if resolved["id"] in table_rows:
                raise IntegrityError(
                    "duplicate offline target mapping identity",
                )
            table_rows[resolved["id"]] = resolved
            for value in values.values():
                if isinstance(value, dict) and set(value) == {"block", "part"}:
                    required_blocks.add(value["block"])
        if not required_blocks.issubset(reader.index.blocks):
            raise IntegrityError(
                "committed publication block set is incomplete",
            )
        record_count = sum(map(len, expected.values()))
        if record_count * 16384 > memory_allowance:
            raise ValueError(
                "fast verification SQL evidence exceeds memory allowance",
            )
        return expected, len(plan["rows"]), len(plan["updates"])


async def verify_fast_publications(
    database,
    stores,
    manifest,
    target,
    *,
    io,
    io_workers,
    memory_bytes,
):
    assignments = iter(
        manifest.data.get("assignments", {}).get("publication", {}).items(),
    )
    batches = manifest.data.get("batches", {})
    if any(
        state not in ("committed", "verified") for state in batches.values()
    ):
        raise IntegrityError("migration contains an uncommitted import batch")

    stores_by_service = {}
    verified_publications = 0
    checked_rows = 0
    checked_updates = 0
    checked_records = 0
    allowance = max(1, memory_bytes // max(1, io_workers))
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

        for start in range(0, len(checks), max(1, io_workers)):
            batch = checks[start : start + max(1, io_workers)]
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
                expected, rows_count, updates_count = result
                checked_rows += rows_count
                checked_updates += updates_count
                for table, rows in expected.items():
                    grouped = expected_by_table.setdefault(
                        (service_unit_key, table),
                        {},
                    )
                    if grouped.keys() & rows.keys():
                        raise IntegrityError(
                            "duplicate offline target mapping identity",
                        )
                    grouped.update(rows)
            batch_records = 0
            for (
                service_unit_key,
                table,
            ), expected in expected_by_table.items():
                if (batch_records + len(expected)) * 16384 > memory_bytes:
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
