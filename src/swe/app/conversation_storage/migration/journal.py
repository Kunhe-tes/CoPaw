# -*- coding: utf-8 -*-
"""DML-only authoritative mappings in DBA-precreated control tables."""

import asyncio
import json
import time
from ..bundle import BundleStore, new_operation_key
from ..identity import WorkspaceScope

JOBS = "swe_conversation_migration_jobs"
ENTRIES = "swe_conversation_migration_entries"
HYDRATE_PAGE_SIZE = 1000
TICKET_KINDS = frozenset({"session", "chat", "turn", "message", "publication"})
ENTITY_TABLES = {
    kind: "swe_conversation_" + kind + "s" for kind in TICKET_KINDS
}
BUSINESS_TABLES = (*ENTITY_TABLES.values(), "swe_conversation_retentions")
JOB_TRANSITIONS = {
    "planned": {"importing", "blocked"},
    "importing": {"imported", "blocked"},
    "imported": {"importing", "verified", "blocked"},
    "verified": {"importing", "ready", "blocked"},
    "blocked": {"importing", "imported", "verified"},
    "ready": set(),
}


def _text(value):
    return value.decode() if isinstance(value, bytes) else value


def _json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


class JournalRecovery:
    """Reuse a recovered mirror only inside one locked SQL owner run."""

    def __init__(self, database, manifest):
        self.database = database
        self.manifest = getattr(manifest, "parent", manifest)
        self.owner = asyncio.current_task()
        self.confirmed = None

    def check(self, database, manifest):
        parent = getattr(manifest, "parent", manifest)
        if (
            database is not self.database
            or parent is not self.manifest
            or asyncio.current_task() is not self.owner
        ):
            raise ValueError("SQL journal recovery owner changed")
        return self.confirmed is not None and all(
            manifest.data[name] is mapping
            for name, mapping in zip(
                ("assignments", "batches"),
                self.confirmed,
            )
        )

    def confirm(self, manifest):
        self.confirmed = (
            manifest.data["assignments"],
            manifest.data["batches"],
        )


