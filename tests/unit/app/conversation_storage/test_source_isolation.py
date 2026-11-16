# -*- coding: utf-8 -*-
"""One source fails while another source of the same tenant can publish."""

import json
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from swe.app.conversation_storage.migration import discovery
from swe.app.conversation_storage.migration.source_state import SourceState
from swe.app.conversation_storage.migration.manifest import SourceBoundary
from swe.app.conversation_storage.migration.v3_manifest import V3Manifest
from swe.app.conversation_storage.migration.journal import MigrationJournal
from swe.app.conversation_storage.tenant_admission import (
    TenantAdmission,
    TenantNotPublished,
)
from swe.config.context import encode_scope_id
from swe.cli import conversation_storage_tenants as cli

JOB = "00000000-0000-4000-8000-000000000001"


def sources(tmp_path):
    root, nas = tmp_path / "source", tmp_path / "nas"
    root.mkdir()
    nas.mkdir()
    paths = {}
    for source in ("A", "B", "C"):
        home = root / encode_scope_id("alice", source)
        workspace = home / "workspaces" / "agent"
        workspace.mkdir(parents=True)
        config = home / "config.json"
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
        (workspace / "agent.json").write_text('{"id":"agent"}')
        (workspace / "chats.json").write_text('{"version":1,"chats":[]}')
        paths[source] = (config, workspace)
    paths["B"][0].write_text('{"agents":{"profiles":42}}')
    for path in root.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    service = {"service_unit_id": "svc", "nas_root": str(nas)}
    service.update(
        {
            key: str(root)
            for key in (
                "source_root",
                "config_root",
                "snapshot_root",
                "original_root",
            )
        },
    )
    report = discovery.discover_services(
        [service],
        tenant_isolation=True,
        source_isolation=True,
        in_place=True,
    )
    return report, paths


def test_discovery_and_freeze_isolate_same_tenant_sources(tmp_path):
    report, paths = sources(tmp_path)
    assert {t["source_id"]: t["state"] for t in report["tenants"]} == {
        "A": "discovered",
        "B": "failed",
        "C": "discovered",
    }
    config, _ = paths["B"]
    config.chmod(0o644)
    config.write_text('{"agents":{"profiles":43}}')
    config.chmod(0o444)
    manifest = discovery.freeze_discovery(
        report,
        tmp_path / "manifest.json",
        SourceBoundary(
            "batch",
            "2026-11-16T00:00:00Z",
            "old@sha256:" + "a" * 64,
            ["stop"],
        ),
        "business",
    )
    assert V3Manifest.load(manifest.path).data["source_isolation"] is True
    assert (
        len(
            cli.TenantManifest(manifest, manifest.data["tenants"][0]).data[
                "workspaces"
            ],
        )
        == 1
    )
    assert {t["source_id"]: t["state"] for t in manifest.data["tenants"]} == {
        "A": "discovered",
        "B": "failed",
        "C": "discovered",
    }


class Database:
    def __init__(self):
        self.rows = {}

    @asynccontextmanager
    async def transaction(self):
        before = deepcopy(self.rows)
        try:
            yield self
        except BaseException:
            self.rows = before
            raise

    async def fetch_one(self, query, params):
        return self.rows.get(params)

    async def execute(self, query, params):
        if query.startswith("INSERT"):
            self.rows[params[:4]] = {
                "state": "discovered",
                "evidence_text": params[4],
                "verification_text": "{}",
            }
        elif "failure_text=%s" in query:
            self.rows[params[1:5]]["state"] = "failed"
        else:
            row = self.rows[params[4:8]]
            assert row["state"] == params[8]
            row["state"] = params[0]
            if params[1] is not None:
                row["verification_text"] = params[1]
        return 1


