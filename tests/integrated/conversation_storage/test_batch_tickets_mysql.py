# -*- coding: utf-8 -*-
"""隔离 MySQL 验证有间隙票据与 SQL 权威恢复。"""

from types import SimpleNamespace

from swe.app.conversation_storage.migration.journal import MigrationJournal
from swe.app.conversation_storage.migration.preflight import DMLDatabase
from tests.integrated.conversation_storage.conftest import (
    SQL_ROOT,
    apply_sql_script,
)


def frozen_manifest():
    """构建不依赖本地 ID 分配器的旧镜像。"""
    return SimpleNamespace(
        migration_id="00000000-0000-0000-0000-000000000001",
        data={"version": 3, "assignments": {}, "batches": {}},
        _persist=lambda: None,
    )


async def test_mysql_mixed_tickets_preserve_real_noncontiguous_identities(
    conversation_test_database,
):
    db = conversation_test_database
    await apply_sql_script(
        db,
        SQL_ROOT / "conversation_migration_control_tables.sql",
    )
    frozen = frozen_manifest()
    async with db.acquire() as session:
        journal = MigrationJournal(DMLDatabase(session, owner=db), frozen)
        first = await journal.allocate(
            "message",
            "svc/source/session/message:0",
        )
    await db.execute(
        "INSERT INTO swe_conversation_migration_entries "
        "(id,migration_id,entry_kind,source_key,state,created_at,updated_at) "
        "VALUES (%s,%s,%s,%s,%s,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))",
        (
            10001,
            b"another-job",
            b"batch",
            b"legal-other-allocation",
            "prepared",
        ),
    )
    async with db.acquire() as session:
        facade = DMLDatabase(session, owner=db)
        resumed = await MigrationJournal(
            facade,
            frozen_manifest(),
        ).allocate_many(
            "message",
            ["svc/source/session/message:0", "svc/source/session/message:1"],
        )
        repeated = await MigrationJournal(
            facade,
            frozen_manifest(),
        ).allocate_many(
            "message",
            list(resumed),
        )
    assert resumed["svc/source/session/message:0"] == first
    assert resumed["svc/source/session/message:1"]["target_id"] > 10001
    assert repeated == resumed
    rows = await db.fetch_all(
        "SELECT id,target_id,source_key,operation_key FROM swe_conversation_migration_entries "
        "WHERE migration_id=%s AND entry_kind=%s",
        (frozen.migration_id.encode(), b"message"),
    )
    assert len(rows) == 2
    for row in rows:
        actual = resumed[row["source_key"].decode()]
        assert row["id"] == row["target_id"] == actual["target_id"]
        assert row["operation_key"].decode() == actual["operation_key"]
