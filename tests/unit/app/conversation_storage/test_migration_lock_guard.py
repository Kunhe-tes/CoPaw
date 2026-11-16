# -*- coding: utf-8 -*-
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.app.conversation_storage.migration.lock_guard import (
    MigrationLockGuard,
)
from swe.app.conversation_storage.migration.parallel import (
    MigrationCoordinator,
)


@pytest.mark.parametrize(
    "field,value",
    [
        ("connection_id", 99),
        ("lock_owner", None),
        ("server_uuid", "other-server"),
        ("schema_name", "other-schema"),
    ],
)
async def test_guard_rejects_connection_lock_or_database_identity_change(
    field,
    value,
):
    original = {
        "connection_id": 17,
        "lock_owner": 17,
        "server_uuid": "server",
        "schema_name": "schema",
    }
    db = SimpleNamespace(fetch_one=AsyncMock(return_value=dict(original)))
    guard = await MigrationLockGuard.capture(
        db,
        "held-lock",
        schema="schema",
        server_uuid="server",
    )
    db.fetch_one.return_value = {**original, field: value}
    with pytest.raises(
        RuntimeError,
        match="identity or named lock lost",
    ) as failure:
        await guard.check()
    assert "mismatches=" + field in str(failure.value)
    assert "expected_connection_id=17" in str(failure.value)
    assert (
        "schema" not in str(failure.value).split("mismatches=", maxsplit=1)[0]
    )


async def test_guard_reports_missing_identity_row_without_reacquiring_lock():
    db = SimpleNamespace(fetch_one=AsyncMock(return_value=None))
    guard = MigrationLockGuard(
        db,
        "lock",
        "server",
        "schema",
        17,
        asyncio.current_task(),
    )
    with pytest.raises(RuntimeError, match="mismatches=missing_row"):
        await guard.check()
    assert db.fetch_one.await_count == 1
    assert "GET_LOCK" not in db.fetch_one.call_args.args[0]


async def test_guard_rejects_child_task_even_with_inherited_context():
    db = SimpleNamespace(fetch_one=AsyncMock())
    guard = MigrationLockGuard(
        db,
        "lock",
        "server",
        "schema",
        17,
        asyncio.current_task(),
    )
    with pytest.raises(RuntimeError, match="original SQL task"):
        await asyncio.create_task(guard.check())
    db.fetch_one.assert_not_awaited()


async def test_idle_io_receives_owner_task_health_checks_and_failure_stops_workers(
    monkeypatch,
):
    from swe.app.conversation_storage.migration import parallel

    monkeypatch.setattr(parallel, "HEALTH_CHECK_INTERVAL", 0.01)
    owner = asyncio.current_task()
    count = 0
    stopped = asyncio.Event()

    async def health():
        nonlocal count
        assert asyncio.current_task() is owner
        count += 1
        if count == 2:
            raise RuntimeError("lock lost")

    async def work(_item, _request):
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    with pytest.raises(RuntimeError, match="lock lost"):
        await MigrationCoordinator({}, workers=1, health_check=health).run(
            [1],
            work,
        )
    assert count == 2
    assert stopped.is_set()
