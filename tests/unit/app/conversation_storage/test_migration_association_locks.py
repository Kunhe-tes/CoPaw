# -*- coding: utf-8 -*-
"""Offline association queries stay bounded and preserve integrity."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from swe.app.conversation_storage.errors import ConflictError, IntegrityError
from swe.app.conversation_storage.migration import install_records
from swe.app.conversation_storage.migration.importer import (
    ConversationImporter,
)
from tests.unit.app.conversation_storage.test_offline_commit_stages import (
    prepared,
)


async def test_commit_uses_set_queries_for_association_locks(tmp_path):
    store, operation, _ = await prepared(tmp_path)
    db = store.db
    queries = []
    original = db.fetch_all

    async def fetch_all(query, params=None):
        if "FOR UPDATE" in query and " WHERE id IN (" in query:
            queries.append((query, params))
            for table, row in (
                ("sessions", db.session),
                ("chats", db.chat),
                ("turns", db.turn),
            ):
                if "swe_conversation_" + table in query:
                    return [deepcopy(row)] if row["id"] in params else []
        return await original(query, params)

    db.fetch_all = fetch_all
    await store.commit(operation.operation_key)
    assert db.messages
    # Commit preflight and the SQL transaction each validate associations.
    assert [params for _, params in queries] == [(1,), (2,), (3,)] * 2
    assert not any(" WHERE id=%s FOR UPDATE" in query for query in db.queries)


@pytest.mark.parametrize(
    "relation,field,value,error",
    [
        ("session", "source_key", b"other-source", IntegrityError),
        ("session", "active_turn_id", 3, ConflictError),
        ("chat", "session_id", 99, IntegrityError),
        ("turn", "chat_id", 99, IntegrityError),
    ],
)
async def test_set_locks_preserve_scope_relation_and_execution_checks(
    tmp_path,
    relation,
    field,
    value,
    error,
):
    store, operation, _ = await prepared(tmp_path)
    getattr(store.db, relation)[field] = value
    with pytest.raises(error):
        await store.commit(operation.operation_key)
    assert not store.db.messages


@pytest.mark.parametrize("committed", [True, False])
async def test_resume_retains_exact_legacy_plan_bytes(tmp_path, committed):
    from swe.app.conversation_storage.migration.plan_compatibility import (
        retained_plan,
    )
    from swe.app.conversation_storage.migration.install_records import (
        plan_block,
    )

    store, operation, _ = await prepared(tmp_path)
    if committed:
        await store.commit(operation.operation_key)
    row = await store.get(operation.operation_key)
    stored = await store._load_plan(row)
    narrow = plan_block(
        store.target,
        stored["rows"],
        stored["updates"],
        {"sessions": [1]},
    )
    legacy = plan_block(
        store.target,
        stored["rows"],
        stored["updates"],
        stored["locks"],
    )
    retained = retained_plan(store.bundles, row, narrow, legacy)
    assert retained.content == legacy.content
    assert await store.verify_blocks(row, [retained]) is None
    from swe.app.conversation_storage.migration.importer import (
        ImportBatch,
        ParallelWorkspaceImporter,
    )
    from swe.app.conversation_storage.identity import WorkspaceScope
    from swe.app.conversation_storage.migration.parallel_import import (
        ParallelWorkspaceContext,
        _NASStages,
    )
    from swe.app.conversation_storage.migration.parallel import MigrationIO

    importer = ConversationImporter.__new__(ConversationImporter)
    importer.target = store.target
    importer.manifest = SimpleNamespace(migration_id="migration")
    importer.bundle_stores = {"schema-test-service": store.bundles}
    importer.stores = {"schema-test-service": store}
    importer._allocate = AsyncMock(
        return_value={
            "operation_key": operation.operation_key,
            "target_id": row["id"],
        },
    )
    importer._batch_finished = AsyncMock()
    importer._set_batch_state = AsyncMock()
    store.verify_batch = AsyncMock(return_value=row)
    store.commit = AsyncMock(return_value=row)
    spec = ImportBatch(
        locks={"sessions": [1]},
        legacy_locks=stored["locks"],
        session_id=1,
    )
    scope = WorkspaceScope(
        "t",
        "s",
        "a",
        service_unit_id="schema-test-service",
    )
    importer._reserve_batch = AsyncMock(return_value=row)
    await importer._publish("position", scope, stored["rows"], [], spec=spec)
    if committed:
        assert (
            store.verify_batch.await_args.args[3]["locks"] == stored["locks"]
        )
    async with MigrationIO(1) as io:
        context = ParallelWorkspaceContext(
            {},
            object(),
            None,
            _NASStages(store),
            io,
        )
        parallel = ParallelWorkspaceImporter.__new__(ParallelWorkspaceImporter)
        parallel.context = context
        parallel.target = store.target
        assert (
            await parallel._retained_message_plan(
                row,
                narrow,
                stored["rows"],
                spec,
            )
        ).content == legacy.content
    changed = plan_block(store.target, [], [], stored["locks"])
    with pytest.raises(IntegrityError):
        retained_plan(store.bundles, row, narrow, changed)


async def test_message_batches_declare_only_referenced_associations():
    from agentscope.message import Msg

    importer = ConversationImporter.__new__(ConversationImporter)
    importer.session_ids = {"session": 1}
    importer.chat_ids = {"chat-one": 2, "chat-two": 3}
    importer.turn_ids = {}
    importer.batch_size = 1
    importer._assigned = AsyncMock(side_effect=range(10, 30))
    importer._allocate_messages = AsyncMock(
        side_effect=lambda positions: {
            position: 100 + index for index, position in enumerate(positions)
        },
    )
    importer._turn_identities = AsyncMock()
    importer._root_and_turns = AsyncMock()
    importer._publish = AsyncMock()
    turns = {
        str(index): {
            "chat_id": "one" if index == 0 else "two",
            "message": Msg("user", str(index), "user").to_dict(),
        }
        for index in range(20)
    }
    session = {
        "position": "session",
        "identity": [None, None, None, None, "alice", "console", "external"],
        "legacy": {"state": {"turn_states": turns}},
    }
    workspace = {
        "chats": [
            {
                "position": "chat-one",
                "spec": {
                    "id": "one",
                    "session_id": "external",
                    "user_id": "alice",
                    "channel": "console",
                    "meta": {},
                },
            },
            {
                "position": "chat-two",
                "spec": {
                    "id": "two",
                    "session_id": "external",
                    "user_id": "alice",
                    "channel": "console",
                    "meta": {},
                },
            },
        ],
    }
    await importer._session(
        session,
        workspace,
        SimpleNamespace(service_unit_id="svc"),
    )
    declarations = [
        call.kwargs["spec"].locks for call in importer._publish.await_args_list
    ]
    assert len(declarations) == 20
    assert declarations[0] == {"sessions": [1], "chats": [2], "turns": [10]}
    assert declarations[-1] == {"sessions": [1], "chats": [3], "turns": [29]}


@pytest.mark.parametrize("packet,maximum", [(1024 * 1024, 100), (2048, 32)])
async def test_lock_queries_bound_sorted_ids_and_cache_missing_rows(
    tmp_path,
    packet,
    maximum,
):
    store, operation, _ = await prepared(tmp_path)
    store.db.max_allowed_packet = packet
    queries = []

    async def missing(query, params):
        queries.append((query, params))
        return []

    store.db.fetch_all = missing
    plan = {
        "rows": [],
        "updates": [],
        "locks": {
            "sessions": [1],
            "chats": [2],
            "turns": list(range(253, 2, -1)),
        },
    }
    cache = {table: {} for table in ("sessions", "chats", "turns")}
    token = install_records._PLAN.set(plan)
    locked = install_records._LOCKED.set(cache)
    try:
        assert await store._lock_associations(operation) == (None, None, None)
        assert all(len(params) <= maximum for _, params in queries)
        assert [
            identity
            for query, params in queries
            if "_turns" in query
            for identity in params
        ] == list(range(3, 254))
        assert cache["turns"][253] is None
        with pytest.raises(IntegrityError, match="missing"):
            store._related("turns", 253)
    finally:
        install_records._LOCKED.reset(locked)
        install_records._PLAN.reset(token)