class MigrationJournal:
    def __init__(
        self,
        database,
        manifest,
        *,
        server_uuid=None,
        recovery=None,
    ):
        if manifest.data.get("version") != 3:
            raise ValueError("SQL journal requires manifest version 3")
        self.db, self.manifest = database, manifest
        self.server_uuid = server_uuid
        self.migration_id = manifest.migration_id.encode()
        self.persist_updates = True
        self._known_scopes = None
        self.active_tenant = None
        self._allocation_owner = None
        self.frozen_bindings_data = None
        self.recovery = recovery

    def _bindings(self):
        data = self.frozen_bindings_data or self.manifest.data
        if data.get("target") is None:
            raise ValueError(
                "migration target must be bound before preparing SQL journal",
            )
        source = {
            key: data[key]
            for key in (
                "source_boundary",
                "services",
                "workspaces",
                "fingerprints",
                "tenant_sync_started_at_ns",
                "shares",
                "discovery_version",
                "tenant_isolation",
                "source_isolation",
                "freshness_protocol",
                "in_place",
                "tenant_review_revision",
                "tenants",
                "source_shares",
                "declared_services",
            )
            if key in data
        }
        target = dict(data["target"])
        if self.server_uuid is not None:
            target["server_uuid"] = self.server_uuid
        started = time.perf_counter()
        result = _json(target), _json(source)
        from .progress import current_progress

        progress = current_progress()
        if progress is not None:
            progress.record_persistence(
                "binding",
                sum(len(value.encode("utf-8")) for value in result),
                time.perf_counter() - started,
            )
        return result

    async def prepare(self):
        target, source = self._bindings()
        await self._require_unpublished_tenant()
        async with self.db.transaction():
            jobs = await self.db.fetch_all(
                "SELECT * FROM " + JOBS + " FOR UPDATE",
            )
            current = next(
                (
                    row
                    for row in jobs
                    if row["migration_id"] == self.migration_id
                ),
                None,
            )
            if any(row["migration_id"] != self.migration_id for row in jobs):
                raise ValueError(
                    "another migration job already owns this application schema",
                )
            if current is None:
                for table in BUSINESS_TABLES:
                    if await self.db.fetch_one(
                        "SELECT id FROM " + table + " LIMIT 1",
                    ):
                        raise ValueError(
                            "first migration requires six empty business tables; unknown rows found",
                        )
                await self.db.execute(
                    "INSERT INTO "
                    + JOBS
                    + " (migration_id,manifest_version,state,target_binding_text,source_binding_text,created_at,updated_at) VALUES (%s,3,'planned',%s,%s,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))",
                    (self.migration_id, target, source),
                )
            elif (
                current["target_binding_text"] != target
                or current["source_binding_text"] != source
                or current["manifest_version"] != 3
            ):
                raise ValueError("migration source or target binding changed")
            elif current["state"] == "ready":
                raise ValueError(
                    "ready migration cannot resume offline import",
                )
        await self.hydrate()
        await self.validate_ownership()
        return current

    async def _require_unpublished_tenant(self):
        if not self.manifest.data.get("tenant_isolation"):
            return
        if self.active_tenant is None:
            raise ValueError("tenant isolation requires an active tenant")
        from .isolation import state_store

        row = await state_store(self.db, self.manifest).get(
            # 租户上下文由编排器注入，pylint 仅推断到初始 None。
            # pylint: disable-next=not-an-iterable
            *self.active_tenant,
        )
        if row is None or row["state"] == "published":
            raise ValueError("unknown or published tenant cannot migrate")

    def _tenant_filter(self, alias=""):
        if not self.manifest.data.get("tenant_isolation"):
            return "", ()
        if self.active_tenant is None:
            raise ValueError("tenant isolation requires an active tenant")
        prefix = alias + "." if alias else ""
        return (
            " AND "
            + prefix
            + "service_unit_key=%s AND "
            + prefix
            + "tenant_key=%s"
            + (
                (" AND " + prefix + "source_key=%s")
                if len(self.active_tenant) == 3
                else ""
            ),
            # pylint: disable-next=not-an-iterable
            tuple(value.encode() for value in self.active_tenant),
        )

    async def validate_ownership(self):
        clause, scope_values = self._tenant_filter("b")
        for kind, table in ENTITY_TABLES.items():
            owned_clause = clause
            if scope_values and kind in ("turn", "message"):
                orphan = await self.db.fetch_one(
                    "SELECT b.id FROM "
                    + table
                    + " b LEFT JOIN swe_conversation_sessions ts"
                    + " ON ts.id=b.session_id AND ts.service_unit_key=b.service_unit_key"
                    + " WHERE ts.id IS NULL LIMIT 1",
                )
                if orphan:
                    raise ValueError("unattributable orphan conversation row")
                owned_clause = (
                    " AND EXISTS (SELECT 1 FROM swe_conversation_sessions ts"
                    " WHERE ts.id=b.session_id AND ts.service_unit_key=b.service_unit_key"
                    " AND ts.service_unit_key=%s AND ts.tenant_key=%s"
                    + (
                        " AND ts.source_key=%s"
                        if len(self.active_tenant) == 3
                        else ""
                    )
                    + ")"
                )
            unknown = await self.db.fetch_one(
                "SELECT b.id FROM "
                + table
                + " b LEFT JOIN "
                + ENTRIES
                + " e ON e.migration_id=%s AND e.entry_kind=%s AND e.target_id=b.id AND e.target_id=e.id WHERE e.id IS NULL"
                + owned_clause
                + " LIMIT 1",
                (self.migration_id, kind.encode(), *scope_values),
            )
            if unknown:
                raise ValueError(
                    "unknown existing business row is not owned by this migration",
                )
        async for row in self._retention_rows():
            await self._validate_retention(row)

    async def _validate_retention(self, row):
        scope_keys = (
            "service_unit_key",
            "tenant_key",
            "source_key",
            "agent_key",
        )
        scope = tuple(row[key] for key in scope_keys)
        if self._known_scopes is None:
            self._known_scopes = {
                tuple(
                    item[key].encode()
                    for key in (
                        "service_unit_id",
                        "tenant_id",
                        "source_id",
                        "agent_id",
                    )
                )
                for item in self.manifest.data["workspaces"]
            }
        legacy = (
            row["scope_kind"] == "legacy_share"
            and not row["source_key"]
            and not row["agent_key"]
            and any(
                item["service_unit_id"].encode() == scope[0]
                and item.get("record", item)["tenant_id"].encode() == scope[1]
                for item in getattr(
                    self.manifest,
                    "parent",
                    self.manifest,
                ).data.get("shares", [])
            )
        )
        if scope not in self._known_scopes and not legacy:
            raise ValueError("unknown retention workspace ownership")
        if row.get("publication_id") is not None:
            owner = await self.db.fetch_one(
                "SELECT p.* FROM swe_conversation_publications p JOIN "
                + ENTRIES
                + " e ON e.target_id=p.id AND e.id=e.target_id WHERE e.migration_id=%s AND e.entry_kind='publication' AND p.id=%s",
                (self.migration_id, row["publication_id"]),
            )
            if owner is None or any(
                owner[key] != row[key] for key in (*scope_keys, "scope_kind")
            ):
                raise ValueError(
                    "retention publication is not owned by this migration scope",
                )
            if row["kind"] == "dependency":
                key = _text(row["retention_key"])
                if not key.startswith("dep:") or not key[4:].isdigit():
                    raise ValueError("invalid retention dependency key")
                source_id = int(key[4:])
                source = await self.db.fetch_one(
                    "SELECT p.* FROM swe_conversation_publications p JOIN "
                    + ENTRIES
                    + " e ON e.target_id=p.id AND e.id=e.target_id WHERE e.migration_id=%s AND e.entry_kind='publication' AND p.id=%s",
                    (self.migration_id, source_id),
                )
                if (
                    source is None
                    or source_id <= row["publication_id"]
                    or any(
                        source[key] != row[key]
                        for key in (*scope_keys, "scope_kind")
                    )
                ):
                    raise ValueError(
                        "retention dependency source is not owned by this migration",
                    )
        elif row["kind"] != "gc_guard":
            raise ValueError("retention without a publication is not a guard")

    @staticmethod
    def _key(kind, position):
        if (
            not isinstance(position, str)
            or not position
            or len(position.encode()) > 2048
        ):
            raise ValueError(
                "stable source key must contain 1 to 2048 UTF-8 bytes",
            )
        return kind.encode(), position.encode()

    async def allocate_many(
        self,
        kind,
        positions,
        *,
        scope=None,
        scope_kind="workspace",
    ):
        """按有界事务分配身份票据；仅在提交确认后更新镜像。"""
        from .batch_tickets import chunks, allocate_chunk
        from .disk_manifest import DiskMap

        if kind not in TICKET_KINDS:
            raise ValueError(
                "only five entity kinds may allocate integer tickets",
            )
        if kind == "publication":
            if scope is None:
                raise ValueError("publication assignment requires its scope")
            BundleStore.path_for("0" * 64, scope, scope_kind=scope_kind)
        elif scope is not None:
            raise ValueError("only publication assignments have bundle scope")
        owner = asyncio.current_task()
        if self._allocation_owner is None:
            self._allocation_owner = owner
        if owner is not self._allocation_owner:
            raise ValueError("SQL journal allocation owner changed")
        positions = list(positions)
        if len(set(positions)) != len(positions):
            raise ValueError("duplicate batch ticket source position")
        keys = [
            (position, self._key(kind, position)[1]) for position in positions
        ]
        if not keys:
            return {}
        # packet 限额来自命名锁固定的物理租约，连接门面本身无此属性。
        async with self.db.acquire() as session:
            packet_limit = session.max_allowed_packet
        result = {}
        extra = len(_json(list(scope.values)).encode()) + 1024 if scope else 0
        for chunk in chunks(packet_limit, keys, extra_bytes=extra):
            assignments = await allocate_chunk(
                self,
                kind,
                chunk,
                scope=scope,
                scope_kind=scope_kind,
            )
            if kind not in self.manifest.data["assignments"]:
                self.manifest.data["assignments"][kind] = (
                    DiskMap()
                    if isinstance(self.manifest.data["batches"], DiskMap)
                    else {}
                )
            self.manifest.data["assignments"][kind].update(assignments)
            if self.persist_updates:
                self.manifest._persist()
            result.update(assignments)
        return result

    async def allocate(
        self,
        kind,
        position,
        *,
        scope=None,
        scope_kind="workspace",
    ):
        if kind not in TICKET_KINDS:
            raise ValueError(
                "only five entity kinds may allocate integer tickets",
            )
        kind_key, key = self._key(kind, position)
        if kind == "publication":
            if scope is None:
                raise ValueError("publication assignment requires its scope")
            scope_values = list(scope.values)
        else:
            if scope is not None:
                raise ValueError(
                    "only publication assignments have bundle scope",
                )
            scope_values = None
        async with self.db.transaction():
            row = await self.db.fetch_one(
                "SELECT * FROM "
                + ENTRIES
                + " WHERE migration_id=%s AND entry_kind=%s AND source_key=%s FOR UPDATE",
                (self.migration_id, kind_key, key),
            )
            if row is None:
                operation = new_operation_key()
                details_text = (
                    _json(
                        {
                            "scope": scope_values,
                            "scope_kind": scope_kind,
                            "relative_path": BundleStore.path_for(
                                operation,
                                scope,
                                scope_kind=scope_kind,
                            ),
                        },
                    )
                    if kind == "publication"
                    else None
                )
                identity = await self.db.insert(
                    "INSERT INTO "
                    + ENTRIES
                    + " (migration_id,entry_kind,source_key,operation_key,state,details_text,created_at,updated_at) VALUES (%s,%s,%s,%s,'mapped',%s,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))",
                    (
                        self.migration_id,
                        kind_key,
                        key,
                        operation.encode(),
                        details_text,
                    ),
                )
                await self.db.execute(
                    "UPDATE "
                    + ENTRIES
                    + " SET target_id=%s WHERE id=%s AND migration_id=%s",
                    (identity, identity, self.migration_id),
                )
                row = {
                    "id": identity,
                    "target_id": identity,
                    "operation_key": operation,
                    "details_text": details_text,
                }
            elif kind == "publication":
                details_text = _json(
                    {
                        "scope": scope_values,
                        "scope_kind": scope_kind,
                        "relative_path": BundleStore.path_for(
                            _text(row["operation_key"]),
                            scope,
                            scope_kind=scope_kind,
                        ),
                    },
                )
                current_details = row.get("details_text")
                if current_details is None:
                    changed = await self.db.execute(
                        "UPDATE "
                        + ENTRIES
                        + " SET details_text=%s WHERE migration_id=%s AND id=%s AND details_text IS NULL",
                        (details_text, self.migration_id, row["id"]),
                    )
                    if changed != 1:
                        current = await self.db.fetch_one(
                            "SELECT details_text FROM "
                            + ENTRIES
                            + " WHERE migration_id=%s AND id=%s",
                            (self.migration_id, row["id"]),
                        )
                        if (
                            current is None
                            or current["details_text"] is None
                            or _text(current["details_text"]) != details_text
                        ):
                            raise ValueError(
                                "SQL publication ticket scope backfill lost a race",
                            )
                    row["details_text"] = details_text
                elif _text(current_details) != details_text:
                    raise ValueError("SQL publication ticket scope changed")
            assignment = self._assignment(
                row,
                kind,
                scope=scope,
                scope_kind=scope_kind,
            )
        from .disk_manifest import DiskMap

        if kind not in self.manifest.data["assignments"]:
            self.manifest.data["assignments"][kind] = (
                DiskMap()
                if isinstance(self.manifest.data["batches"], DiskMap)
                else {}
            )
        self.manifest.data["assignments"][kind][position] = assignment
        if self.persist_updates:
            self.manifest._persist()
        return dict(assignment)

    @staticmethod
    def _assignment(row, kind, *, scope=None, scope_kind="workspace"):
        if (
            type(row["id"]) is not int
            or type(row["target_id"]) is not int
            or row["id"] != row["target_id"]
            or row["target_id"] <= 0
        ):
            raise ValueError("SQL journal integer ticket mapping is invalid")
        operation = _text(row["operation_key"])
        assignment = {
            "target_id": row["target_id"],
            "operation_key": operation,
            "relative_path": None,
        }
        if kind == "publication":
            details = row.get("details_text")
            if details is None:
                if scope is None:
                    raise ValueError("SQL publication ticket scope is missing")
                scope_values = list(scope.values)
                relative_path = BundleStore.path_for(
                    operation,
                    scope,
                    scope_kind=scope_kind,
                )
            else:
                details = json.loads(_text(details))
                scope_values = details["scope"]
                scope_kind = details["scope_kind"]
                relative_path = details["relative_path"]
                stored_scope = WorkspaceScope.from_values(scope_values)
                if scope is not None and stored_scope != scope:
                    raise ValueError("SQL publication ticket scope changed")
                if (
                    BundleStore.path_for(
                        operation,
                        stored_scope,
                        scope_kind=scope_kind,
                    )
                    != relative_path
                ):
                    raise ValueError("SQL publication ticket path is invalid")
            assignment.update(
                scope=scope_values,
                scope_kind=scope_kind,
                relative_path=relative_path,
            )
        elif scope is not None:
            raise ValueError("only publication assignments have bundle scope")
        return assignment

    @staticmethod
    def _publication_details(assignment):
        return _json(
            {
                "scope": assignment["scope"],
                "scope_kind": assignment["scope_kind"],
                "relative_path": assignment["relative_path"],
            },
        )

    async def _recover_publication_assignment(self, row, persisted):
        operation = _text(row["operation_key"])
        expected = None
        if persisted is not None and "scope" in persisted:
            if (
                persisted.get("target_id") != row["target_id"]
                or persisted.get("operation_key") != operation
            ):
                raise ValueError(
                    "manifest publication ticket differs from its SQL identity",
                )
            scope = WorkspaceScope.from_values(persisted["scope"])
            expected = self._assignment(
                row,
                "publication",
                scope=scope,
                scope_kind=persisted.get("scope_kind", "workspace"),
            )
        else:
            publication = await self.db.fetch_one(
                "SELECT * FROM swe_conversation_publications WHERE id=%s AND operation_key=%s",
                (row["target_id"], operation.encode("ascii")),
            )
            if publication is not None:
                scope = WorkspaceScope.from_row(publication)
                scope_kind = publication["scope_kind"]
                BundleStore.validate_publication_locator(publication)
                expected = self._assignment(
                    row,
                    "publication",
                    scope=scope,
                    scope_kind=scope_kind,
                )
        if expected is None:
            if persisted is not None and (
                persisted.get("target_id") != row["target_id"]
                or persisted.get("operation_key") != operation
            ):
                raise ValueError(
                    "manifest publication ticket differs from its SQL identity",
                )
            return {
                "target_id": row["target_id"],
                "operation_key": operation,
                "relative_path": None,
            }
        details = self._publication_details(expected)
        async with self.db.transaction():
            changed = await self.db.execute(
                "UPDATE "
                + ENTRIES
                + " SET details_text=%s WHERE migration_id=%s AND id=%s AND details_text IS NULL",
                (details, self.migration_id, row["id"]),
            )
            if changed != 1:
                current = await self.db.fetch_one(
                    "SELECT details_text FROM "
                    + ENTRIES
                    + " WHERE migration_id=%s AND id=%s",
                    (self.migration_id, row["id"]),
                )
                if (
                    current is None
                    or current["details_text"] is None
                    or _text(current["details_text"]) != details
                ):
                    raise ValueError(
                        "publication ticket scope backfill lost a race",
                    )
        return expected

    async def _hydration_entries(self):
        last_id = None
        while True:
            # Include zero in the first page so invalid integer tickets still
            # reach the mapping validator instead of disappearing from recovery.
            if last_id is None:
                condition = " WHERE migration_id=%s"
                params = (self.migration_id, HYDRATE_PAGE_SIZE)
            else:
                condition = " WHERE migration_id=%s AND id>%s"
                params = (self.migration_id, last_id, HYDRATE_PAGE_SIZE)
            rows = await self.db.fetch_all(
                "SELECT * FROM "
                + ENTRIES
                + condition
                + " ORDER BY id LIMIT %s",
                params,
            )
            if not rows:
                return
            for row in rows:
                yield row
            last_id = rows[-1]["id"]
            if len(rows) < HYDRATE_PAGE_SIZE:
                return

    async def hydrate(self, *, persist=True):
        from .disk_manifest import DiskMap

        if self.recovery is not None and self.recovery.check(
            self.db,
            self.manifest,
        ):
            return
        assignments, batches = {}, DiskMap()
        async for row in self._hydration_entries():
            kind, key = _text(row["entry_kind"]), _text(row["source_key"])
            if kind in TICKET_KINDS:
                persisted = (
                    self.manifest.data["assignments"]
                    .get(kind, {})
                    .get(
                        key,
                    )
                )
                if kind == "publication" and row.get("details_text") is None:
                    assignment = await self._recover_publication_assignment(
                        row,
                        persisted,
                    )
                else:
                    assignment = self._assignment(row, kind)
                if kind not in assignments:
                    assignments[kind] = DiskMap()
                assignments[kind][key] = assignment
            elif kind == "batch":
                batches[key] = (
                    "importing" if row["state"] == "prepared" else row["state"]
                )
        for kind, values in self.manifest.data["assignments"].items():
            for key, value in values.items():
                actual = assignments.get(kind, {}).get(key)
                if actual == value:
                    continue
                if (
                    kind == "publication"
                    and "scope" not in value
                    and actual is not None
                    and value.get("target_id") == actual["target_id"]
                    and value.get("operation_key") == actual["operation_key"]
                ):
                    continue
                raise ValueError(
                    "external mapping has no matching durable SQL ticket",
                )
        self.manifest.data["assignments"], self.manifest.data["batches"] = (
            assignments,
            batches,
        )
        if persist:
            self.manifest._persist()
        if self.recovery is not None:
            self.recovery.confirm(self.manifest)

    async def refresh_batch(self, position):
        """Mirror only this committed SQL batch, never scan all tickets."""
        kind, key = self._key("batch", position)
        row = await self.db.fetch_one(
            "SELECT * FROM "
            + ENTRIES
            + " WHERE migration_id=%s AND entry_kind=%s AND source_key=%s",
            (self.migration_id, kind, key),
        )
        if row is None or row["state"] not in ("committed", "verified"):
            raise ValueError(
                "completed batch has no committed SQL journal row",
            )
        self.manifest.data["batches"][position] = row["state"]
        if self.persist_updates:
            self.manifest._persist()

    async def set_batch_state(self, position, state, *, mirror=True):
        from .manifest import TRANSITIONS

        kind, key = self._key("batch", position)
        sql_state = "prepared" if state == "importing" else state
        async with self.db.transaction():
            row = await self.db.fetch_one(
                "SELECT * FROM "
                + ENTRIES
                + " WHERE migration_id=%s AND entry_kind=%s AND source_key=%s FOR UPDATE",
                (self.migration_id, kind, key),
            )
            previous = (
                "planned"
                if row is None
                else (
                    "importing" if row["state"] == "prepared" else row["state"]
                )
            )
            if state != previous and state not in TRANSITIONS[previous]:
                raise ValueError("invalid migration batch transition")
            if row is None:
                await self.db.execute(
                    "INSERT INTO "
                    + ENTRIES
                    + " (migration_id,entry_kind,source_key,state,created_at,updated_at) VALUES (%s,%s,%s,%s,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))",
                    (self.migration_id, kind, key, sql_state),
                )
            else:
                await self.db.execute(
                    "UPDATE "
                    + ENTRIES
                    + " SET state=%s,updated_at=UTC_TIMESTAMP(6) WHERE id=%s AND migration_id=%s",
                    (sql_state, row["id"], self.migration_id),
                )
        if mirror:
            self.manifest.data["batches"][position] = state
            if self.persist_updates:
                self.manifest._persist()

    async def record_share(self, token, before, expected):
        # Called while the original share is row-locked in publication commit.
        kind, key = self._key("share", token)
        encode = lambda values: [_text(value) for value in values]
        async with self.db.transaction():
            row = await self.db.fetch_one(
                "SELECT * FROM "
                + ENTRIES
                + " WHERE migration_id=%s AND entry_kind=%s AND source_key=%s FOR UPDATE",
                (self.migration_id, kind, key),
            )
            if row is None:
                if any(value is not None for value in before):
                    raise ValueError("unknown existing share extension values")
                details = _json(
                    {"before": encode(before), "expected": encode(expected)},
                )
                await self.db.execute(
                    "INSERT INTO "
                    + ENTRIES
                    + " (migration_id,entry_kind,source_key,state,target_id,details_text,created_at,updated_at) VALUES (%s,%s,%s,'committed',%s,%s,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))",
                    (self.migration_id, kind, key, expected[1], details),
                )
            else:
                details = json.loads(row["details_text"])
                if details["expected"] != encode(expected) or encode(
                    before,
                ) not in (
                    details["before"],
                    details["expected"],
                ):
                    raise ValueError(
                        "share locator differs from this migration journal",
                    )

    async def record_retention(self, retention):
        await self._validate_retention(retention)
        keys = (
            "scope_kind",
            "service_unit_key",
            "tenant_key",
            "source_key",
            "agent_key",
            "retention_key",
            "member_key",
            "kind",
            "publication_id",
            "guard_marker",
        )
        details = {key: _text(retention.get(key)) for key in keys}
        position = _json([details[key] for key in keys[:8]])
        kind, key = self._key("retention", position)
        async with self.db.transaction():
            row = await self.db.fetch_one(
                "SELECT * FROM "
                + ENTRIES
                + " WHERE migration_id=%s AND entry_kind=%s AND source_key=%s FOR UPDATE",
                (self.migration_id, kind, key),
            )
            if row is None:
                await self.db.execute(
                    "INSERT INTO "
                    + ENTRIES
                    + " (migration_id,entry_kind,source_key,state,target_id,details_text,created_at,updated_at) VALUES (%s,%s,%s,'committed',%s,%s,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))",
                    (
                        self.migration_id,
                        kind,
                        key,
                        retention["id"],
                        _json(details),
                    ),
                )
            elif (
                row["target_id"] != retention["id"]
                or json.loads(row["details_text"]) != details
            ):
                raise ValueError("retention identity or business key changed")

    async def _retention_rows(self):
        last_id = None
        clause, scope_values = self._tenant_filter()
        source_mode = (
            self.active_tenant is not None and len(self.active_tenant) == 3
        )
        if source_mode:
            clause = (
                " AND service_unit_key=%s AND tenant_key=%s"
                " AND (source_key=%s OR (scope_kind='legacy_share' AND source_key=''))"
            )
        while True:
            if last_id is None:
                rows = await self.db.fetch_all(
                    (
                        "SELECT * FROM swe_conversation_retentions WHERE 1=1"
                        if clause
                        else "SELECT * FROM swe_conversation_retentions"
                    )
                    + clause
                    + " ORDER BY id LIMIT %s",
                    (*scope_values, HYDRATE_PAGE_SIZE),
                )
            else:
                rows = await self.db.fetch_all(
                    "SELECT * FROM swe_conversation_retentions WHERE id>%s"
                    + clause
                    + " ORDER BY id LIMIT %s",
                    (last_id, *scope_values, HYDRATE_PAGE_SIZE),
                )
            for row in rows:
                if source_mode and row.get("scope_kind") == "legacy_share":
                    if not await self._source_owns_legacy_retention(row):
                        continue
                yield row
            if len(rows) < HYDRATE_PAGE_SIZE:
                return
            last_id = rows[-1]["id"]

    async def _source_owns_legacy_retention(self, row):
        # The tenant-level guard is shared; every source still validates and
        # journals it rather than inventing a source-specific guard namespace.
        if row.get("publication_id") is None:
            return True
        entry = await self.db.fetch_one(
            "SELECT source_key FROM "
            + ENTRIES
            + " WHERE migration_id=%s AND entry_kind='publication' AND target_id=%s AND id=target_id",
            (self.migration_id, row["publication_id"]),
        )
        position = _text(entry["source_key"]) if entry else None
        frozen = getattr(self.manifest, "parent", self.manifest).data
        owners = {
            (share["service_unit_id"], share["tenant_id"], share["source_id"])
            for share in frozen.get("shares", [])
            if share.get("position") == position
        }
        if len(owners) != 1:
            raise ValueError("legacy retention publication source is unproven")
        owner = owners.pop()
        # pylint: disable-next=unsubscriptable-object
        if owner[:2] != self.active_tenant[:2]:
            raise ValueError("legacy retention publication tenant differs")
        return owner == self.active_tenant

    async def capture_retentions(self):
        async for row in self._retention_rows():
            await self.record_retention(row)

    async def mark_state(self, state, verification=None):
        if self.manifest.data.get("tenant_isolation"):
            from .isolation import state_store

            if self.active_tenant is None:
                raise ValueError("tenant isolation requires an active tenant")
            states = {"blocked": "failed", "ready": "published"}
            return await state_store(self.db, self.manifest).transition(
                # pylint: disable-next=not-an-iterable
                *self.active_tenant,
                states.get(state, state),
                verification,
            )
        async with self.db.transaction():
            row = await self.db.fetch_one(
                "SELECT * FROM " + JOBS + " WHERE migration_id=%s FOR UPDATE",
                (self.migration_id,),
            )
            if state in ("imported", "verified", "ready"):
                unresolved = await self.db.fetch_one(
                    "SELECT id FROM "
                    + ENTRIES
                    + " WHERE migration_id=%s AND entry_kind='publication' AND details_text IS NULL LIMIT 1",
                    (self.migration_id,),
                )
                if unresolved is not None:
                    raise ValueError(
                        "migration has publication tickets without recovered scope metadata",
                    )
            if row is None or (
                state != row["state"]
                and state not in JOB_TRANSITIONS[row["state"]]
            ):
                raise ValueError("invalid migration job transition")
            verification_record = verification
            if (
                isinstance(verification, dict)
                and "verification_level" in verification
            ):
                from .verification_evidence import merge_verification

                verification_record = merge_verification(
                    row["verification_text"],
                    verification,
                )
            await self.db.execute(
                "UPDATE "
                + JOBS
                + " SET state=%s,verification_text=COALESCE(%s,verification_text),updated_at=UTC_TIMESTAMP(6) WHERE migration_id=%s",
                (
                    state,
                    (
                        None
                        if verification is None
                        else _json(verification_record)
                    ),
                    self.migration_id,
                ),
            )
