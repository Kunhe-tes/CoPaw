# -*- coding: utf-8 -*-
import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.app.conversation_storage.migration.journal import MigrationJournal
from swe.app.conversation_storage.migration import tenant_retry as retry

JOB = "00000000-0000-4000-8000-000000000001"
SHARES = [
    {
        "service_unit_id": "svc",
        "tenant_id": "alice",
        "source_id": source,
        "position": "share-" + source,
        "token": source,
    }
    for source in ("A", "B")
]


def publication(source):
    return {
        "entry_kind": b"publication",
        "source_key": ("share-" + source).encode(),
        "details_text": json.dumps(
            {"scope_kind": "legacy_share", "scope": ["svc", "alice", "", ""]},
        ),
    }


def guard():
    return {
        "id": 3,
        "scope_kind": "legacy_share",
        "service_unit_key": b"svc",
        "tenant_key": b"alice",
        "source_key": b"",
        "agent_key": b"",
        "kind": "gc_guard",
        "publication_id": None,
        "retention_key": b"guard",
        "member_key": 0,
        "guard_marker": 1,
    }


async def test_capture_includes_owned_legacy_retention_and_shared_guard():
    rows = [
        {"id": 1, "scope_kind": "legacy_share", "publication_id": 11},
        {"id": 2, "scope_kind": "legacy_share", "publication_id": 12},
        guard(),
    ]
    db = SimpleNamespace(
        fetch_all=AsyncMock(return_value=rows),
        fetch_one=AsyncMock(
            side_effect=lambda _query, params: publication(
                "A" if params[-1] == 11 else "B",
            ),
        ),
    )
    manifest = SimpleNamespace(
        migration_id=JOB,
        data={
            "version": 3,
            "tenant_isolation": True,
            "source_isolation": True,
            "shares": SHARES,
        },
    )
    journal = MigrationJournal(db, manifest)
    # DirectImporter receives the source view, whose parent carries all frozen
    # share positions including already-published sibling sources.
    journal.manifest = SimpleNamespace(
        data={**manifest.data, "shares": [SHARES[0]]},
        parent=manifest,
    )
    journal.active_tenant = ("svc", "alice", "A")
    journal.record_retention = AsyncMock()
    await journal.capture_retentions()
    assert [
        call.args[0]["id"] for call in journal.record_retention.call_args_list
    ] == [
        1,
        3,
    ]
    query, params = db.fetch_all.call_args.args
    assert "scope_kind='legacy_share'" in query
    assert params[:3] == (b"svc", b"alice", b"A")


async def test_unknown_legacy_retention_cannot_disappear_from_capture():
    db = SimpleNamespace(
        fetch_all=AsyncMock(
            return_value=[
                {"id": 1, "scope_kind": "legacy_share", "publication_id": 11},
            ],
        ),
        fetch_one=AsyncMock(return_value=None),
    )
    journal = MigrationJournal(
        db,
        SimpleNamespace(
            migration_id=JOB,
            data={"version": 3, "tenant_isolation": True, "shares": SHARES},
        ),
    )
    journal.active_tenant = ("svc", "alice", "A")
    with pytest.raises(ValueError, match="unproven"):
        await journal.capture_retentions()


@pytest.mark.parametrize("indexed", [False, True])
async def test_empty_source_review_ignores_other_source_legacy_rows_but_checks_guard(
    indexed,
):
    current_guard = guard()
    details = {
        key: value.decode() if isinstance(value, bytes) else value
        for key, value in current_guard.items()
        if key != "id"
    }
    ticket = {
        "id": 9,
        "entry_kind": b"retention",
        "source_key": b"guard-ticket",
        "target_id": 3,
        "details_text": json.dumps(details),
    }

    async def one(query, params=None):
        if "entry_kind='publication'" in query:
            return publication("A")
        if "entry_kind='retention'" in query:
            return ticket
        if "retentions WHERE id=%s" in query:
            return current_guard
        assert (
            "scope_kind<>'legacy_share'" in query
            or "publications" not in query
            and "retentions" not in query
        )
        return None

    async def many(query, params=None):
        if "FROM swe_conversation_publications" in query:
            return [{"id": 11}]
        if "FROM swe_conversation_retentions" in query:
            return [{"id": 2, "publication_id": 11}, current_guard]
        return [ticket] if params[-1] == 0 else []

    db = SimpleNamespace(
        fetch_one=AsyncMock(side_effect=one),
        fetch_all=AsyncMock(side_effect=many),
    )
    token = retry._SOURCE_MODE.set(True)
    try:
        with retry._ticket_analysis() if indexed else nullcontext():
            await retry._no_data(
                db,
                JOB,
                {("svc", "alice", "")},
                shares=SHARES,
            )
        with pytest.raises(retry._TenantReviewHasData):
            await retry._no_data(
                db,
                JOB,
                {("svc", "alice", "A")},
                shares=SHARES,
            )
        current_guard["guard_marker"] = 0
        with pytest.raises(ValueError, match="guard differs"):
            await retry._no_data(
                db,
                JOB,
                {("svc", "alice", "")},
                shares=SHARES,
            )
    finally:
        retry._SOURCE_MODE.reset(token)


async def test_legacy_retention_ticket_uses_publication_frozen_owner():
    row = {
        "entry_kind": b"retention",
        "source_key": b"opaque",
        "details_text": json.dumps(
            {
                "scope_kind": "legacy_share",
                "service_unit_key": "svc",
                "tenant_key": "alice",
                "source_key": "",
                "agent_key": "",
                "publication_id": 11,
            },
        ),
    }
    db = SimpleNamespace(fetch_one=AsyncMock(return_value=publication("A")))
    token = retry._SOURCE_MODE.set(True)
    try:
        assert await retry._retention_owner(db, JOB, row, SHARES) == (
            "svc",
            "alice",
            "A",
        )
        assert retry._ticket_owner(
            {**publication("A"), "entry_kind": b"batch"},
            shares=SHARES,
        ) == ("svc", "alice", "A")
        with pytest.raises(ValueError, match="ownership"):
            await retry._retention_owner(db, JOB, row, [])
    finally:
        retry._SOURCE_MODE.reset(token)
