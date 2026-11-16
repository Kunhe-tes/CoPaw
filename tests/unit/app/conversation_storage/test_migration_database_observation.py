# -*- coding: utf-8 -*-
"""Migration metrics observe physical work without retaining SQL values."""

import io
import threading

import pytest

from swe.app.conversation_storage.migration.progress import MigrationProgress
from tests.unit.database.test_prepared import ProtocolSession, template


async def test_multiblock_reader_records_one_open_and_parse(tmp_path):
    from swe.app.conversation_storage.bundle import BundleStore, BundleBlock
    from swe.app.conversation_storage.migration.parallel import MigrationIO

    store = BundleStore(tmp_path)
    index = store.publish(
        "a" * 64,
        [
            BundleBlock("first", "message", b"one"),
            BundleBlock("second", "message", b"two"),
        ],
    )

    def read():
        with store.open_reader(index.relative_path) as reader:
            assert reader.read_extents(index.blocks.values()) == (
                b"one",
                b"two",
            )

    report = MigrationProgress("migrate", "job", stream=io.StringIO())
    with report.activate():
        async with MigrationIO(1) as executor:
            await executor.call(read)
    assert report.snapshot()["bundle_opens"] == 1
    assert report.snapshot()["bundle_index_parses"] == 1
    assert report.snapshot()["bundle_bytes_read"] > len(b"onetwo")


async def test_io_threads_receive_only_value_free_observer():
    from swe.app.conversation_storage.migration.parallel import MigrationIO
    from swe.database.observation import record_operation
    from swe.database.connection import _CURRENT_CONNECTION

    owner = threading.get_ident()

    def read_bundle():
        assert threading.get_ident() != owner
        assert not _CURRENT_CONNECTION.get()
        record_operation("bundle_open")
        record_operation("bundle_index_parse")

    report = MigrationProgress("migrate", "job", stream=io.StringIO())
    with report.activate():
        async with MigrationIO(2) as executor:
            await executor.call(read_bundle)
    assert report.snapshot()["bundle_opens"] == 1
    assert report.snapshot()["bundle_index_parses"] == 1


async def test_prepared_metrics_count_chunks_not_logical_calls():
    from swe.database.prepared import execute_prepared

    progress = MigrationProgress("migrate", "job", stream=io.StringIO())
    with progress.activate():
        await execute_prepared(
            ProtocolSession(),
            template(),
            [(index, "private body") for index in range(5)],
            max_rows=2,
        )
    result = progress.snapshot()
    assert result["db_statement_attempts"] == 3
    assert result["db_statement_seconds"] >= 0
    assert "private body" not in str(result)


async def test_executemany_is_not_reported_as_exact_statement_count(db):
    report = MigrationProgress("migrate", "job", stream=io.StringIO())
    with report.activate():
        await db.execute_many("INSERT private", [(1,), (2,)])
    result = report.snapshot()
    assert result["db_executemany_calls"] == 1
    assert result["db_statement_attempts"] == 0


async def test_failed_prepared_attempt_is_preserved():
    from swe.database.prepared import execute_prepared

    session = ProtocolSession()
    session._run = _fail_operation
    report = MigrationProgress("migrate", "job", stream=io.StringIO())
    with report.activate(), pytest.raises(RuntimeError, match="injected"):
        await execute_prepared(session, template(), [(1, "private")])
    # Cursor creation failed before a statement reached the execute boundary.
    assert report.snapshot()["db_statement_attempts"] == 0


async def _fail_operation(operation):
    operation.close()
    raise RuntimeError("injected")


async def test_failed_statement_attempt_is_counted():
    from swe.database.prepared import execute_prepared

    session = ProtocolSession()

    async def fail_execute(*_args, **_kwargs):
        raise RuntimeError("injected")

    session._connection.cmd_stmt_execute = fail_execute
    report = MigrationProgress("migrate", "job", stream=io.StringIO())
    with report.activate(), pytest.raises(RuntimeError, match="injected"):
        await execute_prepared(session, template(), [(1, "private")])
    assert report.snapshot()["db_statement_attempts"] == 1


def test_stage_wall_time_is_cumulative_and_live(monkeypatch):
    from swe.app.conversation_storage.migration import progress as module

    ticks = iter([0, 2, 5, 9, 11])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(ticks))
    report = MigrationProgress("migrate", "job", stream=io.StringIO())
    report.stage("inventory")
    assert report.snapshot()["stage_wall_seconds"] == {
        "starting": 2,
        "inventory": 3,
    }
    report.stage("verify")
    assert report.snapshot()["stage_wall_seconds"] == {
        "starting": 2,
        "inventory": 7,
        "verify": 2,
    }


@pytest.mark.asyncio
async def test_transaction_observation_counts_actual_boundaries(db):
    report = MigrationProgress("migrate", "job", stream=io.StringIO())
    with report.activate():
        async with db.transaction():
            async with db.transaction():
                await db.fetch_one("SELECT private", ("secret",))
        with pytest.raises(ValueError):
            async with db.transaction():
                raise ValueError("private")
    result = report.snapshot()
    assert result["db_transaction_begins"] == 2
    assert result["db_transaction_commits"] == 1
    assert result["db_transaction_rollbacks"] == 1
    assert result["db_statement_attempts"] == 1
    assert "secret" not in str(result)


@pytest.fixture
async def db(monkeypatch):
    from tests.unit.database.test_connection import Connection
    from swe.database import connection as module
    from swe.database import DatabaseConfig, DatabaseConnection

    monkeypatch.setattr(module, "MySQLConnection", Connection)
    connection = DatabaseConnection(DatabaseConfig(database="swe"))
    await connection.connect()
    try:
        yield connection
    finally:
        await connection.close()
