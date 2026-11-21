# -*- coding: utf-8 -*-
"""实体批量票据的身份、恢复与事务边界回归。"""

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy

import pytest

from tests.unit.app.conversation_storage.test_v3_journal import manifest
from swe.app.conversation_storage.migration.journal import MigrationJournal


class TicketDatabase:
    """模拟有自增间隙及事务提交故障的控制表。"""

    max_allowed_packet = 1024 * 1024

    def __init__(self):
        self.entries = {}
        self.next_id = 83
        self.commits = 0
        self.calls = []
        self.failure = None

    @asynccontextmanager
    async def acquire(self):
        yield self

    @asynccontextmanager
    async def transaction(self):
        before = deepcopy(self.entries)
        try:
            yield self
            if self.failure:
                raise self.failure
        except BaseException:
            self.entries = before
            raise
        self.commits += 1

    async def fetch_all(self, query, params):
        self.calls.append(query)
        migration, kind, *keys = params
        return [
            dict(row)
            for (mid, k, key), row in self.entries.items()
            if mid == migration and k == kind and key in keys
        ][::-1]

    async def insert_prepared(self, template, rows, **options):
        self.calls.append(template.prefix)
        for row in rows:
            migration, kind, key, operation, *_rest = row
            self.next_id += 7
            self.entries[migration, kind, key] = {
                "id": self.next_id,
                "migration_id": migration,
                "entry_kind": kind,
                "source_key": key,
                "operation_key": operation,
                "target_id": None,
                "state": "mapped",
                "details_text": _rest[1],
            }

    async def execute(self, query, params):
        self.calls.append(query)
        if "SET details_text" in query:
            details, migration, identity = params
            for row in self.entries.values():
                if (
                    row["migration_id"] == migration
                    and row["id"] == identity
                    and row["details_text"] is None
                ):
                    row["details_text"] = details
                    return 1
            return 0
        migration, kind, *keys = params
        for (mid, k, key), row in self.entries.items():
            if mid == migration and k == kind and key in keys:
                row["target_id"] = row["id"]


async def test_message_tickets_are_rejected_before_sql():
    db = TicketDatabase()
    with pytest.raises(ValueError, match="entity kinds"):
        await MigrationJournal(db, manifest()).allocate_many("message", ["a"])
    assert not db.calls


async def test_batch_tickets_use_actual_ids_and_resume_mixed_requests():
    db, frozen = TicketDatabase(), manifest()
    journal = MigrationJournal(db, frozen)
    first = await journal.allocate_many("chat", ["source/a", "source/b"])
    assert [first[key]["target_id"] for key in first] == [90, 97]
    restarted = manifest()
    resumed = await MigrationJournal(db, restarted).allocate_many(
        "chat",
        ["source/b", "source/c"],
    )
    assert resumed["source/b"] == first["source/b"]
    assert resumed["source/c"]["target_id"] == 104
    assert len(db.entries) == 3
    assert db.commits == 2
    assert len(db.calls) == 10


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("rollback"), asyncio.CancelledError()],
)
async def test_batch_tickets_do_not_mirror_failed_transaction(failure):
    db, frozen = TicketDatabase(), manifest()
    db.failure = failure
    with pytest.raises(type(failure)):
        await MigrationJournal(db, frozen).allocate_many("chat", ["a"])
    assert frozen.data["assignments"] == {}
    assert db.entries == {}


async def test_batch_tickets_reject_duplicates_and_existing_conflicts():
    db, frozen = TicketDatabase(), manifest()
    journal = MigrationJournal(db, frozen)
    with pytest.raises(ValueError, match="duplicate"):
        await journal.allocate_many("chat", ["a", "a"])
    await journal.allocate_many("chat", ["a"])
    next(iter(db.entries.values()))["target_id"] = 999
    before = deepcopy(frozen.data)
    with pytest.raises(ValueError, match="mapping"):
        await journal.allocate_many("chat", ["a", "b"])
    assert frozen.data == before
    assert len(db.entries) == 1


