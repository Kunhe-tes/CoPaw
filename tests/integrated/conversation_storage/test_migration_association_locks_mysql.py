# -*- coding: utf-8 -*-
"""Verify offline set-lock conflicts and rollback on isolated InnoDB tables."""

from types import SimpleNamespace

import pytest
from mysql.connector.errors import DatabaseError

from swe.app.conversation_storage.bundle import BundleStore
from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.conversation_storage.migration import install_records
from swe.app.conversation_storage.publications import PublicationRequest
from swe.database.connection import DatabaseConnection
from tests.integrated.conversation_storage.test_schema import (
    insert_chat,
    insert_session,
    insert_row,
)


@pytest.mark.parametrize("existing", [True, False])
async def test_offline_set_locks_block_conflicting_turn_write_until_rollback(
    conversation_test_database,
    tmp_path,
    existing,
    record_property,
):
    db = conversation_test_database
    sid = await insert_session(db)
    cid = await insert_chat(db, sid)
    values = {
        "id": 100,
        "session_id": sid,
        "chat_id": cid,
        "question_msg_key": b"question",
        "turn_order": 1,
        "context_epoch": 0,
        "generation": 0,
        "state": "completed",
    }
    if existing:
        await insert_row(db, "swe_conversation_turns", values)
    request = PublicationRequest(
        operation_key="a" * 64,
        scope=WorkspaceScope(
            "tenant",
            "source",
            "agent",
            service_unit_id="schema-test-service",
        ),
        kind="offline_import",
        owner_key="migration",
        generation=0,
        session_id=sid,
        chat_id=cid,
    )
    store = install_records.OfflineImportStore(
        db,
        BundleStore(tmp_path),
        SimpleNamespace(schema=db.config.database),
        service_unit_id="schema-test-service",
    )
    other = DatabaseConnection(db.config)
    await other.connect()
    plan = {
        "rows": [],
        "updates": [],
        "locks": {"sessions": [sid], "chats": [cid], "turns": [100]},
    }
    cache = {table: {} for table in ("sessions", "chats", "turns")}
    token = install_records._PLAN.set(plan)
    locked = install_records._LOCKED.set(cache)

    async def write(connection):
        if existing:
            await connection.execute(
                "UPDATE swe_conversation_turns SET state='failed' WHERE id=100",
            )
        else:
            await insert_row(connection, "swe_conversation_turns", values)

    try:
        async with db.acquire() as holder:
            try:
                async with holder.transaction():
                    await store._lock_associations(request)
                    assert (cache["turns"][100] is not None) == existing
                    explain = await holder.fetch_all(
                        "EXPLAIN SELECT * FROM swe_conversation_turns WHERE id IN (100) ORDER BY id FOR UPDATE",
                    )
                    record_property("association_lock_explain", explain)
                    assert all(
                        row["key"] in (None, "PRIMARY") for row in explain
                    )
                    async with other.acquire() as contender:
                        await contender.execute(
                            "SET SESSION innodb_lock_wait_timeout=1",
                        )
                        with pytest.raises(DatabaseError) as error:
                            async with contender.transaction():
                                await write(contender)
                        assert error.value.errno == 1205
                    raise RuntimeError("rollback lock holder")
            except RuntimeError as error:
                assert str(error) == "rollback lock holder"
        async with other.transaction():
            await write(other)
        actual = await db.fetch_one(
            "SELECT state FROM swe_conversation_turns WHERE id=100",
        )
        assert actual["state"] == ("failed" if existing else "completed")
    finally:
        install_records._LOCKED.reset(locked)
        install_records._PLAN.reset(token)
        await other.close()
