# -*- coding: utf-8 -*-
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.app.conversation_storage.migration import tenant_retry as retry

JOB = "00000000-0000-4000-8000-000000000001"


def test_ticket_identity_with_slashes_is_parsed_as_json_not_split():
    row = {
        "source_key": '["session","svc","a/b","SRC","agent","user","console","sid"]/message:0',
        "details_text": None,
    }
    assert retry._ticket_owner(row) == ("svc", "a/b")
    with pytest.raises(ValueError, match="cannot be proved"):
        retry._ticket_owner(
            {"source_key": "unknown:ticket", "details_text": None},
        )


async def test_review_rejects_unknown_or_affected_ticket():
    db = SimpleNamespace(
        fetch_one=AsyncMock(return_value=None),
        fetch_all=AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "source_key": '["session","svc","alice","SRC","agent"]',
                    "details_text": None,
                },
            ],
        ),
    )
    with pytest.raises(ValueError, match="ticket exists"):
        await retry._no_data(db, JOB, {("svc", "alice")})
    db.fetch_all.return_value = [
        {"id": 1, "source_key": "unknown", "details_text": None},
    ]
    with pytest.raises(ValueError):
        await retry._no_data(db, JOB, {("svc", "alice")})


async def test_review_rejects_business_data_without_deleting():
    async def existing_row(query, params=None):
        if "LEFT JOIN" in query:
            return None
        return {"id": 1}

    db = SimpleNamespace(fetch_one=AsyncMock(side_effect=existing_row))
    with pytest.raises(ValueError, match="business data exists"):
        await retry._no_data(db, JOB, {("svc", "alice")})


async def test_review_excludes_old_share_publications_for_new_manifests():
    queries = []

    async def fetch_one(query, _params=None):
        queries.append(query)
        return None

    async def fetch_all(query, _params=None):
        queries.append(query)
        return []

    db = SimpleNamespace(
        fetch_one=AsyncMock(side_effect=fetch_one),
        fetch_all=AsyncMock(side_effect=fetch_all),
    )
    await retry._no_data(
        db,
        JOB,
        {("svc", "alice", "source")},
        shares=[{"token": "old-share"}],
        exclude_historical_shares=True,
    )
    assert not any("scope_kind='legacy_share'" in query for query in queries)


@pytest.mark.parametrize("outcome", ["old", "new", "unknown"])
@pytest.mark.parametrize("new_state", ["discovered", "failed"])
async def test_recovery_requires_matching_sql_evidence_and_retains_unknown(
    tmp_path,
    monkeypatch,
    outcome,
    new_state,
):
    old, new = {"migration_id": JOB, "version": 3, "source": "old"}, {
        "migration_id": JOB,
        "version": 3,
        "source": "new",
    }
    new["tenant_review_failures"] = [
        {
            "service_unit_id": "svc",
            "tenant_id": "bob",
            "stage": "retry-review",
            "code": "tenant_boundary_invalid",
            "reason": retry._REVIEW_REASONS["tenant_boundary_invalid"],
        },
    ]
    monkeypatch.setattr(retry, "_source", lambda data: data["source"])
    snapshots = {}
    for label, data in (("old", old), ("new", new)):
        path = tmp_path / (label + ".json")
        retry._write(path, data)
        snapshots[label] = {"name": path.name, "sha256": retry._digest(data)}
    manifest = SimpleNamespace(
        path=tmp_path / "manifest.json",
        migration_id=JOB,
        data=dict(old),
        _persist=lambda: None,
    )
    pending = {
        "migration_id": JOB,
        "revision": "revision",
        "old_source": "old",
        "new_source": "new",
        "files": snapshots,
        "tenants": [
            {
                "service": "svc",
                "tenant": "alice",
                "old": "before",
                "new": "after",
                "old_state": "failed",
                "new_state": new_state,
            },
        ],
    }
    retry._write(retry._pending(manifest), pending)

    @asynccontextmanager
    async def transaction():
        yield

    async def fetch(query, params):
        if "migration_jobs" in query:
            return {
                "source_binding_text": outcome,
                "verification_text": json.dumps(
                    (
                        {"tenant_review_revision": "revision"}
                        if outcome == "new"
                        else {}
                    ),
                ),
            }
        return {
            "state": new_state if outcome == "new" else "failed",
            "evidence_text": "after" if outcome == "new" else "before",
        }

    db = SimpleNamespace(transaction=transaction, fetch_one=fetch)
    monkeypatch.setattr(
        retry.V3Manifest,
        "load",
        lambda path: SimpleNamespace(
            data=json.loads(path.read_text()),
            migration_id=JOB,
        ),
    )
    if outcome == "unknown":
        with pytest.raises(ValueError, match="unknown"):
            await retry.recover_pending_review(db, manifest)
        assert retry._pending(manifest).exists()
    else:
        recovered = await retry.recover_pending_review(db, manifest)
        assert recovered["outcome"] == outcome
        assert recovered["failures"] == (
            new["tenant_review_failures"] if outcome == "new" else []
        )
        assert manifest.data["source"] == outcome
        assert not retry._pending(manifest).exists()
        assert list(tmp_path.glob("*.audit.json"))


