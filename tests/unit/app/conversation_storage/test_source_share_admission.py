# -*- coding: utf-8 -*-
"""First request and legacy-share reads enforce exact source publication."""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.app.conversation_storage import runtime
from swe.app.conversation_storage.bundle import BundleStore
from swe.app.conversation_storage.errors import (
    IntegrityError,
    StorageUnavailable,
)
from swe.app.conversation_storage.shares import ShareStorage
from swe.app.conversation_storage.tenant_admission import (
    TenantAdmission,
    TenantNotPublished,
)
from swe.config.context import encode_scope_id

JOB = "00000000-0000-4000-8000-000000000001"


async def test_first_request_validates_binding_before_decoding_source_admission(
    monkeypatch,
):
    admission = SimpleNamespace()

    async def validate():
        admission.source_binding = {"source_isolation": True}

    admission.validate = AsyncMock(side_effect=validate)
    instance = SimpleNamespace(admission=admission, admit=AsyncMock())
    monkeypatch.setenv(runtime.AUTHORITY_ENV, "mysql")
    monkeypatch.setattr(runtime, "_runtime", instance)
    await runtime.require_tenant_published(encode_scope_id("alice", "SRC"))
    admission.validate.assert_awaited_once()
    instance.admit.assert_awaited_once_with("alice", "SRC")


@pytest.mark.parametrize(
    "owners,published",
    [([], True), (["A", "B"], True), (["B"], False), (["B"], True)],
)
async def test_legacy_share_token_evidence_selects_exact_published_source(
    tmp_path,
    monkeypatch,
    owners,
    published,
):
    record = SimpleNamespace(
        tenant_id="alice",
        publication_id=1,
        byte_offset=0,
        byte_length=2,
    )
    pin = AsyncMock(
        side_effect=AssertionError("read must stop after admission"),
    )

    @asynccontextmanager
    async def transaction():
        yield

    async def fetch_one(query, params=None):
        if "migration_jobs" in query:
            return {
                "target_binding_text": json.dumps(
                    {
                        "server_uuid": "server",
                        "schema": "test",
                        "migration_id": JOB,
                        "nas_roots": {"svc": str(tmp_path)},
                    },
                ),
                "source_binding_text": '{"tenant_isolation":true,"source_isolation":true}',
            }
        if "@@server_uuid" in query:
            return {"server_uuid": "server", "schema_name": "test"}
        if "migration_sources" in query:
            assert params[-1] == b"B"
            return {
                "state": "published" if published else "failed",
                "verification_text": json.dumps(
                    {
                        "version": 1,
                        "migration_id": JOB,
                        "services": {
                            "svc": {
                                "nas_root": str(tmp_path),
                                "workspaces": [],
                            },
                        },
                    },
                ),
            }
        assert "source_key,scope_kind" in query
        assert params == (1, b"svc", b"alice")
        return {"source_key": b"", "scope_kind": "legacy_share"}

    async def fetch_all(query, params):
        assert "migration_sources" in query
        assert params == (JOB.encode(), b"svc", b"alice")
        return [
            {
                "source_key": source.encode(),
                "evidence_text": json.dumps(
                    {
                        "shares": [
                            {
                                "token": (
                                    "token" if source in owners else "other"
                                ),
                            },
                        ],
                    },
                ),
            }
            for source in ("A", "B")
        ]

    db = SimpleNamespace(
        transaction=transaction,
        fetch_one=AsyncMock(side_effect=fetch_one),
        fetch_all=AsyncMock(side_effect=fetch_all),
    )
    admission = TenantAdmission(
        db,
        {
            "version": 3,
            "service_unit_id": "svc",
            "nas_root": str(tmp_path),
            "migration_id": JOB,
        },
    )
    storage = ShareStorage(
        db,
        BundleStore(tmp_path),
        service_unit_id="svc",
        admission=admission,
    )
    monkeypatch.setattr(storage.store, "get", AsyncMock(return_value=record))
    if len(owners) != 1:
        with pytest.raises(StorageUnavailable) as failure:
            await storage.read_snapshot("token", record_access=False)
        assert isinstance(failure.value.__cause__, IntegrityError)
        assert "ambiguous" in str(failure.value.__cause__)
    elif not published:
        with pytest.raises(StorageUnavailable) as failure:
            await storage.read_snapshot("token", record_access=False)
        assert isinstance(failure.value.__cause__, TenantNotPublished)
    else:
        # The second publication read proves source admission passed. It must
        # never run for missing, ambiguous or failed source evidence.
        original = db.fetch_one.side_effect

        async def stop_after_admission(query, params=None):
            if query.startswith("SELECT * FROM swe_conversation_publications"):
                await pin()
            return await original(query, params)

        db.fetch_one.side_effect = stop_after_admission
        with pytest.raises(AssertionError, match="after admission"):
            await storage.read_snapshot("token", record_access=False)
        pin.assert_awaited_once()
    if not published or len(owners) != 1:
        assert not any(
            call.args[0].startswith(
                "SELECT * FROM swe_conversation_publications",
            )
            for call in db.fetch_one.await_args_list
        )
