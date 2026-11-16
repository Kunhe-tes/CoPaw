# -*- coding: utf-8 -*-
"""在单 SQL owner 内按有界块分配身份持久票据。"""

from datetime import datetime, timezone
import json
import re

from ....database.prepared import PreparedInsert
from ..bundle import BundleStore, new_operation_key

TABLE = "swe_conversation_migration_entries"
INSERT = PreparedInsert(
    "INSERT INTO "
    + TABLE
    + " (migration_id,entry_kind,source_key,operation_key,state,details_text,created_at,updated_at) VALUES ",
    "(%s,%s,%s,%s,%s,%s,%s,%s)",
)
MAX_ROWS = 100
MAX_BYTES = 256 * 1024


def chunks(packet, keys, *, extra_bytes=0):
    """同时限制行数、参数字节和服务器 packet 安全预算。"""
    budget = min(MAX_BYTES, packet - 1024, packet * 9 // 10)
    pending, used = [], 1024
    for position, key in keys:
        # 包含控制表字段、操作身份及 prepared 协议的保守开销。
        size = len(key) + 512 + extra_bytes
        if size + 1024 > budget:
            raise ValueError("ticket row exceeds max_allowed_packet budget")
        if pending and (len(pending) >= MAX_ROWS or used + size > budget):
            yield pending
            pending, used = [], 1024
        pending.append((position, key))
        used += size
    if pending:
        yield pending


async def allocate_chunk(
    journal,
    kind,
    chunk,
    *,
    scope=None,
    scope_kind="workspace",
):
    """完整唯一键读回真实 ID，事务成功前不修改镜像。"""
    database = journal.db
    migration = journal.migration_id
    kind_key = kind.encode()
    keys = [key for _, key in chunk]
    params = (migration, kind_key, *keys)
    condition = (
        " WHERE migration_id=%s AND entry_kind=%s AND source_key IN ("
        + ",".join("%s" for _ in keys)
        + ")"
    )

    async def read():
        rows = await database.fetch_all(
            "SELECT * FROM " + TABLE + condition + " FOR UPDATE",
            params,
        )
        mapped = {}
        for row in rows:
            key = row["source_key"]
            if isinstance(key, str):
                key = key.encode()
            if (
                key not in keys
                or key in mapped
                or row["migration_id"] != migration
                or row["entry_kind"] != kind_key
            ):
                raise ValueError("SQL journal ticket identity mismatch")
            mapped[key] = row
        return mapped

    def details(operation):
        if kind != "publication":
            return None
        return json.dumps(
            {
                "scope": list(scope.values),
                "scope_kind": scope_kind,
                "relative_path": BundleStore.path_for(
                    operation,
                    scope,
                    scope_kind=scope_kind,
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    def assignment(row):
        operation = row["operation_key"]
        operation = (
            operation.decode() if isinstance(operation, bytes) else operation
        )
        if not isinstance(operation, str) or not re.fullmatch(
            r"[0-9a-f]{64}",
            operation,
        ):
            raise ValueError("SQL journal ticket operation key is invalid")
        if kind == "publication" and row.get("details_text") is not None:
            stored = row["details_text"]
            stored = stored.decode() if isinstance(stored, bytes) else stored
            if json.loads(stored) != json.loads(details(operation)):
                raise ValueError(
                    "SQL publication ticket scope or path changed",
                )
        return journal._assignment(
            row,
            kind,
            scope=scope,
            scope_kind=scope_kind,
        )

    async with database.transaction():
        rows = await read()
        for row in rows.values():
            assignment(row)
            if kind == "publication" and row.get("details_text") is None:
                value = details(assignment(row)["operation_key"])
                changed = await database.execute(
                    "UPDATE "
                    + TABLE
                    + " SET details_text=%s WHERE migration_id=%s AND id=%s AND details_text IS NULL",
                    (value, migration, row["id"]),
                )
                if changed != 1:
                    raise ValueError(
                        "SQL publication ticket scope backfill lost a race",
                    )
                row["details_text"] = value
        missing = [key for key in keys if key not in rows]
        if missing:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            operations = {key: new_operation_key().encode() for key in missing}
            await database.insert_prepared(
                INSERT,
                (
                    (
                        migration,
                        kind_key,
                        key,
                        operations[key],
                        "mapped",
                        details(operations[key].decode()),
                        now,
                        now,
                    )
                    for key in missing
                ),
                max_rows=MAX_ROWS,
                max_bytes=MAX_BYTES,
            )
            rows = await read()
            if set(rows) != set(keys) or any(
                rows[key]["operation_key"] != operations[key]
                or rows[key]["target_id"] is not None
                for key in missing
            ):
                raise ValueError(
                    "SQL journal inserted ticket identity mismatch",
                )
            await database.execute(
                "UPDATE "
                + TABLE
                + " SET target_id=id"
                + condition
                + " AND target_id IS NULL",
                params,
            )
            rows = await read()
        if set(rows) != set(keys):
            raise ValueError("SQL journal ticket mapping is incomplete")
        assignments = {
            position: assignment(rows[key]) for position, key in chunk
        }
        mirror = journal.manifest.data["assignments"].get(kind, {})
        if any(
            position in mirror and mirror[position] != value
            for position, value in assignments.items()
        ):
            raise ValueError(
                "manifest has no matching durable SQL ticket mapping",
            )
    return assignments