@pytest.mark.parametrize("unknown_commit", [True, False])
@pytest.mark.parametrize("new_state", ["discovered", "failed"])
async def test_review_corrected_failed_tenant_preserves_published_scope_and_pending_on_unknown_commit(
    tmp_path,
    monkeypatch,
    unknown_commit,
    new_state,
):
    from copy import deepcopy

    service = {
        "service_unit_id": "svc",
        "source_root": "/frozen",
        "config_root": "/frozen",
        "original_root": "/runtime",
        "nas_root": "/nas",
    }
    alice = {
        "service_unit_id": "svc",
        "tenant_id": "alice",
        "source_id": "SRC",
        "agent_id": "a",
        "position": "alice",
        "root": "/frozen/a",
        "runtime_root": "/runtime/a",
        "counts": {"sessions": 0, "chats": 0},
        "empty": True,
    }
    tenants = [
        {
            "service_unit_id": "svc",
            "tenant_id": "alice",
            "state": "discovered",
            "blockers": [],
        },
        {
            "service_unit_id": "svc",
            "tenant_id": "bob",
            "state": "failed",
            "blockers": [{"code": "config_invalid"}],
        },
    ]
    data = {
        "version": 3,
        "migration_id": JOB,
        "tenant_isolation": True,
        "services": [service],
        "declared_services": [service],
        "source_shares": [],
        "shares": [],
        "tenants": tenants,
        "workspaces": [alice],
        "blockers": [{"code": "config_invalid"}],
        "ready": False,
        "status": "partial_success",
        "target": {
            "migration_id": JOB,
            "schema": "test",
            "nas_roots": {"svc": "/nas"},
        },
        "assignments": {},
        "batches": {},
    }
    report = {
        k: deepcopy(v)
        for k, v in data.items()
        if k not in ("target", "migration_id", "assignments", "batches")
    }
    bob = {
        **alice,
        "tenant_id": "bob",
        "position": "bob",
        "root": "/frozen/b",
        "runtime_root": "/runtime/b",
    }
    report["workspaces"].append(bob)
    report["tenants"][1].update(
        state=new_state,
        blockers=(
            []
            if new_state == "discovered"
            else [{"code": "tenant_boundary_invalid"}]
        ),
    )
    report.update(blockers=[], ready=True, status="success")
    monkeypatch.setattr(
        retry,
        "discover_services",
        lambda *args, **kwargs: report,
    )
    manifest = SimpleNamespace(
        data=data,
        path=tmp_path / "manifest.json",
        migration_id=JOB,
    )
    data["tenant_sync_started_at_ns"] = {
        "svc\x00alice": 100,
        "svc\x00bob": 100,
    }
    data["source_change_blockers"] = [
        {"scope": ["svc", "bob"], "detail": "old"},
        {"scope": ["svc", "alice"], "detail": "keep"},
    ]
    old_source = retry._source(data)
    records = {
        "alice": {
            "state": "published",
            "evidence_text": retry._json(
                retry._evidence(data, ("svc", "alice")),
            ),
        },
        "bob": {
            "state": "failed",
            "evidence_text": retry._json(
                retry._evidence(data, ("svc", "bob")),
            ),
        },
    }

    @asynccontextmanager
    async def transaction():
        yield
        if unknown_commit:
            raise ConnectionError("commit outcome unknown")

    async def fetch(query, params=None):
        if "migration_tenants" in query:
            return records[params[2].decode()]
        if "migration_jobs" in query:
            return {
                "source_binding_text": old_source,
                "verification_text": "{}",
            }
        return None

    db = SimpleNamespace(
        transaction=transaction,
        fetch_one=fetch,
        fetch_all=AsyncMock(return_value=[]),
        execute=AsyncMock(return_value=1),
    )
    if unknown_commit:
        with pytest.raises(ConnectionError, match="unknown"):
            await retry.review_retry(db, manifest, report)
    else:
        recover = AsyncMock(return_value={"outcome": "new"})
        monkeypatch.setattr(retry, "recover_pending_review", recover)
        assert (await retry.review_retry(db, manifest, report))[
            "outcome"
        ] == "new"
        recover.assert_awaited_once_with(db, manifest)
    assert retry._pending(manifest).exists()
    pending = json.loads(retry._pending(manifest).read_text())
    assert [r["tenant"] for r in pending["tenants"]] == ["bob"]
    assert pending["tenants"][0]["new_state"] == new_state
    tenant_update = db.execute.await_args_list[-1].args[1]
    assert tenant_update[1] == new_state
    assert (tenant_update[2] is not None) == (new_state == "failed")
    new_data = json.loads(
        (tmp_path / pending["files"]["new"]["name"]).read_text(),
    )
    assert new_data["tenant_sync_started_at_ns"]["svc\x00alice"] == 100
    assert new_data["tenant_sync_started_at_ns"]["svc\x00bob"] > 100
    assert new_data["source_change_blockers"] == [
        {"scope": ["svc", "alice"], "detail": "keep"},
    ]
    assert manifest.data == data
    assert db.execute.await_count == 2


