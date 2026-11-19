# -*- coding: utf-8 -*-
"""Opt-in SQL shape, lease and FOR SHARE checks in a disposable test schema."""

import asyncio
import os

import pytest

from swe.app.conversation_storage.reference_queries import (
    ReferenceQuery,
    fetch_reference_rows,
)
from tests.integrated.conversation_storage.test_schema import (
    insert_chat,
    insert_publication,
    insert_row,
    insert_session,
)

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("SWE_TEST_DB_HOST")
        and os.environ.get("SWE_TEST_DB_NAME")
    ),
    reason="isolated MySQL not configured; B1a acceptance not executed",
)
SERVICE = b"schema-test-service"


async def seed_references(db):
    session = await insert_session(db)
    chat = await insert_chat(db, session)
    publication = await insert_publication(
        db,
        session_id=session,
        result_metadata_text="x" * (1024 * 1024),
    )
    turn = await insert_row(
        db,
        "swe_conversation_turns",
        {
            "session_id": session,
            "chat_id": chat,
            "question_msg_key": b"q",
            "turn_order": 1,
            "context_epoch": 0,
            "generation": 0,
            "state": "completed",
            "history_status": "completed",
            "terminal_publication_id": publication,
        },
    )
    return {
        "sessions": session,
        "chats": chat,
        "publications": publication,
        "turns": turn,
    }


async def test_real_reference_templates_and_transaction_lease(
    conversation_test_database,
    monkeypatch,
    record_property,
):
    db = conversation_test_database
    identities_by_table = await seed_references(db)
    publication = identities_by_table["publications"]
    async with db.transaction() as session:
        original = session.fetch_all
        calls = []

        async def capture(query, params):
            calls.append((query, params))
            return await original(query, params)

        monkeypatch.setattr(session, "fetch_all", capture)
        expected_queries = 0
        for kind in ReferenceQuery:
            identities = [identities_by_table[kind.value[0]]]
            expected_queries += (len(identities) + 255) // 256
            result = await fetch_reference_rows(db, kind, identities, SERVICE)
            assert set(result) == set(identities)
            assert all(
                "result_metadata_text" not in row
                and "execution_identity_text" not in row
                for row in result.values()
            )
        assert len(calls) == expected_queries
        assert (
            await fetch_reference_rows(
                db,
                ReferenceQuery.PUBLICATION_OWNERSHIP,
                [publication],
                b"foreign",
            )
            == {}
        )
        assert (
            await fetch_reference_rows(
                db,
                ReferenceQuery.PUBLICATION_OWNERSHIP,
                [999],
                SERVICE,
            )
            == {}
        )
        query, params = calls[0]
        record_property(
            "reference_explain",
            await original("EXPLAIN " + query, params),
        )
        assert (
            await fetch_reference_rows(
                db,
                ReferenceQuery.PUBLICATION_OWNERSHIP,
                [publication],
                SERVICE,
            )
        )[publication]["session_id"] == identities_by_table["sessions"]


async def test_publication_dependency_locks_block_writer_until_commit(
    conversation_test_database,
):
    db = conversation_test_database
    publication = (await seed_references(db))["publications"]
    release_writer = asyncio.Event()
    started = asyncio.Event()

    async def write():
        await release_writer.wait()
        async with db.transaction():
            started.set()
            await db.execute(
                "UPDATE swe_conversation_publications SET gc_state='deleting' WHERE id=%s",
                (publication,),
            )

    # Spawn before the reader transaction so no task-owned lease is inherited.
    task = asyncio.create_task(write())
    try:
        async with db.transaction():
            await fetch_reference_rows(
                db,
                ReferenceQuery.PUBLICATION_LOCK,
                [publication],
                SERVICE,
            )
            release_writer.set()
            await asyncio.wait_for(started.wait(), timeout=5)
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.2)
        await asyncio.wait_for(task, timeout=5)
        async with db.transaction():
            rows = await fetch_reference_rows(
                db,
                ReferenceQuery.PUBLICATION_LOCK,
                [publication],
                SERVICE,
            )
            assert rows[publication]["gc_state"] == "deleting"
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
