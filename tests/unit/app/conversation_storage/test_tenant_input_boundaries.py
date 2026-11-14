# -*- coding: utf-8 -*-
"""Tenant input failures remain attributable across preparation and import."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from swe.app.conversation_storage.migration import discovery
from swe.app.conversation_storage.migration.importer import (
    ConversationImporter,
)
from swe.app.conversation_storage.migration.manifest import SourceBoundary
from swe.config.context import encode_scope_id


def setup_source(tmp_path, *, broken=False):
    root, nas = tmp_path / "source", tmp_path / "nas"
    root.mkdir()
    nas.mkdir()
    paths = {}
    for tenant in ("alice", "bob"):
        home = root / encode_scope_id(tenant, "SRC")
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
        paths[tenant] = (config, workspace)
    if broken:
        paths["bob"][0].write_text("{broken")
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
        in_place=True,
    )
    return report, paths


def freeze(tmp_path, report):
    return discovery.freeze_discovery(
        report,
        tmp_path / "manifest.json",
        SourceBoundary(
            "snapshot",
            "2026-11-15T00:00:00Z",
            "old@sha256:" + "a" * 64,
            ("stop", "readonly"),
        ),
        "business",
    )


@pytest.mark.parametrize("repair", [False, True])
def test_failed_tenant_change_does_not_block_freeze(tmp_path, repair):
    report, paths = setup_source(tmp_path, broken=True)
    config = paths["bob"][0]
    config.chmod(0o644)
    config.write_text('{"agents":{"profiles":{}}}' if repair else "{different")
    config.chmod(0o444)
    manifest = freeze(tmp_path, report)
    states = {t["tenant_id"]: t["state"] for t in manifest.data["tenants"]}
    assert states == {"alice": "discovered", "bob": "failed"}


def test_healthy_tenant_content_change_is_isolated_during_freeze(tmp_path):
    report, paths = setup_source(tmp_path)
    chats = paths["bob"][1] / "chats.json"
    chats.chmod(0o644)
    chats.write_text('{"version": 1, "chats": []}')
    chats.chmod(0o444)
    manifest = freeze(tmp_path, report)
    states = {t["tenant_id"]: t["state"] for t in manifest.data["tenants"]}
    assert states == {"alice": "discovered", "bob": "failed"}


def test_freeze_rejects_new_unknown_workspace(tmp_path):
    report, paths = setup_source(tmp_path)
    root = Path(report["services"][0]["source_root"])
    orphan = root / "unknown"
    orphan.mkdir()
    (orphan / "chats.json").write_text('{"version":1,"chats":[]}')
    with pytest.raises(ValueError, match="coverage|ownership|identity"):
        freeze(tmp_path, report)


def test_freeze_rejects_changed_mapping_with_new_unowned_workspace(tmp_path):
    report, paths = setup_source(tmp_path)
    config = paths["bob"][0]
    config.chmod(0o644)
    config.write_text(
        json.dumps(
            {
                "agents": {
                    "profiles": {
                        "agent": {
                            "id": "agent",
                            "workspace_dir": str(paths["alice"][1]),
                        },
                    },
                },
            },
        ),
    )
    config.chmod(0o444)
    with pytest.raises(ValueError, match="coverage or ownership"):
        freeze(tmp_path, report)


def test_unsettled_turn_has_explicit_tenant_error():
    from swe.app.conversation_storage.migration.tenant_errors import (
        TenantInputError,
    )

    state = {"turn_states": {"t": {"status": "running"}}}
    with pytest.raises(TenantInputError, match="unsettled"):
        ConversationImporter._validate_runtime_sources(
            object(),
            {
                "workspaces": [
                    {
                        "sessions": [
                            {"legacy": {"state": state}},
                        ],
                        "chats": [],
                    },
                ],
            },
        )


def test_freshness_has_explicit_source_changed_error(tmp_path):
    from swe.app.conversation_storage.migration.tenant_errors import (
        SourceChanged,
    )

    path = tmp_path / "changed"
    path.write_text("changed")
    recorded = []
    importer = SimpleNamespace(
        manifest=SimpleNamespace(
            data={"tenant_sync_started_at_ns": {"svc\x00bob": 1}},
        ),
        _record_source_change=recorded.append,
    )
    with pytest.raises(SourceChanged):
        ConversationImporter._assert_source_fresh(
            importer,
            {
                "workspaces": [
                    {
                        "scope": ["svc", "bob"],
                        "position": "b",
                        "source_paths": [str(path)],
                    },
                ],
                "shares": [],
            },
        )
    assert recorded[0]["scope"] == ["svc", "bob"]


async def test_automatic_review_only_accepts_prior_failed_tenant(
    tmp_path,
    monkeypatch,
):
    from unittest.mock import AsyncMock
    from swe.app.conversation_storage.migration import tenant_retry as retry

    report, paths = setup_source(tmp_path, broken=True)
    manifest = SimpleNamespace(
        data={
            **report,
            "migration_id": "00000000-0000-4000-8000-000000000001",
        },
        migration_id="00000000-0000-4000-8000-000000000001",
        path=tmp_path / "manifest.json",
    )
    a_config, _ = paths["alice"]
    a_config.chmod(0o644)
    a_config.write_text(
        "must not parse healthy tenant during automatic review",
    )
    b_config, b_workspace = paths["bob"]
    b_config.chmod(0o644)
    b_config.write_text(
        json.dumps(
            {
                "agents": {
                    "profiles": {
                        "agent": {
                            "id": "agent",
                            "workspace_dir": str(b_workspace),
                        },
                    },
                },
            },
        ),
    )
    b_config.chmod(0o444)
    monkeypatch.setattr(
        retry.TenantState,
        "get",
        AsyncMock(
            side_effect=lambda _service, tenant: {
                "state": "failed" if tenant == "bob" else "discovered",
            },
        ),
    )
    monkeypatch.setattr(retry, "_no_data", AsyncMock())
    commit = AsyncMock()
    monkeypatch.setattr(retry, "_commit_review", commit)
    monkeypatch.setattr(
        retry,
        "recover_pending_review",
        AsyncMock(return_value={"outcome": "new"}),
    )
    result = await retry.review_retry(
        None,
        manifest,
        report,
        eligible={("svc", "bob")},
    )
    assert result["failures"] == []
    revised, changed = commit.call_args.args[3:5]
    assert changed == {("svc", "bob")}
    old_a = next(t for t in report["tenants"] if t["tenant_id"] == "alice")
    assert (
        next(t for t in revised["tenants"] if t["tenant_id"] == "alice")
        == old_a
    )


def test_digest_detects_same_count_change_and_legacy_is_compatible(tmp_path):
    from swe.app.conversation_storage.migration.tenant_inputs import (
        verify_input_digest,
    )
    from swe.app.conversation_storage.migration.tenant_errors import (
        SourceChanged,
    )

    report, paths = setup_source(tmp_path)
    chats = paths["bob"][1] / "chats.json"
    chats.chmod(0o644)
    chats.write_text('{"version": 1, "chats": []}')
    chats.chmod(0o444)
    with pytest.raises(SourceChanged, match="after preparation"):
        verify_input_digest(report, ("svc", "bob"))
    verify_input_digest(report, ("svc", "alice"))
    for tenant in report["tenants"]:
        tenant.pop("input_digest", None)
    verify_input_digest(report, ("svc", "bob"))


async def test_direct_parallel_import_borrows_io_without_closing(monkeypatch):
    from unittest.mock import AsyncMock, Mock
    from swe.app.conversation_storage.migration.direct_import import (
        DirectImporter,
    )
    from swe.app.conversation_storage.migration import importer as module
    from swe.app.conversation_storage.migration import (
        parallel_import,
        parallel_shares,
    )
    from swe.app.conversation_storage.migration.parallel import MigrationIO

    borrowed = SimpleNamespace(__aexit__=AsyncMock())
    item = object.__new__(DirectImporter)
    item.manifest = SimpleNamespace(
        data={"tenant_sync_started_at_ns": {}, "batches": {}},
        _persist=Mock(),
        migration_id="job",
    )
    item.journal = SimpleNamespace(
        prepare=AsyncMock(),
        mark_state=AsyncMock(),
        capture_retentions=AsyncMock(),
        persist_updates=True,
    )
    item.stores = {"svc": SimpleNamespace(validate_target=AsyncMock())}
    item._validate_source_binding = Mock()
    item._assert_source_fresh = Mock()
    item._validate_runtime_sources = Mock()
    monkeypatch.setattr(module, "validate_inventory", Mock())
    runner = SimpleNamespace(run=AsyncMock(return_value={}))
    monkeypatch.setattr(
        parallel_import,
        "ParallelImportPrototype",
        lambda *_a, **_k: runner,
    )
    shares = AsyncMock()
    monkeypatch.setattr(parallel_shares, "run_parallel_shares", shares)
    monkeypatch.setattr(
        MigrationIO,
        "__aenter__",
        AsyncMock(side_effect=AssertionError("private pool opened")),
    )
    await item.run_parallel(
        {"workspaces": [], "shares": [], "files": []},
        io=borrowed,
    )
    assert runner.run.call_args.kwargs["io"] is borrowed
    assert shares.call_args.kwargs["io"] is borrowed
    borrowed.__aexit__.assert_not_awaited()


@pytest.mark.parametrize("in_place", [False, True])
async def test_review_reports_retained_failed_evidence_without_rewriting(
    tmp_path,
    monkeypatch,
    in_place,
):
    from unittest.mock import AsyncMock
    from swe.app.conversation_storage.migration import tenant_retry as retry

    report, paths = setup_source(tmp_path)
    report["in_place"] = in_place
    if not in_place:
        from copy import deepcopy

        candidate = deepcopy(report)
        bob = next(t for t in candidate["tenants"] if t["tenant_id"] == "bob")
        bob["input_digest"] = "changed-candidate"
        monkeypatch.setattr(
            retry,
            "_discover_review",
            lambda *_args: candidate,
        )
    tenant = next(t for t in report["tenants"] if t["tenant_id"] == "bob")
    tenant.update(
        state="failed",
        blockers=[{"code": "source_changed_after_discovery"}],
    )
    manifest = SimpleNamespace(
        data=report,
        migration_id="00000000-0000-4000-8000-000000000001",
        path=tmp_path / "manifest.json",
    )
    monkeypatch.setattr(
        retry.TenantState,
        "get",
        AsyncMock(
            return_value={"state": "failed"},
        ),
    )
    monkeypatch.setattr(
        retry,
        "_no_data",
        AsyncMock(
            side_effect=retry._TenantReviewHasData("ticket"),
        ),
    )
    commit = AsyncMock()
    monkeypatch.setattr(retry, "_commit_review", commit)
    before = json.dumps(report, sort_keys=True)
    result = await retry.review_retry(
        None,
        manifest,
        report,
        eligible={("svc", "bob")},
    )
    assert result["retained_keys"] == [["svc", "bob"]]
    assert json.dumps(report, sort_keys=True) == before
    assert result["outcome"] == "unchanged"
    commit.assert_not_awaited()