def test_workspace_prefix_ticket_uses_exact_original_position():
    position = '["workspace","svc","tenant/workspaces/agent"]'
    workspace = {
        "position": position,
        "service_unit_id": "svc",
        "tenant_id": "alice",
    }
    assert retry._ticket_owner(
        {
            "source_key": position + "/session:0/message:1",
            "details_text": None,
        },
        [workspace],
    ) == ("svc", "alice")
    with pytest.raises(ValueError):
        retry._ticket_owner(
            {"source_key": position + "evil/session:0", "details_text": None},
            [workspace],
        )


async def test_runtime_tickets_do_not_prevent_zero_data_tenant_review():
    db = SimpleNamespace(
        fetch_one=AsyncMock(return_value=None),
        fetch_all=AsyncMock(
            side_effect=[
                [
                    {
                        "id": 1,
                        "entry_kind": b"runtime_id",
                        "source_key": b"opaque",
                        "details_text": None,
                    },
                ],
                [],
            ],
        ),
    )
    await retry._no_data(db, JOB, {("svc", "bob")})
    queries = [call.args[0] for call in db.fetch_one.call_args_list]
    assert any(
        "swe_conversation_turns b JOIN swe_conversation_sessions" in query
        for query in queries
    )
    assert any(
        "FROM swe_conversation_publications WHERE service_unit_key=%s" in query
        for query in queries
    )


