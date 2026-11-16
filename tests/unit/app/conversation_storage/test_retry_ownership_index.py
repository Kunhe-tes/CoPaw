# -*- coding: utf-8 -*-
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

from swe.app.conversation_storage.migration import tenant_retry as retry
from swe.app.conversation_storage.migration.disk_manifest import (
    disk_index_policy,
)

JOB = "00000000-0000-4000-8000-000000000001"


async def test_automatic_review_scans_tickets_once_for_all_failed_sources(
    tmp_path,
    monkeypatch,
):
    sources = ("A", "B", "C", "D")
    old = {
        "tenant_isolation": True,
        "source_isolation": True,
        "services": [{"service_unit_id": "svc"}],
        "declared_services": [],
        "source_shares": [],
        "shares": [],
        "workspaces": [],
        "blockers": [],
        "tenants": [
            {
                "service_unit_id": "svc",
                "tenant_id": "alice",
                "source_id": source,
                "state": "failed",
                "blockers": [],
            }
            for source in sources
        ],
    }
    current = deepcopy(old)
    for tenant in current["tenants"]:
        tenant["state"] = "discovered"
    manifest = SimpleNamespace(
        data=old,
        migration_id=JOB,
        path=tmp_path / "manifest.json",
    )
    scans = []

    async def many(query, params):
        if retry.ENTRIES not in query:
            return []
        scans.append(params[-1])
        if params[-1]:
            return []
        return [
            {
                "id": 1,
                "entry_kind": b"session",
                "source_key": b'["session","svc","alice","A","agent"]',
                "details_text": None,
            },
        ]

    db = SimpleNamespace(
        fetch_one=AsyncMock(return_value=None),
        fetch_all=many,
    )
    monkeypatch.setattr(
        retry,
        "_states",
        lambda *_: SimpleNamespace(
            get=AsyncMock(return_value={"state": "failed"}),
        ),
    )
    monkeypatch.setattr(
        retry,
        "_discover_review",
        lambda *_: deepcopy(current),
    )
    commit = AsyncMock()
    monkeypatch.setattr(retry, "_commit_review", commit)
    monkeypatch.setattr(
        retry,
        "recover_pending_review",
        AsyncMock(return_value={"outcome": "new"}),
    )
    keys = {("svc", "alice", source) for source in sources}
    with disk_index_policy(tmp_path.resolve(), 65536):
        result = await retry.review_retry(db, manifest, current, eligible=keys)
        assert not list(tmp_path.glob("migration-index-*"))
    assert commit.call_args.args[4] == keys - {("svc", "alice", "A")}
    assert result["retained_keys"] == [["svc", "alice", "A"]]
    assert result["failures"][0]["code"] == "tenant_evidence_locked"
    assert scans.count(0) == 1


async def test_retention_analysis_is_discarded_before_final_sql_recheck(
    tmp_path,
    monkeypatch,
):
    import pytest

    state = {"written": False}
    scans = []

    async def many(_query, params):
        scans.append(params[-1])
        if not state["written"] or params[-1]:
            return []
        return [
            {
                "id": 1,
                "entry_kind": "session",
                "source_key": '["session","svc","alice","SRC","a"]',
                "details_text": None,
            },
        ]

    db = SimpleNamespace(
        fetch_one=AsyncMock(return_value=None),
        fetch_all=many,
    )
    key = {("svc", "alice")}
    with disk_index_policy(tmp_path.resolve(), 65536):
        with retry._ticket_analysis():
            await retry._no_data(db, JOB, key)
        state["written"] = True
        with pytest.raises(retry._TenantReviewHasData, match="ticket exists"):
            await retry._no_data(db, JOB, key)
        assert not list(tmp_path.glob("migration-index-*"))
    assert scans == [0, 0]


async def test_replaced_frozen_mapping_rebuilds_ownership(tmp_path):
    import pytest

    row = {
        "id": 1,
        "entry_kind": "session",
        "source_key": '["workspace","one"]/message:0',
        "details_text": None,
    }

    async def many(_query, params):
        return [row] if not params[-1] else []

    db = SimpleNamespace(
        fetch_one=AsyncMock(return_value=None),
        fetch_all=many,
    )
    old = [
        {
            "position": '["workspace","one"]',
            "service_unit_id": "svc",
            "tenant_id": "alice",
        },
    ]
    new = [{**old[0], "tenant_id": "bob"}]
    with disk_index_policy(tmp_path.resolve(), 65536):
        with retry._ticket_analysis():
            await retry._no_data(db, JOB, {("svc", "bob")}, old)
            with pytest.raises(retry._TenantReviewHasData):
                await retry._no_data(db, JOB, {("svc", "bob")}, new)
        assert not list(tmp_path.glob("migration-index-*"))


