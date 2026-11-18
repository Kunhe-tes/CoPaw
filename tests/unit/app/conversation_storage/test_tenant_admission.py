# -*- coding: utf-8 -*-
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.app.conversation_storage.tenant_admission import (
    TenantAdmission,
    TenantDatabase,
    TenantNotPublished,
)
from swe.app.conversation_storage.errors import IntegrityError

JOB = "00000000-0000-4000-8000-000000000001"


def database(state="failed", tenant="alice", *, source_mode=False):
    proof = {
        "version": 1,
        "migration_id": JOB,
        "services": {
            "svc": {
                "nas_root": "/nas",
                "workspaces": [
                    {
                        "root": "/workspace",
                        "scope": ["svc", tenant, "SRC", "agent"],
                    },
                ],
            },
        },
    }

    async def fetch(query, params=None):
        if "migration_jobs" in query:
            return {
                "target_binding_text": json.dumps(
                    {
                        "migration_id": JOB,
                        "nas_roots": {"svc": "/nas"},
                        "server_uuid": "server",
                        "schema": "test",
                    },
                ),
                "source_binding_text": json.dumps(
                    {
                        "tenant_isolation": True,
                        "source_isolation": source_mode,
                    },
                ),
            }
        if "@@server_uuid" in query:
            return {"server_uuid": "server", "schema_name": "test"}
        if "migration_sources" in query:
            assert source_mode
            assert params[-1] == b"SRC"
            return {"state": db.state, "verification_text": json.dumps(proof)}
        if "migration_tenants" in query:
            return {"state": db.state, "verification_text": json.dumps(proof)}
        raise AssertionError(query)

    db = SimpleNamespace(state=state, fetch_one=AsyncMock(side_effect=fetch))
    admission = TenantAdmission(
        db,
        {
            "version": 3,
            "service_unit_id": "svc",
            "nas_root": "/nas",
            "migration_id": JOB,
        },
    )
    return db, admission