def test_retention_and_share_tickets_have_explicit_verified_owners():
    retention = {
        "entry_kind": b"retention",
        "source_key": b"retention",
        "details_text": json.dumps(
            {"service_unit_key": "svc", "tenant_key": "alice"},
        ),
    }
    assert retry._ticket_owner(retention) == ("svc", "alice")
    share = {
        "entry_kind": b"share",
        "source_key": b"opaque-token",
        "details_text": "{}",
    }
    assert retry._ticket_owner(
        share,
        shares=[
            {
                "token": "opaque-token",
                "service_unit_id": "svc",
                "tenant_id": "alice",
            },
        ],
    ) == ("svc", "alice")
    with pytest.raises(ValueError, match="share ownership"):
        retry._ticket_owner(share)


async def test_in_place_review_repairs_b_without_reading_live_a(
    tmp_path,
    monkeypatch,
):
    from pathlib import Path
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
    )
    from swe.config.context import encode_scope_id

    root, nas = tmp_path / "root", tmp_path / "nas"
    root.mkdir()
    nas.mkdir()
    configs = {}
    for tenant in ("alice", "bob"):
        folder = root / encode_scope_id(tenant, "SRC")
        workspace = folder / "workspaces" / "agent"
        workspace.mkdir(parents=True)
        (workspace / "agent.json").write_text('{"id":"agent"}')
        (workspace / "chats.json").write_text('{"version":1,"chats":[]}')
        config = folder / "config.json"
        configs[tenant] = config
        config.write_text(
            json.dumps(
                {
                    "agents": {
                        "profiles": {
                            "agent": {
                                "id": "agent",
                                "workspace_dir": str(workspace),
                            },
                        },
                    },
                },
            ),
        )
    good_b = configs["bob"].read_text()
    configs["bob"].write_text("{invalid")
    for path in root.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    root.chmod(0o555)
    service = {
        "service_unit_id": "svc",
        "source_root": str(root),
        "config_root": str(root),
        "snapshot_root": str(root),
        "original_root": str(root),
        "nas_root": str(nas),
    }
    report = discover_services([service], tenant_isolation=True, in_place=True)
    data = {
        **report,
        "migration_id": JOB,
        "version": 3,
        "target": {
            "schema": "test",
            "nas_roots": {"svc": str(nas)},
            "migration_id": JOB,
        },
        "assignments": {},
        "batches": {},
    }
    # Overrides bind a workspace position, not a service_unit_id field. A's
    # frozen override must be retained without attempting to resolve live A.
    published_override = {
        "position": next(
            w["position"]
            for w in data["workspaces"]
            if w["tenant_id"] == "alice"
        ),
        "tenant_id": "alice",
        "reason": "reviewed exceptional session path",
    }
    data["overrides"] = report["overrides"] = [published_override]
    for tenant in ("alice", "bob"):
        configs[tenant].chmod(0o644)
    configs["alice"].write_text("live mutated config cannot be parsed")
    configs["bob"].write_text(good_b)
    configs["bob"].chmod(0o444)
    original_read = Path.read_bytes

    def forbid_a(path):
        if encode_scope_id("alice", "SRC") in path.parts:
            pytest.fail("published source read during review")
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", forbid_a)
    manifest = SimpleNamespace(
        data=data,
        path=tmp_path / "manifest.json",
        migration_id=JOB,
    )

    async def get(_self, service, tenant, **kwargs):
        return {"state": "published" if tenant == "alice" else "failed"}

    monkeypatch.setattr(retry.TenantState, "get", get)
    monkeypatch.setattr(retry, "_no_data", AsyncMock())
    committed = AsyncMock()
    monkeypatch.setattr(retry, "_commit_review", committed)
    monkeypatch.setattr(
        retry,
        "recover_pending_review",
        AsyncMock(return_value={"outcome": "new"}),
    )
    await retry.review_retry(None, manifest, report)
    new_data = committed.call_args.args[3]
    assert (
        next(t for t in new_data["tenants"] if t["tenant_id"] == "bob")[
            "state"
        ]
        == "discovered"
    )
    assert new_data["overrides"] == [published_override]
    assert retry._evidence(new_data, ("svc", "alice")) == retry._evidence(
        data,
        ("svc", "alice"),
    )
    root.chmod(0o755)
    unknown = root / encode_scope_id("charlie", "SRC")
    unknown.mkdir()
    (unknown / "config.json").write_text('{"agents":{"profiles":{}}}')
    with pytest.raises(ValueError, match="add or remove tenants"):
        await retry.review_retry(None, manifest, report)