async def test_review_index_budget_failure_cleans_disposable_evidence(
    tmp_path,
):
    import pytest
    from swe.app.conversation_storage.migration.spool import (
        MigrationCapacityError,
    )

    async def many(_query, params):
        if params[-1]:
            return []
        return [
            {
                "id": i + 1,
                "entry_kind": "session",
                "details_text": None,
                "source_key": '["session","svc","'
                + str(i)
                + "x" * 1024
                + '","SRC","agent"]',
            }
            for i in range(1000)
        ]

    db = SimpleNamespace(
        fetch_one=AsyncMock(return_value=None),
        fetch_all=many,
    )
    with disk_index_policy(tmp_path.resolve(), 65536) as policy:
        with pytest.raises(MigrationCapacityError, match="disk budget"):
            with retry._ticket_analysis():
                await retry._no_data(db, JOB, {("svc", "empty")})
        assert policy.peak_bytes <= 65536
        assert not list(tmp_path.glob("migration-index-*"))


async def test_unattributable_ticket_is_fatal_and_index_is_cleaned(tmp_path):
    import pytest

    async def many(_query, _params):
        return [
            {
                "id": 1,
                "entry_kind": "batch",
                "source_key": "unknown",
                "details_text": None,
            },
        ]

    db = SimpleNamespace(
        fetch_one=AsyncMock(return_value=None),
        fetch_all=many,
    )
    with disk_index_policy(tmp_path.resolve(), 65536):
        with pytest.raises(ValueError, match="ownership cannot be proved"):
            with retry._ticket_analysis():
                await retry._no_data(db, JOB, {("svc", "alice")})
        assert not list(tmp_path.glob("migration-index-*"))


async def test_shared_scan_failure_propagates_and_does_not_leave_partial_index(
    tmp_path,
):
    import pytest

    for failure in (
        OSError(5, "shared IO failed"),
        ConnectionError("SQL owner lost"),
    ):
        db = SimpleNamespace(
            fetch_one=AsyncMock(return_value=None),
            fetch_all=AsyncMock(side_effect=failure),
        )
        with disk_index_policy(tmp_path.resolve(), 65536):
            with pytest.raises(type(failure)) as caught:
                with retry._ticket_analysis():
                    await retry._no_data(db, JOB, {("svc", "alice")})
            assert caught.value is failure
            assert not list(tmp_path.glob("migration-index-*"))


async def test_index_keeps_entity_batch_share_and_retention_ownership(
    tmp_path,
):
    import json
    import pytest

    workspace = {
        "position": '["workspace","one"]',
        "service_unit_id": "svc",
        "tenant_id": "alice",
        "source_id": "workspace-source",
    }
    shares = [
        {
            "position": "share-position",
            "token": "share-token",
            "service_unit_id": "svc",
            "tenant_id": "alice",
            "source_id": "share-source",
        },
    ]
    rows = [
        {
            "entry_kind": "session",
            "source_key": '["session","svc","alice","entity-source","a"]',
        },
        {
            "entry_kind": "message",
            "source_key": workspace["position"] + "/message:0",
        },
        {
            "entry_kind": "batch",
            "source_key": "batch",
            "details_text": json.dumps(
                {"scope": ["svc", "alice", "batch-source", "a"]},
            ),
        },
        {"entry_kind": "share", "source_key": "share-token"},
        {
            "entry_kind": "publication",
            "source_key": "share-position",
            "details_text": json.dumps({"scope_kind": "legacy_share"}),
        },
        {
            "entry_kind": "retention",
            "source_key": "retention",
            "details_text": json.dumps(
                {
                    "service_unit_key": "svc",
                    "tenant_key": "alice",
                    "source_key": "retention-source",
                },
            ),
        },
        {
            "entry_kind": "runtime_id",
            "source_key": "unattributable-runtime-id",
        },
    ]
    rows = [
        {"id": i + 1, "details_text": None, **row}
        for i, row in enumerate(rows)
    ]

    async def many(_query, params):
        if "migration_entries" not in _query:
            return []
        return rows if not params[-1] else []

    # No business records: every refusal below comes from a real ticket owner.
    db = SimpleNamespace(
        fetch_one=AsyncMock(return_value=None),
        fetch_all=many,
    )
    token = retry._SOURCE_MODE.set(True)
    try:
        with disk_index_policy(tmp_path.resolve(), 65536):
            with retry._ticket_analysis():
                await retry._no_data(
                    db,
                    JOB,
                    {("svc", "alice", "empty")},
                    [workspace],
                    shares,
                )
                for source in (
                    "entity-source",
                    "workspace-source",
                    "batch-source",
                    "share-source",
                    "retention-source",
                ):
                    with pytest.raises(
                        retry._TenantReviewHasData,
                        match="ticket exists",
                    ):
                        await retry._no_data(
                            db,
                            JOB,
                            {("svc", "alice", source)},
                            [workspace],
                            shares,
                        )
    finally:
        retry._SOURCE_MODE.reset(token)


async def test_review_proof_cannot_be_reused_by_another_sql_owner(tmp_path):
    import asyncio
    import pytest

    db = SimpleNamespace(
        fetch_one=AsyncMock(return_value=None),
        fetch_all=AsyncMock(return_value=[]),
    )
    with disk_index_policy(tmp_path.resolve(), 65536):
        with retry._ticket_analysis():
            await retry._no_data(db, JOB, {("svc", "alice")})
            with pytest.raises(RuntimeError, match="original SQL task"):
                await asyncio.create_task(
                    retry._no_data(db, JOB, {("svc", "alice")}),
                )