async def test_source_publication_and_failure_are_independent():
    db = Database()
    states = SourceState(db, JOB)
    evidence = {
        "service": {"service_unit_id": "svc", "nas_root": "/nas"},
        "workspaces": [],
        "shares": [],
    }
    await states.register(
        [
            {
                "service_unit_id": "svc",
                "tenant_id": "alice",
                "source_id": s,
                "evidence": evidence,
            }
            for s in ("A", "B")
        ],
    )
    await states.fail("svc", "alice", "B", "inventory", "invalid", "bad")
    for state in ("importing", "imported", "verified"):
        await states.transition("svc", "alice", "A", state)
    proof = {
        "version": 1,
        "migration_id": JOB,
        "services": {"svc": {"nas_root": "/nas", "workspaces": []}},
    }
    await states.publish("svc", "alice", "A", proof)
    assert (await states.get("svc", "alice", "A"))["state"] == "published"
    assert (await states.get("svc", "alice", "B"))["state"] == "failed"


async def test_admission_checks_exact_source_and_proof():
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
                "source_binding_text": '{"tenant_isolation":true,"source_isolation":true}',
            }
        if "@@server_uuid" in query:
            return {"server_uuid": "server", "schema_name": "test"}
        assert "migration_sources" in query and "source_key=%s" in query
        source = params[-1].decode()
        return {
            "state": "published" if source == "A" else "failed",
            "verification_text": json.dumps(
                {
                    "version": 1,
                    "migration_id": JOB,
                    "services": {
                        "svc": {
                            "nas_root": "/nas",
                            "workspaces": [
                                {
                                    "root": "/workspace",
                                    "scope": ["svc", "alice", source, "agent"],
                                },
                            ],
                        },
                    },
                },
            ),
        }

    admission = TenantAdmission(
        SimpleNamespace(fetch_one=AsyncMock(side_effect=fetch)),
        {
            "version": 3,
            "migration_id": JOB,
            "service_unit_id": "svc",
            "nas_root": "/nas",
        },
    )
    assert (await admission.require("alice", "A"))[0]["scope"][2] == "A"
    with pytest.raises(TenantNotPublished):
        await admission.require("alice", "B")
    with pytest.raises(TenantNotPublished):
        await admission.require("alice")


async def test_journal_ownership_filters_source():
    db = SimpleNamespace(
        fetch_one=AsyncMock(return_value=None),
        fetch_all=AsyncMock(return_value=[]),
    )
    manifest = SimpleNamespace(
        migration_id=JOB,
        data={
            "version": 3,
            "tenant_isolation": True,
            "source_isolation": True,
        },
    )
    journal = MigrationJournal(db, manifest)
    journal.active_tenant = ("svc", "alice", "B")
    await journal.validate_ownership()
    for call in db.fetch_one.call_args_list:
        if len(call.args) > 1:
            assert "source_key=%s" in call.args[0]
            assert call.args[1][-3:] == (b"svc", b"alice", b"B")


async def test_orchestrator_skips_bad_source_and_published_sibling(
    monkeypatch,
    tmp_path,
):
    from tests.unit.app.conversation_storage.test_tenant_orchestration import (
        orchestration,
        run,
    )

    fixture = orchestration.__wrapped__(monkeypatch, tmp_path)
    fixture.manifest.data["source_isolation"] = True
    fixture.manifest.data["tenant_isolation"] = True
    for record in fixture.manifest.data["tenants"]:
        record["source_id"] = record["tenant_id"]
        record["tenant_id"] = "alice"
    for record in fixture.manifest.data["workspaces"]:
        record["source_id"] = record["tenant_id"]
        record["tenant_id"] = "alice"
    fixture.states.get.side_effect = (
        lambda service, tenant, source: fixture.rows[source]
    )
    monkeypatch.setattr(cli, "_states", lambda *_: fixture.states)
    visited = []

    async def one(operation, view, *_args):
        visited.append(view.key)
        assert len(view.data["workspaces"]) == 1
        if view.key[2] == "b":
            raise cli.TenantFailure("bad source")

    monkeypatch.setattr(cli, "_one_tenant", one)
    result = await run(fixture)
    assert visited == [("svc", "alice", "b"), ("svc", "alice", "c")]
    assert result["counter_unit"] == "sources"
    assert (result["completed"], result["failed"], result["published"]) == (
        1,
        1,
        1,
    )
    assert fixture.states.fail.call_args.args[:3] == ("svc", "alice", "b")
    assert fixture.writer.call_args.args[2][0]["source_id"] == "b"