async def test_batch_tickets_are_bounded_and_single_owner():
    db, frozen = TicketDatabase(), manifest()
    journal = MigrationJournal(db, frozen)
    result = await journal.allocate_many(
        "chat",
        [str(i) for i in range(205)],
    )
    assert len(result) == 205
    assert db.commits == 3
    with pytest.raises(ValueError, match="owner"):
        await asyncio.create_task(journal.allocate_many("chat", ["other"]))
    assert await journal.allocate_many("chat", []) == {}


async def test_batch_tickets_reject_packet_oversize_without_sql():
    db = TicketDatabase()
    db.max_allowed_packet = 2048
    with pytest.raises(ValueError, match="packet"):
        await MigrationJournal(db, manifest()).allocate_many(
            "chat",
            ["a" * 2048],
        )
    assert db.calls == []


async def test_unknown_commit_keeps_sql_but_never_updates_mirror():
    from swe.app.conversation_storage.errors import UnknownCommit

    class LostCommit(TicketDatabase):
        @asynccontextmanager
        async def transaction(self):
            yield self
            self.commits += 1
            raise UnknownCommit("ticket-commit")

    db, frozen = LostCommit(), manifest()
    with pytest.raises(UnknownCommit):
        await MigrationJournal(db, frozen).allocate_many("chat", ["a"])
    assert frozen.data["assignments"] == {}
    db.transaction = TicketDatabase.transaction.__get__(db)
    recovered = await MigrationJournal(db, manifest()).allocate_many(
        "chat",
        ["a"],
    )
    assert recovered["a"]["target_id"] == 90
    assert len(db.entries) == 1


async def test_batch_tickets_read_packet_limit_from_pinned_lease():
    from swe.app.conversation_storage.migration.preflight import DMLDatabase

    class Connection:
        config = None

        def __init__(self):
            self.session = TicketDatabase()

        @asynccontextmanager
        async def acquire(self):
            yield self.session

        def transaction(self):
            return self.session.transaction()

        def __getattr__(self, name):
            if name == "max_allowed_packet":
                raise AttributeError(name)
            return getattr(self.session, name)

    db = DMLDatabase(Connection())
    result = await MigrationJournal(db, manifest()).allocate_many(
        "chat",
        ["a"],
    )
    assert result["a"]["target_id"] == 90


async def test_batch_tickets_reuse_pinned_packet_limit():
    class CountedDatabase(TicketDatabase):
        def __init__(self):
            super().__init__()
            self.acquires = 0

        @asynccontextmanager
        async def acquire(self):
            self.acquires += 1
            yield self

    db = CountedDatabase()
    journal = MigrationJournal(db, manifest())
    await journal.allocate_many("chat", ["a"])
    await journal.allocate_many("chat", ["b"])

    assert db.acquires == 1


@pytest.mark.parametrize("kind", ["session", "chat", "turn"])
async def test_entity_batches_resume_actual_ids_with_bounded_transactions(
    kind,
):
    db = TicketDatabase()
    first = await MigrationJournal(db, manifest()).allocate_many(kind, ["old"])
    result = await MigrationJournal(db, manifest()).allocate_many(
        kind,
        ["old", *[f"new:{i}" for i in range(204)]],
    )
    assert result["old"] == first["old"]
    assert len(result) == len(db.entries) == 205
    assert db.commits == 4
    assert result["new:0"]["target_id"] == 97