async def test_manifest_binding_uses_existing_runtime_path(
    tmp_path,
    monkeypatch,
):
    db, admission = database("published", source_mode=True)
    original_fetch = db.fetch_one.side_effect
    manifest = {
        "migration_id": JOB,
        "source_binding_storage": "manifest-v1",
        "tenant_isolation": True,
        "source_isolation": True,
        "services": [],
        "workspaces": [],
        "tenants": [],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setenv(
        "SWE_CONVERSATION_SCOPE_MANIFEST",
        str(tmp_path / "scopes.json"),
    )

    async def fetch(query, params=None):
        result = await original_fetch(query, params)
        if "migration_jobs" in query:
            result["source_binding_text"] = json.dumps(
                {
                    "source_binding_storage": "manifest-v1",
                    "tenant_isolation": True,
                    "source_isolation": True,
                },
            )
        return result

    db.fetch_one.side_effect = fetch
    assert await admission.require("alice", "SRC")
    assert admission.source_binding == manifest


@pytest.mark.parametrize(
    "operation",
    ["authority", "capture", "gc", "rollback"],
)
async def test_source_published_admission_for_backup_gc_and_rollback(
    monkeypatch,
    tmp_path,
    operation,
):
    from swe.app.conversation_storage.identity import WorkspaceScope
    from swe.app.conversation_storage.bundle import BundleStore
    from swe.app.conversation_storage.backup import ConversationBackup
    from swe.app.conversation_storage.gc import GarbageCollector
    from swe.app.conversation_storage.migration.authority import (
        backup_authority,
    )
    from swe.app.conversation_storage.migration.manifest import SourceBoundary
    from swe.app.conversation_storage.migration import (
        tenant_rollback as rollback,
    )
    import swe.app.conversation_storage.tenant_admission as module

    scope = WorkspaceScope("alice", "SRC", "agent", service_unit_id="svc")
    db, admission = database("published", source_mode=True)
    monkeypatch.setattr(
        module,
        "partial_admission",
        AsyncMock(return_value=admission),
    )
    if operation == "authority":
        proof = await backup_authority(db, scope)
        assert proof["services"]["svc"]["workspaces"][0]["scope"] == list(
            scope.values,
        )
    elif operation == "capture":
        backup = ConversationBackup(db, BundleStore(tmp_path), scope)
        await backup._check_capture_admission(None)
    elif operation == "gc":
        collector_db = SimpleNamespace(fetch_one=AsyncMock(return_value=None))
        collector = GarbageCollector(
            collector_db,
            scope,
            BundleStore(tmp_path),
        )
        reasons = await collector._protections(
            {
                "id": 1,
                "state": "committed",
                "retained_history": False,
                "session_id": None,
                "chat_id": None,
                "turn_id": None,
            },
        )
        assert "migration_tenant_unpublished" not in reasons
    else:
        evidence = rollback.TenantRollbackEvidence(
            SourceBoundary(
                "snapshot",
                "2026-11-16T00:00:00Z",
                "old@sha256:" + "a" * 64,
                ("record",),
            ),
            "stop",
            "drain",
            "review",
        )
        authorization = rollback.RollbackBackupAuthorization(
            evidence,
            SimpleNamespace(migration_id=JOB, data={"services": []}),
            ({},),
            scope,
            "/workspace",
        )
        monkeypatch.setattr(
            rollback,
            "validate_current_config",
            lambda *_: [{"root": "/workspace", "scope": list(scope.values)}],
        )
        await rollback.validate_backup_authorization(authorization, db, scope)


async def test_partial_jobs_detects_source_table_without_tenant_table():
    from swe.app.conversation_storage.tenant_admission import partial_jobs

    async def tables(query):
        assert "'swe_conversation_migration_sources'" in query
        return {"tenant_controls": 1}

    row = {
        "source_binding_text": json.dumps(
            {"tenant_isolation": True, "source_isolation": True},
        ),
        "target_binding_text": json.dumps({"nas_roots": {"svc": "/nas"}}),
    }
    db = SimpleNamespace(
        fetch_one=AsyncMock(side_effect=tables),
        fetch_all=AsyncMock(return_value=[row]),
    )
    assert await partial_jobs(db, "svc") == [
        (row, {"nas_roots": {"svc": "/nas"}}),
    ]


async def test_failed_then_published_is_visible_without_restart():
    db, admission = database()
    with pytest.raises(TenantNotPublished):
        await admission.require("alice")
    db.state = "published"
    assert (await admission.require("alice"))[0]["scope"][1] == "alice"


async def test_published_proof_cannot_cover_other_tenant():
    _db, admission = database("published", tenant="bob")
    with pytest.raises(IntegrityError, match="proof"):
        await admission.require("alice")


async def test_cached_adapter_checks_each_query_and_never_swallows_db_failure():
    db, admission = database("published")
    db.execute = AsyncMock(return_value=1)
    guarded = TenantDatabase(db, admission, "alice")
    assert await guarded.execute("UPDATE business") == 1
    db.state = "failed"
    with pytest.raises(TenantNotPublished):
        await guarded.execute("UPDATE business")
    assert db.execute.await_count == 1
    db.fetch_one.side_effect = ConnectionError("offline")
    with pytest.raises(ConnectionError):
        await guarded.execute("UPDATE business")


async def test_partial_backup_uses_published_scope_only(monkeypatch):
    from swe.app.conversation_storage.migration.authority import (
        backup_authority,
    )
    from swe.app.conversation_storage.identity import WorkspaceScope
    import swe.app.conversation_storage.tenant_admission as module

    db, admission = database("published")
    monkeypatch.setattr(
        module,
        "partial_admission",
        AsyncMock(return_value=admission),
    )
    proof = await backup_authority(
        db,
        WorkspaceScope("alice", "SRC", "agent", service_unit_id="svc"),
    )
    assert proof["services"]["svc"]["workspaces"][0]["scope"][1] == "alice"
    db.state = "failed"
    with pytest.raises(TenantNotPublished):
        await backup_authority(
            db,
            WorkspaceScope("alice", "SRC", "agent", service_unit_id="svc"),
        )


async def test_gc_protects_unpublished_migration_even_without_business_references(
    monkeypatch,
    tmp_path,
):
    from swe.app.conversation_storage.gc import GarbageCollector
    from swe.app.conversation_storage.identity import WorkspaceScope
    from swe.app.conversation_storage.bundle import BundleStore
    import swe.app.conversation_storage.tenant_admission as module

    admission = SimpleNamespace(
        require=AsyncMock(side_effect=TenantNotPublished()),
    )
    monkeypatch.setattr(
        module,
        "partial_admission",
        AsyncMock(return_value=admission),
    )
    db = SimpleNamespace(fetch_one=AsyncMock(return_value=None))
    collector = GarbageCollector(
        db,
        WorkspaceScope("alice", "SRC", "agent", service_unit_id="svc"),
        BundleStore(tmp_path),
    )
    reasons = await collector._protections(
        {
            "id": 1,
            "state": "committed",
            "retained_history": False,
            "session_id": None,
            "chat_id": None,
            "turn_id": None,
        },
    )
    assert "migration_tenant_unpublished" in reasons


async def test_restore_rejects_active_partial_job_before_insert(monkeypatch):
    from swe.app.conversation_storage.migration.authority import (
        restore_authorities,
    )
    import swe.app.conversation_storage.tenant_admission as module

    monkeypatch.setattr(
        module,
        "partial_jobs",
        AsyncMock(return_value=[object()]),
    )
    db = SimpleNamespace(insert=AsyncMock())
    with pytest.raises(IntegrityError, match="active partial"):
        await restore_authorities(db, [], [], {})
    db.insert.assert_not_awaited()


async def test_acquired_session_and_bulk_operations_cannot_bypass_admission():
    from contextlib import asynccontextmanager

    db, admission = database("published")
    session = SimpleNamespace(
        fetch_all=AsyncMock(return_value=[]),
        _in_transaction=True,
    )

    @asynccontextmanager
    async def acquire():
        yield session

    db.acquire = acquire
    db.execute_result = AsyncMock(return_value=1)
    db.execute_many = AsyncMock(return_value=2)
    guarded = TenantDatabase(db, admission, "alice")
    assert await guarded.execute_many("UPDATE business", []) == 2
    assert await guarded.execute_result("UPDATE business") == 1
    async with guarded.acquire() as lease:
        assert lease._in_transaction
        assert await lease.fetch_all("SELECT business") == []
        db.state = "failed"
        with pytest.raises(TenantNotPublished):
            await lease.fetch_all("SELECT business")
    with pytest.raises(TenantNotPublished):
        async with guarded.acquire():
            pytest.fail("unpublished tenant acquired SQL lease")
    with pytest.raises(TenantNotPublished):
        await guarded.execute_many("UPDATE business", [])
    assert session.fetch_all.await_count == 1
    assert db.execute_many.await_count == 1


async def test_maintenance_http_response_is_503_and_does_not_expose_failure():
    from swe.app.conversation_storage.tenant_admission import (
        tenant_maintenance_response,
    )

    response = await tenant_maintenance_response(None, TenantNotPublished())
    assert response.status_code == 503
    assert json.loads(response.body) == {
        "detail": "Conversation tenant is under maintenance",
        "code": "conversation_tenant_not_published",
    }


@pytest.mark.parametrize("from_middleware", [True, False])
async def test_tenant_denial_is_http_503_in_middleware_and_endpoint(
    monkeypatch,
    from_middleware,
):
    import httpx
    from fastapi import FastAPI
    import swe.app.middleware.tenant_workspace as middleware
    from swe.app.conversation_storage.tenant_admission import (
        tenant_maintenance_response,
    )

    app = FastAPI(
        exception_handlers={TenantNotPublished: tenant_maintenance_response},
    )

    @app.get("/denied")
    async def denied():
        raise TenantNotPublished()

    if from_middleware:
        monkeypatch.setattr(
            middleware,
            "_get_effective_request_tenant_id",
            lambda request: "alice",
        )
        monkeypatch.setattr(
            middleware.TenantWorkspaceMiddleware,
            "_is_workspace_exempt",
            lambda self, path: False,
        )
        monkeypatch.setattr(
            middleware.TenantWorkspaceMiddleware,
            "_get_workspace",
            AsyncMock(side_effect=TenantNotPublished()),
        )
        app.add_middleware(middleware.TenantWorkspaceMiddleware)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/denied")
    assert response.status_code == 503
    assert response.json()["code"] == "conversation_tenant_not_published"