async def test_repaired_source_review_never_reads_published_sibling(
    monkeypatch,
    tmp_path,
):
    from pathlib import Path
    from swe.app.conversation_storage.migration import tenant_retry as retry

    report, paths = sources(tmp_path)
    data = {
        **report,
        "migration_id": JOB,
        "target": {
            "schema": "test",
            "migration_id": JOB,
            "nas_roots": {"svc": report["services"][0]["nas_root"]},
        },
        "assignments": {},
        "batches": {},
    }
    good = (
        paths["A"][0]
        .read_text()
        .replace(str(paths["A"][1]), str(paths["B"][1]))
    )
    paths["B"][0].chmod(0o644)
    paths["B"][0].write_text(good)
    paths["B"][0].chmod(0o444)
    paths["A"][0].chmod(0o644)
    paths["A"][0].write_text("live source config")
    original = Path.read_bytes

    def read(path):
        if encode_scope_id("alice", "A") in path.parts:
            pytest.fail("published source read")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    states = SimpleNamespace(
        get=AsyncMock(
            side_effect=lambda service, tenant, source, **kw: {
                "state": "published" if source == "A" else "failed",
            },
        ),
    )
    monkeypatch.setattr(retry, "_states", lambda *_: states)
    monkeypatch.setattr(retry, "_no_data", AsyncMock())
    commit = AsyncMock()
    monkeypatch.setattr(retry, "_commit_review", commit)
    monkeypatch.setattr(
        retry,
        "recover_pending_review",
        AsyncMock(return_value={"outcome": "new"}),
    )
    manifest = SimpleNamespace(
        data=data,
        path=tmp_path / "manifest.json",
        migration_id=JOB,
    )
    await retry.review_retry(None, manifest, report)
    revised = commit.call_args.args[3]
    assert (
        next(t for t in revised["tenants"] if t["source_id"] == "B")["state"]
        == "discovered"
    )
    assert next(
        t for t in revised["tenants"] if t["source_id"] == "A"
    ) == next(t for t in data["tenants"] if t["source_id"] == "A")


def test_share_source_considers_failed_source_config(tmp_path):
    from swe.app.conversation_storage.migration.source_ownership import (
        share_source,
    )

    report, _ = sources(tmp_path)
    with pytest.raises(ValueError, match="ambiguous"):
        share_source(
            report,
            report["services"][0],
            {"tenant_id": "alice", "token": "token", "chat_id": "deleted"},
        )


async def test_source_proof_cannot_publish_sibling():
    db = Database()
    states = SourceState(db, JOB)
    await states.register(
        [{"service_unit_id": "svc", "tenant_id": "alice", "source_id": "A"}],
    )
    proof = {
        "version": 1,
        "migration_id": JOB,
        "services": {
            "svc": {
                "nas_root": "/nas",
                "workspaces": [
                    {"root": "/w", "scope": ["svc", "alice", "B", "agent"]},
                ],
            },
        },
    }
    with pytest.raises(ValueError, match="scope"):
        await states.publish("svc", "alice", "A", proof)


async def test_share_comparison_allows_live_sibling_but_rejects_unknown_source(
    monkeypatch,
):
    from tests.unit.app.conversation_storage.test_tenant_orchestration import (
        share,
    )

    own = share("frozen", "svc")
    parent = SimpleNamespace(
        data={
            "source_isolation": True,
            "source_shares": [own],
            "shares": [own],
        },
    )
    view = SimpleNamespace(
        key=("svc", "same-account", "B"),
        migration_id=JOB,
        parent=parent,
        data={"source_isolation": True, "shares": [own]},
    )
    db = SimpleNamespace(
        fetch_all=AsyncMock(
            return_value=[
                {**own, "service_unit_key": None},
                {**share("new", "svc"), "service_unit_key": b"svc"},
            ],
        ),
        fetch_one=AsyncMock(
            side_effect=[
                {"source_key": b"A", "scope_kind": "workspace"},
                {"state": "published"},
            ],
        ),
    )
    await cli._compare_shares(db, view)
    db.fetch_one.side_effect = [
        {"source_key": b"B", "scope_kind": "workspace"},
        {"state": "failed"},
    ]
    with pytest.raises(cli.TenantFailure, match="unregistered"):
        await cli._compare_shares(db, view)
