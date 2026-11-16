# -*- coding: utf-8 -*-
"""Offline records retain full validation while SQL grows by bounded blocks."""

from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.app.conversation_storage.bundle import BundleIndex
from swe.app.conversation_storage.errors import IntegrityError
from swe.app.conversation_storage.migration.install_records import (
    OfflineImportStore,
    _LOCKED,
    _PLAN,
)
from swe.app.conversation_storage.publications import CommitPlan
from swe.database.prepared import execute_prepared
from tests.unit.database.test_prepared import ProtocolSession

SERVICE = b"schema-test-service"
PUBLICATION = {
    "id": 5000,
    "service_unit_key": SERVICE,
    "tenant_key": b"tenant",
    "source_key": b"source",
    "agent_key": b"agent",
}
INDEX = BundleIndex("bundle", 0, {}, {})


def message(identity, **extra):
    return {
        "table": "messages",
        "values": {
            "id": identity,
            "service_unit_key": SERVICE.decode(),
            "session_id": 1,
            "source_msg_key": "中文😀\\\n\x00",
            "publication_id": {"publication": True},
            "deleted_at": None,
            **extra,
        },
    }


class Database:
    max_allowed_packet = 1024 * 1024

    def __init__(self):
        self.rows = {}
        self.queries = []
        self.prepared = []

    @asynccontextmanager
    async def acquire(self):
        yield self

    async def insert(self, query, params):
        raise AssertionError("offline messages must use prepared batches")

    async def insert_prepared(self, template, rows, **limits):
        values = list(rows)
        self.prepared.append((template, values, limits))
        return len(values)

    async def fetch_one(self, query, params):
        raise AssertionError("committed verification must use bounded sets")

    async def fetch_all(self, query, params):
        self.queries.append((query, params))
        assert query.count("%s") == len(params)
        return [deepcopy(self.rows[i]) for i in params[1:] if i in self.rows]


def store(database):
    return OfflineImportStore(
        database,
        None,
        SimpleNamespace(schema="test_conversation_batch", migration_id="m"),
        service_unit_id=SERVICE.decode(),
    )


async def install(service, rows, updates=()):
    plan_token = _PLAN.set({"rows": rows, "updates": list(updates)})
    lock_token = _LOCKED.set(
        {"sessions": {1: {**PUBLICATION, "id": 1}}, "chats": {}, "turns": {}},
    )
    try:
        await service._install(PUBLICATION, CommitPlan(), INDEX)
    finally:
        _LOCKED.reset(lock_token)
        _PLAN.reset(plan_token)


@pytest.mark.parametrize("count", [0, 1, 100, 101, 513])
async def test_install_uses_one_lazy_prepared_stream_for_contiguous_messages(
    count,
):
    db = Database()
    await install(store(db), [message(i + 1) for i in range(count)])
    assert len(db.prepared) == bool(count)
    if count:
        template, rows, _limits = db.prepared[0]
        assert "swe_conversation_messages" in template.prefix
        columns = template.prefix.split("(", 1)[1].split(")", 1)[0].split(",")
        mapped = [dict(zip(columns, row)) for row in rows]
        assert mapped[0]["source_msg_key"] == "中文😀\\\n\x00".encode()
        assert [row["id"] for row in mapped] == list(range(1, count + 1))
        assert all(
            row["publication_id"] == PUBLICATION["id"] for row in mapped
        )


async def test_field_shapes_and_other_records_preserve_install_order():
    db = Database()
    service = store(db)
    service._apply_record = AsyncMock()
    rows = [message(1), message(2, role_key="assistant"), message(3)]
    other = {"table": "sessions", "values": {"id": 9}}
    await install(service, [*rows, other, message(4)], updates=[other])
    assert [len(batch) for _template, batch, _ in db.prepared] == [1, 1, 1, 1]
    assert service._apply_record.await_count == 2


async def test_each_message_still_checks_its_source_scope():
    db = Database()
    with pytest.raises(IntegrityError, match="scope mismatch"):
        await install(
            store(db),
            [message(1), message(2, service_unit_key="other")],
        )


async def test_equal_field_sets_batch_even_when_input_key_order_differs():
    db = Database()
    second = message(2)
    second["values"] = dict(reversed(list(second["values"].items())))
    await install(store(db), [message(1), second])
    assert len(db.prepared) == 1
    assert [row[0] for row in db.prepared[0][1]] == [1, 2]


@pytest.mark.parametrize("count", [0, 1, 256, 257, 513])
async def test_verification_reads_bounded_sets_and_compares_every_row(count):
    db = Database()
    service = store(db)
    plan = {"rows": [message(i + 1) for i in range(count)], "updates": []}
    db.rows = {
        i: service._resolve(message(i)["values"], PUBLICATION, INDEX)
        for i in range(1, count + 1)
    }
    await service._verify_records_sql(PUBLICATION, plan, INDEX)
    assert len(db.queries) == (count + 255) // 256
    if count:
        db.rows[count]["source_msg_key"] = b"corrupt"
        with pytest.raises(
            IntegrityError,
            match="immutable typed row differs",
        ):
            await service._verify_records_sql(PUBLICATION, plan, INDEX)


async def test_verification_rejects_missing_and_duplicate_input_identity():
    db = Database()
    service = store(db)
    with pytest.raises(IntegrityError, match="typed row differs"):
        await service._verify_records_sql(
            PUBLICATION,
            {"rows": [message(1)], "updates": []},
            INDEX,
        )
    db.rows[1] = service._resolve(message(1)["values"], PUBLICATION, INDEX)
    with pytest.raises(IntegrityError, match="duplicate"):
        await service._verify_records_sql(
            PUBLICATION,
            {"rows": [message(1), message(1)], "updates": []},
            INDEX,
        )


@pytest.mark.parametrize(
    "count,executions",
    [(0, 0), (1, 1), (100, 1), (101, 2), (513, 6)],
)
async def test_actual_prepared_protocol_executes_one_insert_per_bounded_block(
    count,
    executions,
):
    db = Database()
    protocol = ProtocolSession()

    async def prepared(template, rows):
        return await execute_prepared(protocol, template, rows)

    db.insert_prepared = prepared
    await install(store(db), [message(i + 1) for i in range(count)])
    assert len(protocol.executes) == executions
    assert (
        sum(len(params) // 6 for _statement, params in protocol.executes)
        == count
    )


async def test_packet_budget_splits_messages_and_rejects_oversized_row():
    db = Database()
    protocol = ProtocolSession(packet_limit=2048)

    async def prepared(template, rows):
        return await execute_prepared(protocol, template, rows)

    db.insert_prepared = prepared
    await install(
        store(db),
        [message(i + 1, source_msg_key="x" * 128) for i in range(10)],
    )
    assert 1 < len(protocol.executes) < 10
    with pytest.raises(ValueError, match="max_allowed_packet"):
        await install(store(db), [message(11, source_msg_key="x" * 2048)])


async def test_failed_prepared_insert_rolls_back_current_publication(tmp_path):
    from tests.unit.app.conversation_storage.test_offline_commit_stages import (
        prepared,
    )

    service, operation, _plan = await prepared(tmp_path)
    original = service.db.insert_prepared

    async def fail_after_insert(template, rows, **limits):
        await original(template, rows, **limits)
        assert service.db.messages
        raise IntegrityError("bad offline typed row")

    service.db.insert_prepared = fail_after_insert
    with pytest.raises(IntegrityError, match="bad offline typed row"):
        await service.commit(operation.operation_key)
    assert service.db.messages == []
    assert (
        service.db.rows[operation.operation_key.encode()]["state"]
        == "prepared"
    )