@pytest.mark.parametrize("published_conflict", [False, True])
async def test_review_boundary_failure_isolated_unless_published_scope_affected(
    tmp_path,
    monkeypatch,
    published_conflict,
):
    from copy import deepcopy

    roots = {
        "alice": tmp_path / "a",
        "bob": tmp_path / ("a/child" if published_conflict else "shared"),
        "carol": tmp_path / "shared/child",
        "dave": tmp_path / "d",
    }
    report = {
        "services": [
            {
                "service_unit_id": "svc",
                "source_root": str(tmp_path),
                "original_root": str(tmp_path),
            },
        ],
        "tenants": [
            {
                "service_unit_id": "svc",
                "tenant_id": tenant,
                "state": "discovered",
                "blockers": [],
            }
            for tenant in roots
        ],
        "workspaces": [
            {
                "service_unit_id": "svc",
                "tenant_id": tenant,
                "runtime_root": str(root),
                "position": tenant,
                "evidence_refs": [],
            }
            for tenant, root in roots.items()
        ],
        "shares": [],
        "overrides": [],
        "blockers": [],
        "ready": True,
        "status": "success",
    }
    old = deepcopy(report)
    old["workspaces"][1]["runtime_root"] = str(tmp_path / "old-b")
    old["tenants"][3].update(
        state="failed",
        blockers=[{"code": "config_invalid"}],
    )
    if published_conflict:
        retry._review_boundaries(report, {("svc", "alice")}, old)
        for tenant in ("alice", "bob", "dave"):
            assert [
                w for w in report["workspaces"] if w["tenant_id"] == tenant
            ] == [w for w in old["workspaces"] if w["tenant_id"] == tenant]
        assert (
            next(t for t in report["tenants"] if t["tenant_id"] == "bob")[
                "state"
            ]
            == "failed"
        )
        assert (
            next(t for t in report["tenants"] if t["tenant_id"] == "dave")[
                "state"
            ]
            == "discovered"
        )
    else:
        retry._review_boundaries(report, {("svc", "alice")}, old)
        states = {
            item["tenant_id"]: item["state"] for item in report["tenants"]
        }
        assert states == {
            "alice": "discovered",
            "bob": "failed",
            "carol": "failed",
            "dave": "discovered",
        }
        assert {
            json.loads(item["position"])[1] for item in report["blockers"]
        } == {"bob", "carol"}
        assert report["status"] == "partial_success"

    for data in (old, report):
        data.update(
            in_place=True,
            tenant_isolation=True,
            declared_services=data["services"],
            source_shares=[],
        )
    manifest = SimpleNamespace(
        data=old,
        migration_id=JOB,
        path=tmp_path / "manifest.json",
    )
    monkeypatch.setattr(retry, "_discover_review", lambda *_args: report)
    monkeypatch.setattr(retry, "_no_data", AsyncMock())
    monkeypatch.setattr(
        retry.TenantState,
        "get",
        AsyncMock(
            side_effect=lambda service, tenant: {
                "state": "published" if tenant == "alice" else "failed",
            },
        ),
    )
    commit = AsyncMock()
    monkeypatch.setattr(retry, "_commit_review", commit)
    monkeypatch.setattr(
        retry,
        "recover_pending_review",
        AsyncMock(return_value={"outcome": "new"}),
    )
    outcome = await retry.review_retry(None, manifest, report)
    assert {item["tenant_id"] for item in outcome["failures"]} == (
        {"bob"} if published_conflict else {"bob", "carol"}
    )
    assert all(
        item["code"] == "tenant_boundary_invalid"
        for item in outcome["failures"]
    )
    revised = commit.call_args.args[3]
    changed = commit.call_args.args[4]
    assert ("svc", "dave") in changed
    assert ("svc", "alice") not in changed
    assert retry._evidence(revised, ("svc", "alice")) == retry._evidence(
        old,
        ("svc", "alice"),
    )
    if published_conflict:
        assert retry._evidence(revised, ("svc", "bob")) == retry._evidence(
            old,
            ("svc", "bob"),
        )
        assert revised["tenants"] != old["tenants"]