async def test_publication_batches_resume_mixed_scoped_tickets():
    from swe.app.conversation_storage.identity import WorkspaceScope

    scope = WorkspaceScope("tenant", "source", "agent", service_unit_id="svc")
    db = TicketDatabase()
    first = await MigrationJournal(db, manifest()).allocate_many(
        "publication",
        ["old"],
        scope=scope,
    )
    result = await MigrationJournal(db, manifest()).allocate_many(
        "publication",
        ["old", "new"],
        scope=scope,
    )
    assert result["old"] == first["old"]
    assert result["new"]["target_id"] == 97
    assert result["new"]["scope"] == ["svc", "tenant", "source", "agent"]
    assert result["new"]["scope_kind"] == "workspace"
    assert result["new"]["relative_path"].endswith(
        result["new"]["operation_key"] + ".bundle",
    )
    assert all(row["details_text"] for row in db.entries.values())
    assert db.commits == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", ["svc", "tenant", "other", "agent"]),
        ("scope_kind", "legacy_share"),
        ("relative_path", "bundles/invalid.bundle"),
    ],
)
async def test_publication_batches_reject_changed_scope_and_location(
    field,
    value,
):
    import json
    from swe.app.conversation_storage.identity import WorkspaceScope

    scope = WorkspaceScope("tenant", "source", "agent", service_unit_id="svc")
    db = TicketDatabase()
    await MigrationJournal(db, manifest()).allocate_many(
        "publication",
        ["old"],
        scope=scope,
    )
    row = next(iter(db.entries.values()))
    details = json.loads(row["details_text"])
    details[field] = value
    row["details_text"] = json.dumps(details)
    frozen = manifest()
    with pytest.raises(ValueError, match="scope|path"):
        await MigrationJournal(db, frozen).allocate_many(
            "publication",
            ["old", "new"],
            scope=scope,
        )
    assert len(db.entries) == 1
    assert frozen.data["assignments"] == {}


@pytest.mark.parametrize("identity", [0, -1, True, "90"])
async def test_entity_batches_reject_invalid_integer_identity(identity):
    db = TicketDatabase()
    await MigrationJournal(db, manifest()).allocate_many("chat", ["old"])
    row = next(iter(db.entries.values()))
    row["id"] = row["target_id"] = identity
    with pytest.raises(ValueError, match="mapping"):
        await MigrationJournal(db, manifest()).allocate_many(
            "chat",
            ["old"],
        )


async def test_publication_batch_requires_scope_before_sql():
    db = TicketDatabase()
    with pytest.raises(ValueError, match="scope"):
        await MigrationJournal(db, manifest()).allocate_many(
            "publication",
            ["a"],
        )
    assert db.calls == []


async def test_publication_batch_backfills_legacy_ticket_with_explicit_scope():
    from swe.app.conversation_storage.identity import WorkspaceScope

    scope = WorkspaceScope("tenant", "source", "agent", service_unit_id="svc")
    db = TicketDatabase()
    first = await MigrationJournal(db, manifest()).allocate_many(
        "publication",
        ["old"],
        scope=scope,
    )
    next(iter(db.entries.values()))["details_text"] = None
    resumed = await MigrationJournal(db, manifest()).allocate_many(
        "publication",
        ["old", "new"],
        scope=scope,
    )
    assert resumed["old"] == first["old"]
    assert all(row["details_text"] for row in db.entries.values())


@pytest.mark.parametrize(
    "field,value",
    [
        ("operation_key", b"invalid"),
        ("migration_id", b"other"),
        ("entry_kind", b"turn"),
    ],
)
async def test_batch_rejects_incomplete_durable_identity(field, value):
    db = TicketDatabase()
    await MigrationJournal(db, manifest()).allocate_many("chat", ["old"])
    next(iter(db.entries.values()))[field] = value
    with pytest.raises(ValueError, match="identity|operation"):
        await MigrationJournal(db, manifest()).allocate_many("chat", ["old"])


async def test_publication_batches_unknown_commit_do_not_publish_mirror():
    from swe.app.conversation_storage.errors import UnknownCommit
    from swe.app.conversation_storage.identity import WorkspaceScope

    scope = WorkspaceScope("tenant", "source", "agent", service_unit_id="svc")
    db, frozen = TicketDatabase(), manifest()
    db.failure = UnknownCommit("publication-ticket-commit")
    with pytest.raises(UnknownCommit):
        await MigrationJournal(db, frozen).allocate_many(
            "publication",
            ["a", "b"],
            scope=scope,
        )
    assert frozen.data["assignments"] == {}
