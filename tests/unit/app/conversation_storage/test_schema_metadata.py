# -*- coding: utf-8 -*-
"""Bulk metadata keeps validation while bounding SQL round trips."""

from unittest.mock import AsyncMock

import pytest


async def test_bulk_schema_preserves_checks_and_bounds_queries(monkeypatch):
    from swe.app.conversation_storage.migration import preflight

    raw = AsyncMock()
    raw.fetch_all.side_effect = [[], [], []]

    async def business(db, schema, **options):
        assert (
            await db.fetch_all(
                "SELECT c FROM information_schema.COLUMNS",
                (schema, "t"),
            )
            == []
        )
        assert (
            await db.fetch_all(
                "SELECT i FROM information_schema.STATISTICS",
                (schema, "t"),
            )
            == []
        )

    async def tenant(db, schema, **options):
        assert (
            await db.fetch_one(
                "SELECT t FROM information_schema.TABLES",
                (schema, "t"),
            )
            is None
        )
        raise ValueError("precreated tenant migration columns differ")

    monkeypatch.setattr(preflight, "check_schema", business)
    monkeypatch.setattr(preflight, "check_tenant_schema", tenant)
    with pytest.raises(ValueError, match="columns differ"):
        await preflight.check_migration_schema(
            raw,
            "app",
            source_isolation=True,
        )
    assert raw.fetch_all.await_count == 3
    raw.fetch_one.assert_not_awaited()


async def test_bulk_metadata_preserves_order_and_rejects_escape():
    from swe.app.conversation_storage.migration.preflight import (
        _SchemaMetadata,
    )

    raw = AsyncMock()
    raw.fetch_all.side_effect = [
        [
            {"TABLE_NAME": "a", "COLUMN_NAME": "first"},
            {"TABLE_NAME": "b", "COLUMN_NAME": "other"},
            {"TABLE_NAME": "a", "COLUMN_NAME": "second"},
        ],
        [],
        [{"TABLE_NAME": "a", "ENGINE": "InnoDB"}],
    ]
    snapshot = await _SchemaMetadata.load(raw, "app")
    rows = await snapshot.fetch_all(
        "SELECT c FROM information_schema.COLUMNS",
        ("app", "a"),
    )
    assert [row["COLUMN_NAME"] for row in rows] == ["first", "second"]
    assert await snapshot.fetch_one(
        "SELECT t FROM information_schema.TABLES",
        ("app", "a"),
    ) == {"TABLE_NAME": "a", "ENGINE": "InnoDB"}
    with pytest.raises(ValueError, match="metadata"):
        await snapshot.fetch_all("SELECT private FROM business", ("app",))
    with pytest.raises(ValueError, match="schema"):
        await snapshot.fetch_all(
            "SELECT c FROM information_schema.COLUMNS",
            ("other", "a"),
        )


async def test_sql_progress_includes_checks_and_failed_roundtrips():
    import asyncio
    import io
    from swe.app.conversation_storage.migration.preflight import DMLDatabase
    from swe.app.conversation_storage.migration.progress import (
        MigrationProgress,
    )

    async def query(*args):
        await asyncio.sleep(0.001)
        raise RuntimeError("database failed")

    raw = AsyncMock()
    raw.fetch_one.side_effect = query
    progress = MigrationProgress("migrate", "job", stream=io.StringIO())
    with progress.activate():
        with pytest.raises(RuntimeError):
            await DMLDatabase(raw).fetch_one("SELECT private", ("secret",))
    assert progress.data["db_calls"] == 1
    assert progress.data["db_seconds"] > 0
    assert "secret" not in str(progress.snapshot())