@pytest.mark.parametrize("candidate_state", ["failed", "discovered"])
async def test_review_retains_failed_tenant_with_committed_data_and_keeps_other_candidate(
    tmp_path,
    monkeypatch,
    candidate_state,
):
    from copy import deepcopy

    old = {
        "services": [
            {
                "service_unit_id": "svc",
                "source_root": str(tmp_path),
                "original_root": str(tmp_path),
            },
        ],
        "declared_services": [],
        "source_shares": [],
        "tenant_isolation": True,
        "in_place": True,
        "overrides": [],
        "shares": [],
        "workspaces": [],
        "tenants": [
            {
                "service_unit_id": "svc",
                "tenant_id": tenant,
                "state": "failed",
                "blockers": [],
            }
            for tenant in ("bob", "dave")
        ],
    }
    old["tenants"][0]["state"] = "discovered"
    old["workspaces"] = [
        {
            "service_unit_id": "svc",
            "tenant_id": "bob",
            "position": "bob",
            "root": str(tmp_path / "old-b"),
            "runtime_root": str(tmp_path / "old-b"),
            "in_place_evidence": {"config": "old-hash"},
        },
    ]
    current = deepcopy(old)
    current["workspaces"][0]["in_place_evidence"] = {"config": "repaired-hash"}
    current["tenants"][0].update(
        state=candidate_state,
        blockers=(
            [{"code": "tenant_boundary_invalid"}]
            if candidate_state == "failed"
            else []
        ),
    )
    current["tenants"][1]["state"] = "discovered"
    current["blockers"] = [{"code": "tenant_boundary_invalid"}]
    candidate = deepcopy(current)
    manifest = SimpleNamespace(
        data=old,
        migration_id=JOB,
        path=tmp_path / "manifest.json",
    )

    async def existing_data(_db, _migration, keys, *_args, **_kwargs):
        if ("svc", "bob") in keys:
            raise retry._TenantReviewHasData("business data")

    no_data = AsyncMock(side_effect=existing_data)
    monkeypatch.setattr(retry, "_no_data", no_data)
    failures = await retry._retain_committed_failures(None, manifest, current)
    expected_code = (
        "tenant_boundary_invalid"
        if candidate_state == "failed"
        else "tenant_evidence_locked"
    )
    assert failures[("svc", "bob")]["code"] == expected_code
    assert set(failures[("svc", "bob")]) == {
        "service_unit_id",
        "tenant_id",
        "stage",
        "code",
        "reason",
    }
    assert (
        next(t for t in current["tenants"] if t["tenant_id"] == "bob")
        == old["tenants"][0]
    )
    assert (
        next(t for t in current["tenants"] if t["tenant_id"] == "dave")[
            "state"
        ]
        == "discovered"
    )
    assert current["blockers"] == [{"code": "tenant_boundary_invalid"}]
    assert no_data.await_count == 2
    monkeypatch.setattr(retry, "_discover_review", lambda *_args: candidate)
    monkeypatch.setattr(
        retry.TenantState,
        "get",
        AsyncMock(return_value={"state": "failed"}),
    )
    commit = AsyncMock()
    monkeypatch.setattr(retry, "_commit_review", commit)
    monkeypatch.setattr(
        retry,
        "recover_pending_review",
        AsyncMock(return_value={"outcome": "new"}),
    )
    outcome = await retry.review_retry(None, manifest, candidate)
    revised = commit.call_args.args[3]
    assert commit.call_args.args[4] == {("svc", "dave")}
    assert (
        next(t for t in revised["tenants"] if t["tenant_id"] == "bob")
        == old["tenants"][0]
    )
    assert revised["workspaces"] == old["workspaces"]
    assert outcome["failures"][0]["code"] == expected_code


