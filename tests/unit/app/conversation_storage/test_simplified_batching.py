# -*- coding: utf-8 -*-
"""Cost and integrity contracts for simplified reads and batched writes."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.app.conversation_storage.errors import ConflictError
from swe.app.conversation_storage.history import HistorySnapshot
from swe.app.runner.models import ChatSpec
from tests.unit.app.conversation_storage.test_chat_repository import (
    chat_row,
    repository,
)
from tests.unit.app.conversation_storage.test_history import history
from tests.unit.app.conversation_storage.test_reference_queries import (
    ReferenceDatabase,
)


@pytest.mark.parametrize("count", [1, 257, 4097])
async def test_chat_revalidation_is_narrow_bounded_and_scoped(tmp_path, count):
    rows = {i: chat_row(id=i) for i in range(1, count + 1)}
    db = ReferenceDatabase(chats=rows)
    await repository(db, tmp_path)._revalidate(list(rows.values()))
    assert len(db.calls) == (count + 255) // 256
    assert db.acquisitions == 1
    assert all("metadata_text" not in query for query, _ in db.calls)
    rows[count]["metadata_revision"] += 1
    with pytest.raises(ConflictError):
        await repository(db, tmp_path)._revalidate(
            [chat_row(id=i) for i in rows],
        )


async def test_chat_revalidation_rejects_foreign_scope(tmp_path):
    expected = chat_row()
    db = ReferenceDatabase(chats={1: chat_row(tenant_key=b"other")})
    with pytest.raises(ConflictError):
        await repository(db, tmp_path)._revalidate([expected])


async def test_history_assembly_checks_snapshot_twice_without_message_requery(
    tmp_path,
):
    store = history(tmp_path)
    store._validate_snapshot = AsyncMock()
    store.chats._hydrate = AsyncMock(
        return_value=[
            ChatSpec(id="chat", session_id="session", user_id="alice"),
        ],
    )
    store._payloads = AsyncMock(return_value=[])
    store._revalidate_rows = AsyncMock(
        side_effect=AssertionError("full requery"),
    )
    store._finish = AsyncMock()
    result = await store._assemble(HistorySnapshot({}, [], [], []))
    assert result.messages == []
    assert store._validate_snapshot.await_count == 2
    store._finish.assert_awaited_once()


async def test_history_capture_does_not_lock_or_requery_messages(tmp_path):
    store = history(tmp_path)

    @asynccontextmanager
    async def transaction():
        yield

    store.db = SimpleNamespace(
        transaction=transaction,
        fetch_one=AsyncMock(
            return_value={
                "history_high": 0,
                "context_epoch": 0,
                "state_revision": 1,
                "recovery_publication_id": 8,
            },
        ),
        fetch_all=AsyncMock(return_value=[]),
    )
    store._chat = AsyncMock(return_value={"id": 1, "session_id": 2})
    store.reader.session_messages = AsyncMock(return_value=[])
    store._pins = AsyncMock(return_value=[])
    store._boundaries = AsyncMock(return_value=[])
    store._revalidate_rows = AsyncMock(
        side_effect=AssertionError("full requery"),
    )
    snapshot = await store._snapshot("chat")
    assert snapshot.rows == []
    assert snapshot.context_epoch == 0
    assert snapshot.recovery_publication_id == 8
    store.reader.session_messages.assert_awaited_once_with(
        2,
        high=0,
        layers=None,
    )
    store.db.fetch_all.assert_not_awaited()


@pytest.mark.parametrize("count", [1, 257, 4097])
async def test_source_publication_locks_are_batched_before_complete_current(
    count,
):
    from swe.app.conversation_storage.source_messages import SourceMessages
    from tests.unit.app.conversation_storage.test_reference_queries import (
        SERVICE,
    )

    rows = {
        i: {
            "id": i,
            "service_unit_key": SERVICE,
            "scope_kind": "workspace",
            "tenant_key": b"t",
            "source_key": b"s",
            "agent_key": b"a",
            "session_id": 1,
            "chat_id": None,
            "turn_id": None,
            "kind": "state",
            "operation_key": str(i).encode(),
            "relative_path": str(i).encode(),
            "byte_length": 100,
            "state": "committed",
            "gc_state": "live",
        }
        for i in range(1, count + 1)
    }

    class SourceDatabase(ReferenceDatabase):
        async def fetch_one(self, query, params):
            assert len(self.calls) == (count + 255) // 256
            assert "FOR UPDATE" in query
            assert params == (count + 1, SERVICE)
            return {"id": count + 1, "result_metadata_text": "exact-plan"}

    db = SourceDatabase(publications=rows)
    service = SimpleNamespace(db=db, service_unit_key=SERVICE)
    source = SourceMessages(dependency_publications=rows)
    current, locked = await source.lock_publications(
        service,
        {"id": count + 1},
    )
    assert current["result_metadata_text"] == "exact-plan"
    assert locked == rows
    assert all(query.endswith("FOR UPDATE") for query, _ in db.calls)


async def test_pin_member_writes_use_prepared_and_keep_exact_set():
    from tests.unit.app.conversation_storage.test_retention import (
        RetentionDatabase,
        store,
    )

    db = RetentionDatabase()
    calls = []

    async def prepared(template, rows, **kwargs):
        values = list(rows)
        calls.append(values)
        fields = template.prefix.split("(", 1)[1].split(")", 1)[0].split(",")
        for values_row in values:
            row = dict(zip(fields, values_row))
            db.pins.append({**row, "id": len(db.pins) + 1})
        return len(values)

    db.insert_prepared = prepared
    original = db.fetch_one

    async def fetch(query, params=None):
        if "UTC_TIMESTAMP" in query:
            return {"created_at": "database-time"}
        return await original(query, params)

    db.fetch_one = fetch
    await store(db).pin([1, 2, 3], kind="reader")
    assert len(calls) == 1
    assert len(calls[0]) == 3
    assert [row["publication_id"] for row in db.pins] == [1, 2, 3]
    assert all(row["created_at"] == "database-time" for row in db.pins)


@pytest.mark.parametrize("corruption", ["missing", "extra", "released"])
async def test_dependency_members_validate_tail_after_4096(corruption):
    from tests.unit.app.conversation_storage.test_retention import (
        RetentionDatabase,
        store,
    )

    db = RetentionDatabase()
    service = store(db)
    key = b"dep:5000"
    db.pins = [
        {
            **service.scope.fields,
            "scope_kind": "workspace",
            "retention_key": key,
            "member_key": i,
            "publication_id": i,
            "kind": "dependency",
            "state": "active",
            "guard_marker": None,
        }
        for i in range(1, 4098)
    ]
    calls = []
    original = db.fetch_all

    async def fetch(query, params):
        calls.append(params)
        return await original(query, params)

    db.fetch_all = fetch
    await service._validate_members(key, list(range(1, 4098)), "dependency")
    assert len(calls) == 17
    assert all(params[-1] == 256 for params in calls)
    if corruption == "missing":
        db.pins.pop()
    elif corruption == "extra":
        db.pins.append(
            {**db.pins[-1], "publication_id": 4098, "member_key": 4098},
        )
    else:
        db.pins[-1]["state"] = "released"
    with pytest.raises(ConflictError):
        await service._validate_members(
            key,
            list(range(1, 4098)),
            "dependency",
        )


async def test_locked_dependencies_do_not_requery_publications():
    from tests.unit.app.conversation_storage.test_retention import (
        RetentionDatabase,
        store,
    )

    db = RetentionDatabase()
    service = store(db)
    with pytest.raises(RuntimeError, match="transaction"):
        await service._install_locked_dependencies(
            db.objects[4],
            [db.objects[1]],
        )
    async with db.transaction():
        await service._install_locked_dependencies(
            db.objects[4],
            [db.objects[1], db.objects[2]],
        )
    assert not any(
        "FROM swe_conversation_publications" in query for query in db.queries
    )
    assert [row["publication_id"] for row in db.pins] == [1, 2]


# Use the real facade/session/PreparedInsert with the protocol-level connection
# substitute: unlike AsyncMock this exercises chunking and poisoned transactions.
from tests.unit.database.test_connection import (
    db as protocol_db,
)  # noqa: F401,E402


def message_batch(*, bad_at=None):
    from swe.app.conversation_storage.message_installs import MessageInstall
    from swe.app.conversation_storage.bundle import BlockExtent, BundleIndex
    from swe.app.conversation_storage.identity import WorkspaceScope

    request = SimpleNamespace(
        scope=WorkspaceScope(
            "t",
            "s",
            "a",
            service_unit_id="schema-test-service",
        ),
        session_id=1,
        chat_id=2,
        turn_id=None,
    )
    messages = [
        MessageInstall(
            str(i),
            "memory",
            "user",
            source_occurrence_no=9 + i,
            context_epoch=int(i == bad_at),
        )
        for i in range(201)
    ]
    index = BundleIndex(
        "bundle",
        10000,
        {},
        {
            item.block_name: BlockExtent("message", 50 + i, 1)
            for i, item in enumerate(messages)
        },
    )
    return request, messages, index


@pytest.mark.parametrize("bad_at", [0, 100, 200])
async def test_late_message_validation_failure_prevents_partial_commit(
    protocol_db,
    bad_at,
):
    from swe.app.conversation_storage.message_installs import install_messages
    from tests.unit.database.test_connection import Connection

    request, messages, index = message_batch(bad_at=bad_at)
    with pytest.raises(ConflictError, match="context epoch"):
        async with protocol_db.transaction():
            await install_messages(
                protocol_db,
                request,
                messages,
                {"id": 3},
                index,
                ({"history_high": 9}, {"history_high": 0}, None),
            )
    calls = Connection.instances[0].calls
    inserts = [
        sql
        for sql, _ in calls
        if sql.startswith("INSERT INTO swe_conversation_")
    ]
    assert not inserts
    assert "ROLLBACK" in [sql for sql, _ in calls]
    assert "COMMIT" not in [sql for sql, _ in calls]
    assert not any(
        sql.startswith("UPDATE swe_conversation_") for sql, _ in calls
    )


async def test_messages_update_only_watermarks_for_201_occurrences(
    protocol_db,
):
    from swe.app.conversation_storage.message_installs import install_messages
    from tests.unit.database.test_connection import Connection

    request, messages, index = message_batch()
    async with protocol_db.transaction():
        await install_messages(
            protocol_db,
            request,
            messages,
            {"id": 3},
            index,
            ({"history_high": 9}, {"history_high": 0}, None),
        )
    calls = Connection.instances[0].calls
    inserted = [
        params
        for sql, params in calls
        if sql.startswith("INSERT INTO swe_conversation_")
    ]
    assert not inserted
    assert (
        sum(sql.startswith("UPDATE swe_conversation_") for sql, _ in calls)
        == 2
    )
    assert (
        "UPDATE swe_conversation_sessions SET history_high=%s WHERE id=%s",
        (210, 1),
    ) in calls
    assert "COMMIT" in [sql for sql, _ in calls]


@pytest.mark.parametrize("failure_at", [None, 2])
async def test_delete_batches_freeze_candidates_and_keep_one_transaction(
    tmp_path,
    failure_at,
):
    from copy import deepcopy

    class Database:
        max_allowed_packet = 1024 * 1024
        _in_transaction = False

        def __init__(self):
            self.rows = {
                i: {
                    "id": i,
                    "session_id": i,
                    "key": str(i).encode(),
                    "deleted": False,
                }
                for i in range(1, 514)
            }
            self.calls = []
            self.updates = 0

        @asynccontextmanager
        async def acquire(self):
            yield self

        @asynccontextmanager
        async def transaction(self):
            before = deepcopy(self.rows)
            self._in_transaction = True
            try:
                yield self
            except BaseException:
                self.rows = before
                raise
            finally:
                self._in_transaction = False

        async def fetch_all(self, sql, params):
            self.calls.append((sql, params))
            if "external_chat_key IN" in sql:
                return [
                    dict(row)
                    for row in self.rows.values()
                    if row["key"] in params[4:]
                ]
            rows = [dict(self.rows[i]) for i in params[1:]]
            if "swe_conversation_chats" in sql:
                self.rows[999] = {
                    "id": 999,
                    "session_id": 999,
                    "key": b"late",
                    "deleted": False,
                }
            return rows

        async def execute(self, sql, params):
            self.calls.append((sql, params))
            assert self._in_transaction
            self.updates += 1
            if self.updates == failure_at:
                raise RuntimeError("later update failed")
            for identity in params[4:]:
                self.rows[identity]["deleted"] = True
            return len(params) - 4

    db = Database()
    repo = repository(db, tmp_path)
    repo.retentions.assert_writes_allowed = AsyncMock()
    keys = [str(i) for i in range(1, 514)] + ["late"]
    if failure_at:
        with pytest.raises(RuntimeError, match="later update"):
            await repo.delete_chats(keys)
        assert not any(row["deleted"] for row in db.rows.values())
    else:
        assert await repo.delete_chats(keys)
        assert all(db.rows[i]["deleted"] for i in range(1, 514))
        assert not db.rows[999]["deleted"]
        assert db.updates == 3
    queries = [sql for sql, _ in db.calls]
    last_session = max(
        i
        for i, sql in enumerate(queries)
        if "swe_conversation_sessions" in sql
    )
    first_chat = min(
        i
        for i, sql in enumerate(queries)
        if "swe_conversation_chats" in sql and "FOR UPDATE" in sql
    )
    assert last_session < first_chat
    assert all(sql.count("%s") == len(params) for sql, params in db.calls)


async def test_share_read_keeps_full_identity_plan_with_narrow_pin_rows(
    tmp_path,
):
    from datetime import datetime
    from swe.app.chat_sharing.models import ChatShareRecord
    from swe.app.conversation_storage.bundle import (
        BundleStore,
        BundleBlock,
        new_operation_key,
    )
    from swe.app.conversation_storage.commit_plan import CommitPlan
    from swe.app.conversation_storage.retention import PinBatch
    from swe.app.conversation_storage.reference_queries import (
        PUBLICATION_LOCK_FIELDS,
    )
    from swe.app.conversation_storage.shares import ShareStorage
    from tests.unit.app.conversation_storage.test_shares import (
        mutation,
        share_request,
    )

    bundles = BundleStore(tmp_path)
    raw = b'{"chat_name":"shared","messages":[]}'
    operation = new_operation_key()
    scope = share_request().scope
    index = bundles.publish(
        operation,
        [BundleBlock("share", "share", raw)],
        scope=scope,
    )
    plan = mutation()
    row = {
        **share_request().scope.fields,
        "id": 1,
        "scope_kind": "workspace",
        "session_id": 1,
        "chat_id": 2,
        "turn_id": None,
        "state": "committed",
        "gc_state": "live",
        "kind": "share",
        "operation_key": operation.encode(),
        "relative_path": index.relative_path.encode(),
        "byte_length": index.byte_length,
        "result_metadata_text": CommitPlan(share=plan).serialize(),
    }
    pin = PinBatch(
        b"reader",
        ({name: row[name] for name in PUBLICATION_LOCK_FIELDS},),
    )
    retentions = SimpleNamespace(
        pin=AsyncMock(return_value=pin),
        finish_reader=AsyncMock(),
    )

    @asynccontextmanager
    async def transaction():
        yield

    db = SimpleNamespace(
        transaction=transaction,
        fetch_one=AsyncMock(return_value=row),
    )
    storage = ShareStorage(
        db,
        bundles,
        service_unit_id="schema-test-service",
        retention_factory=lambda *_args, **_kwargs: retentions,
    )
    extent = index.blocks["share"]
    storage.store.get = AsyncMock(
        return_value=ChatShareRecord(
            token=plan.token,
            chat_id=plan.chat_id,
            creator_id=plan.creator_id,
            snapshot_key=plan.snapshot_key,
            tenant_id=plan.tenant_id,
            service_unit_id="schema-test-service",
            created_at=datetime(2026, 10, 30),
            publication_id=1,
            byte_offset=extent.offset,
            byte_length=extent.length,
        ),
    )
    storage._finish_snapshot_read = AsyncMock()
    assert await storage.read_snapshot(plan.token, record_access=False) == {
        "chat_name": "shared",
        "messages": [],
    }
    assert "result_metadata_text" not in pin.publications[0]
    retentions.finish_reader.assert_awaited_once_with(pin)


async def test_read_only_lease_does_not_expose_mutations(protocol_db):
    from swe.app.conversation_storage.migration.manifest import SourceBoundary
    from swe.app.conversation_storage.migration.readonly import (
        ReadOnlyDatabase,
    )

    boundary = SourceBoundary(
        "snapshot",
        "2026-11-05T00:00:00Z",
        "old@sha256:" + "1" * 64,
        ("writers and GC stopped",),
    )
    db = ReadOnlyDatabase(protocol_db, boundary)
    async with db.acquire() as session:
        assert not hasattr(session, "execute")
        assert not hasattr(session, "insert_prepared")
        with pytest.raises(RuntimeError, match="read-only"):
            await session.fetch_all("DELETE FROM swe_conversation_sessions")
        assert await session.fetch_all("SELECT 1") == [
            {"value": 1},
            {"value": 2},
        ]