async def test_review_unchanged_failed_candidate_returns_safe_failures(
    tmp_path,
    monkeypatch,
):
    from copy import deepcopy

    tenant = {
        "service_unit_id": "svc",
        "tenant_id": "bob",
        "state": "failed",
        "blockers": [
            {"code": "untrusted secret code", "detail": "private password"},
        ],
    }
    old = {
        "tenant_isolation": True,
        "services": [{"service_unit_id": "svc"}],
        "declared_services": [],
        "source_shares": [],
        "workspaces": [],
        "shares": [],
        "tenants": [tenant],
    }
    report = deepcopy(old)
    manifest = SimpleNamespace(
        data=old,
        migration_id=JOB,
        path=tmp_path / "manifest.json",
    )
    monkeypatch.setattr(retry, "_discover_review", lambda *_args: report)
    monkeypatch.setattr(
        retry.TenantState,
        "get",
        AsyncMock(return_value={"state": "failed"}),
    )
    commit = AsyncMock()
    monkeypatch.setattr(retry, "_commit_review", commit)
    outcome = await retry.review_retry(None, manifest, report)
    assert outcome["outcome"] == "unchanged"
    assert outcome["failures"] == [
        {
            "service_unit_id": "svc",
            "tenant_id": "bob",
            "stage": "retry-review",
            "code": "tenant_input_invalid",
            "reason": retry._REVIEW_REASONS["tenant_input_invalid"],
        },
    ]
    assert "private" not in json.dumps(outcome)
    assert "secret" not in json.dumps(outcome)
    commit.assert_not_awaited()


async def test_review_restored_ticket_owner_rechecks_final_boundaries(
    tmp_path,
    monkeypatch,
):
    from copy import deepcopy
    from swe.app.conversation_storage.in_place_admission import (
        tenant_write_boundaries,
    )

    names = ("alice", "bob", "carol", "dave", "eve")
    service = {
        "service_unit_id": "svc",
        "source_root": str(tmp_path),
        "original_root": str(tmp_path),
    }
    old = {
        "tenant_isolation": True,
        "in_place": True,
        "services": [service],
        "declared_services": [service],
        "source_shares": [],
        "shares": [],
        "overrides": [],
        "blockers": [],
        "ready": True,
        "status": "success",
        "tenants": [
            {
                "service_unit_id": "svc",
                "tenant_id": name,
                "state": "discovered" if name in names[:2] else "failed",
                "blockers": [],
            }
            for name in names
        ],
        "workspaces": [
            {
                "service_unit_id": "svc",
                "tenant_id": name,
                "position": name,
                "root": str(tmp_path / name),
                "runtime_root": str(tmp_path / name),
            }
            for name in names
        ],
    }
    candidate = deepcopy(old)
    roots = {
        "bob": tmp_path / "new-b",
        "carol": tmp_path / "dave" / "child",
        "dave": tmp_path / "bob" / "child",
        "eve": tmp_path / "new-e",
    }
    for workspace in candidate["workspaces"]:
        if workspace["tenant_id"] in roots:
            root = str(roots[workspace["tenant_id"]])
            workspace.update(root=root, runtime_root=root)
    for tenant in candidate["tenants"]:
        tenant["state"] = "discovered"
    tenant_write_boundaries(candidate)
    manifest = SimpleNamespace(
        data=old,
        migration_id=JOB,
        path=tmp_path / "manifest.json",
    )

    async def no_data(_db, _migration, keys, *_args, **_kwargs):
        if ("svc", "bob") in keys:
            raise retry._TenantReviewHasData("ticket")

    monkeypatch.setattr(retry, "_no_data", no_data)
    monkeypatch.setattr(retry, "_discover_review", lambda *_args: candidate)
    monkeypatch.setattr(
        retry.TenantState,
        "get",
        AsyncMock(
            side_effect=lambda _service, tenant: {
                "state": "published" if tenant == "alice" else "failed",
            },
        ),
    )
    commit = AsyncMock()
    monkeypatch.setattr(retry, "_commit_review", commit)
    monkeypatch.setattr(
        retry,
        "recover_pending_review",
        AsyncMock(
            return_value={"outcome": "new"},
        ),
    )
    outcome = await retry.review_retry(None, manifest, candidate)
    revised, changed = commit.call_args.args[3:5]
    assert ("svc", "bob") not in changed
    assert ("svc", "alice") not in changed
    assert ("svc", "eve") in changed
    for name in names[:-1]:
        assert retry._evidence(revised, ("svc", name)) == retry._evidence(
            old,
            ("svc", name),
        )
    assert {item["tenant_id"] for item in outcome["failures"]} == {
        "bob",
        "carol",
        "dave",
    }
    assert {t["tenant_id"]: t["state"] for t in revised["tenants"]} == {
        "alice": "discovered",
        "bob": "discovered",
        "carol": "failed",
        "dave": "failed",
        "eve": "discovered",
    }
    tenant_write_boundaries(revised)


def test_review_validator_routes_only_candidates_into_shared_budget_mapper():
    from unittest.mock import Mock

    def selected(tenant):
        return {
            "workspaces": [
                {
                    "service_unit_id": "svc",
                    "tenant_id": tenant,
                    "position": tenant,
                    "counts": {"sessions": 2, "chats": 1},
                },
            ],
            "shares": [],
            "services": [{"service_unit_id": "svc"}],
        }

    old = selected("published")
    manifest = SimpleNamespace(data=old)
    validator = Mock(
        side_effect=AssertionError("synchronous semantic fallback used"),
    )
    candidate = selected("retry")
    marker = {"blockers": [], "workspaces": [{"sessions": (), "chats": ()}]}
    validator.map_tenants = Mock(return_value=iter([marker]))
    validator.map_input_digests = Mock()
    wrapped = retry._review_validator(
        manifest,
        {("svc", "published")},
        {("svc", "retained")},
        validator,
    )
    results = list(
        wrapped.map_tenants(
            [selected("published"), selected("retained"), candidate],
        ),
    )
    assert len(results[0]["workspaces"][0]["sessions"]) == 2
    assert results[1]["workspaces"][0]["sessions"] == ()
    assert results[2] is marker
    validator.map_tenants.assert_called_once_with([candidate])
    assert wrapped.map_input_digests is validator.map_input_digests
    validator.assert_not_called()


async def test_review_retry_passes_resource_validator_to_thread(
    tmp_path,
    monkeypatch,
):
    from unittest.mock import Mock

    data = {
        "tenant_isolation": True,
        "tenants": [],
        "services": [],
        "declared_services": [],
        "source_shares": [],
        "workspaces": [],
        "shares": [],
    }
    manifest = SimpleNamespace(
        data=data,
        path=tmp_path / "manifest.json",
        migration_id=JOB,
    )
    discover = Mock(return_value=data)
    validator = object()
    monkeypatch.setattr(retry, "_discover_review", discover)
    result = await retry.review_retry(
        None,
        manifest,
        data,
        eligible=set(),
        semantic_validator=validator,
    )
    assert result["outcome"] == "unchanged"
    discover.assert_called_once_with(manifest, data, set(), set(), validator)
