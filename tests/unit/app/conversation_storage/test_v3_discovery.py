# -*- coding: utf-8 -*-
import json
from pathlib import Path

import pytest

from swe.app.conversation_storage.migration.manifest import SourceBoundary


def fixture_service(tmp_path):
    source = tmp_path / "source"
    source.mkdir(parents=True)
    tenant = source / "default_SRC"
    workspace = tenant / "workspaces" / "agent"
    workspace.mkdir(parents=True)
    nas = tmp_path / "nas"
    (nas / "default_SRC" / "workspaces" / "agent").mkdir(parents=True)
    (tenant / "config.json").write_text(
        json.dumps(
            {
                "agents": {
                    "profiles": {
                        "agent": {
                            "id": "agent",
                            "workspace_dir": str(
                                nas / "default_SRC" / "workspaces" / "agent",
                            ),
                            "enabled": False,
                        },
                    },
                },
            },
        ),
    )
    (workspace / "agent.json").write_text('{"id": "agent"}')
    (workspace / "chats.json").write_text('{"version": 1, "chats": []}')
    for path in source.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    source.chmod(0o555)
    return {
        "service_unit_id": "SERVICE",
        "source_root": str(source),
        "config_root": str(source),
        "original_root": str(nas),
        "nas_root": str(nas),
    }


def test_discovers_disabled_profile_and_rebases_absolute_path(tmp_path):
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
    )

    service = fixture_service(tmp_path)
    report = discover_services([service])
    assert report["ready"], report["blockers"]
    assert len(report["workspaces"]) == 1
    item = report["workspaces"][0]
    assert (item["tenant_id"], item["source_id"], item["agent_id"]) == (
        "default",
        "SRC",
        "agent",
    )
    assert item["root"].startswith(service["source_root"])
    assert item["runtime_root"].startswith(service["nas_root"])


def test_new_discovery_avoids_fingerprints_and_keeps_service_authority(
    tmp_path,
    monkeypatch,
):
    from swe.app.conversation_storage.migration import discovery
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
        freeze_discovery,
    )
    from swe.app.conversation_storage.migration.inventory_v3 import (
        inventory_v3,
    )

    service = fixture_service(tmp_path)
    report = discover_services([service])
    fingerprint_calls = []
    original_fingerprints = discovery.fingerprints

    def count_fingerprints(services):
        fingerprint_calls.append(True)
        return original_fingerprints(services)

    monkeypatch.setattr(discovery, "fingerprints", count_fingerprints)
    boundary = SourceBoundary(
        "snapshot",
        "2026-11-02T00:00:00Z",
        "old@sha256:" + "a" * 64,
        ("stop", "readonly"),
    )
    manifest = freeze_discovery(
        report,
        tmp_path / "manifest.json",
        boundary,
        "business",
    )
    assert fingerprint_calls == []
    assert manifest.data["version"] == 3
    assert inventory_v3(manifest)["ready"]
    assert "tenant_sync_started_at_ns" not in manifest.data
    assert inventory_v3(manifest, begin_sync=True)["ready"]
    registry = Path(report["workspaces"][0]["root"]) / "chats.json"
    cutoff = manifest.data["tenant_sync_started_at_ns"]["SERVICE\x00default"]
    registry.chmod(0o644)
    registry.write_text("{changed")
    import os

    os.utime(registry, ns=(cutoff + 1, cutoff + 1))
    registry.chmod(0o444)
    result = inventory_v3(manifest)
    assert not result["ready"]
    blocker = result["blockers"][0]
    assert blocker["code"] == "source_modified_after_sync_started"
    assert blocker["scope"] == ["SERVICE", "default"]
    assert blocker["path"] == str(registry)
    assert blocker["mtime_ns"] > blocker["cutoff_ns"]
    assert manifest.data["source_change_blockers"] == [blocker]


def test_unregistered_workspace_is_blocker(tmp_path):
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
    )

    service = fixture_service(tmp_path)
    root = Path(service["source_root"])
    root.chmod(0o755)
    extra = root / "orphan"
    extra.mkdir()
    (extra / "chats.json").write_text('{"chats": []}')
    (extra / "chats.json").chmod(0o444)
    extra.chmod(0o555)
    root.chmod(0o555)
    report = discover_services([service])
    assert not report["ready"]
    assert any(
        item["code"] == "unregistered_workspace" for item in report["blockers"]
    )


def test_service_without_workspaces_is_retained_for_share_only_job(tmp_path):
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
    )

    root = tmp_path / "frozen"
    root.mkdir()
    nas = tmp_path / "nas"
    nas.mkdir()
    root.chmod(0o555)
    service = {
        "service_unit_id": "SERVICE",
        "source_root": str(root),
        "config_root": str(root),
        "original_root": str(nas),
        "nas_root": str(nas),
    }
    report = discover_services([service])
    assert report["ready"], report["blockers"]
    assert report["services"][0]["service_unit_id"] == "SERVICE"
    assert report["workspaces"] == []


def test_rejects_another_services_source_overlapping_target_nas(tmp_path):
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
    )

    first = fixture_service(tmp_path / "one")
    second_root = tmp_path / "two" / "source"
    second_root.mkdir(parents=True)
    first["nas_root"] = str(second_root)
    # Target NAS is a parent of another service's frozen source.
    second_nas = tmp_path / "two" / "nas"
    second_nas.mkdir()
    second = {
        "service_unit_id": "SERVICE2",
        "source_root": str(second_root),
        "config_root": str(second_root),
        "original_root": str(second_nas),
        "nas_root": str(second_nas),
    }
    report = discover_services([first, second])
    assert any(
        item["code"] == "service_invalid" and "overlap" in item["detail"]
        for item in report["blockers"]
    )


def test_source_change_blocker_survives_manifest_reload(tmp_path):
    from pathlib import Path
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
        freeze_discovery,
    )

    service = fixture_service(tmp_path)
    report = discover_services([service])
    boundary = SourceBoundary(
        "snapshot",
        "2026-11-02T00:00:00Z",
        "old@sha256:" + "a" * 64,
        ("stop", "readonly"),
    )
    manifest_path = tmp_path / "manifest.json"
    manifest = freeze_discovery(report, manifest_path, boundary, "business")
    from swe.app.conversation_storage.migration.freshness import tenant_key

    cutoff = manifest.begin_tenant_sync("SERVICE", "default")
    blocker = {
        "code": "source_modified_after_sync_started",
        "position": report["workspaces"][0]["position"],
        "scope": ["SERVICE", "default"],
        "path": str(Path(service["source_root"])),
        "mtime_ns": cutoff + 1,
        "cutoff_ns": cutoff,
    }
    manifest.record_source_change(blocker)
    from swe.app.conversation_storage.migration.v3_manifest import V3Manifest

    loaded = V3Manifest.load(manifest_path)
    assert (
        loaded.data["tenant_sync_started_at_ns"][
            tenant_key("SERVICE", "default")
        ]
        == cutoff
    )
    assert loaded.data["source_change_blockers"] == [blocker]
    loaded.data["assignments"]["publication"] = {
        "legacy-ticket": {
            "target_id": 1,
            "operation_key": "a" * 64,
            "relative_path": None,
        },
    }
    loaded._persist()
    resumed = V3Manifest.load(manifest_path)
    assert (
        resumed.data["assignments"]["publication"]["legacy-ticket"][
            "relative_path"
        ]
        is None
    )


def test_deferred_journal_mirror_preserves_source_change_error(
    tmp_path,
    monkeypatch,
):
    from types import SimpleNamespace
    from swe.app.conversation_storage.migration import freshness
    from swe.app.conversation_storage.migration.direct_import import (
        DirectImporter,
    )
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
        freeze_discovery,
    )
    from swe.app.conversation_storage.migration.v3_manifest import V3Manifest

    service = fixture_service(tmp_path)
    discovered = discover_services([service])
    frozen = freeze_discovery(
        discovered,
        tmp_path / "manifest.json",
        SourceBoundary(
            "snapshot",
            "2026-11-02T00:00:00Z",
            "old@sha256:" + "a" * 64,
            ("stop", "readonly"),
        ),
        "business",
    )
    cutoff = frozen.begin_tenant_sync("SERVICE", "default")
    # Simulate a SQL-confirmed ticket whose disk mirror is deferred.
    frozen.data["assignments"]["session"] = {
        "new-session": {
            "target_id": 84,
            "operation_key": "a" * 64,
            "relative_path": None,
        },
    }
    importer = object.__new__(DirectImporter)
    importer.manifest = frozen
    importer.journal = SimpleNamespace(persist_updates=False)
    monkeypatch.setattr(
        freshness,
        "changed_source",
        lambda paths, timestamp, **_options: (paths[0], timestamp + 1),
    )
    workspace = discovered["workspaces"][0]
    report = {
        "workspaces": [
            {
                "scope": ["SERVICE", "default", "SRC", "agent"],
                "position": workspace["position"],
                "source_paths": [service["source_root"]],
            },
        ],
        "shares": [],
    }
    with pytest.raises(ValueError, match="tenant source changed"):
        importer._assert_source_fresh(report)
    reloaded = V3Manifest.load(frozen.path)
    assert reloaded.data["assignments"] == frozen.data["assignments"]
    blocker = reloaded.data["source_change_blockers"][0]
    assert blocker["cutoff_ns"] == cutoff
    assert blocker["position"] == workspace["position"]


def test_freeze_rejects_modified_discovery_identity(tmp_path):
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
        freeze_discovery,
    )

    report = discover_services([fixture_service(tmp_path)])
    report["workspaces"][0]["tenant_id"] = "wrong"
    boundary = SourceBoundary(
        "snapshot",
        "2026-11-02T00:00:00Z",
        "old@sha256:" + "a" * 64,
        ("stop", "readonly"),
    )
    with pytest.raises(ValueError, match="discovery"):
        freeze_discovery(
            report,
            tmp_path / "manifest.json",
            boundary,
            "business",
        )


def test_bound_override_resolves_only_unregistered_candidate(tmp_path):
    from pathlib import Path
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
        source_key,
    )

    service = fixture_service(tmp_path)
    root = Path(service["source_root"])
    root.chmod(0o755)
    extra = root / "orphan"
    extra.mkdir()
    (extra / "agent.json").write_text('{"id": "retired"}')
    (extra / "chats.json").write_text('{"version": 1, "chats": []}')
    for path in extra.iterdir():
        path.chmod(0o444)
    extra.chmod(0o555)
    root.chmod(0o555)
    override = {
        "position": source_key("workspace", "SERVICE", "orphan"),
        "discovery_version": 1,
        "evidence_refs": ["historical-registration"],
        "reason": "retired profile removed",
        "tenant_id": "default",
        "source_id": "SRC",
        "agent_id": "retired",
    }
    report = discover_services([service], overrides=[override])
    assert report["ready"], report["blockers"]
    assert len(report["workspaces"]) == 2


def test_empty_workspace_without_registry_is_empty_inventory(tmp_path):
    from pathlib import Path
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
        freeze_discovery,
    )
    from swe.app.conversation_storage.migration.inventory_v3 import (
        inventory_v3,
    )

    service = fixture_service(tmp_path)
    workspace = (
        Path(service["source_root"]) / "default_SRC" / "workspaces" / "agent"
    )
    workspace.chmod(0o755)
    (workspace / "chats.json").unlink()
    workspace.chmod(0o555)
    boundary = SourceBoundary(
        "snapshot",
        "2026-11-02T00:00:00Z",
        "old@sha256:" + "a" * 64,
        ("stop", "readonly"),
    )
    report = discover_services([service])
    manifest = freeze_discovery(
        report,
        tmp_path / "manifest.json",
        boundary,
        "business",
    )
    result = inventory_v3(manifest)
    assert result["ready"], result["blockers"]
    assert result["workspaces"][0]["sessions"] == []


def test_discovery_rejects_registry_that_would_generate_chat_identity(
    tmp_path,
):
    from pathlib import Path
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
    )

    service = fixture_service(tmp_path)
    registry = (
        Path(service["source_root"])
        / "default_SRC"
        / "workspaces"
        / "agent"
        / "chats.json"
    )
    registry.chmod(0o644)
    registry.write_text(
        json.dumps(
            {"version": 1, "chats": [{"session_id": "sid", "user_id": "u"}]},
        ),
    )
    registry.chmod(0o444)
    report = discover_services([service])
    assert not report["ready"]
    assert any(
        item["code"] == "registry_invalid" for item in report["blockers"]
    )


def test_share_only_service_snapshot_lives_outside_workspace(tmp_path):
    from pathlib import Path
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
        freeze_discovery,
    )
    from swe.app.conversation_storage.migration.inventory_v3 import (
        inventory_v3,
    )

    source = tmp_path / "frozen"
    source.mkdir()
    snapshot = tmp_path / "snapshots"
    target = snapshot / "tenant" / "chat_shares" / "token.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"chat_name": "old share", "messages": []}')
    nas = tmp_path / "nas"
    nas.mkdir()
    for path in [source, snapshot, *snapshot.rglob("*")]:
        path.chmod(0o555 if path.is_dir() else 0o444)
    service = {
        "service_unit_id": "SERVICE",
        "source_root": str(source),
        "config_root": str(source),
        "nas_root": str(nas),
        "snapshot_root": str(snapshot),
    }
    share = {
        "token": "token",
        "chat_id": "deleted-chat",
        "creator_id": "u",
        "tenant_id": "tenant",
        "snapshot_key": "tenant/chat_shares/token.json",
        "created_at": "2026-11-01T00:00:00+00:00",
        "access_count": 4,
        "last_access_at": None,
    }
    report = discover_services([service], shares=[share])
    assert report["ready"], report["blockers"]
    boundary = SourceBoundary(
        "snapshot",
        "2026-11-02T00:00:00Z",
        "old@sha256:" + "a" * 64,
        ("stop", "readonly"),
    )
    manifest = freeze_discovery(
        report,
        tmp_path / "manifest.json",
        boundary,
        "business",
    )
    result = inventory_v3(manifest, begin_sync=True)
    assert result["ready"], result["blockers"]
    assert result["shares"][0]["scope_kind"] == "legacy_share"
    assert result["shares"][0]["record"]["access_count"] == 4
    cutoff = manifest.data["tenant_sync_started_at_ns"]["SERVICE\x00tenant"]
    import os

    os.utime(target, ns=(cutoff + 1, cutoff + 1))
    result = inventory_v3(manifest)
    assert not result["ready"]
    assert result["blockers"][0]["scope"] == ["SERVICE", "tenant"]
    assert result["blockers"][0]["path"] == str(target)


def test_relative_profile_requires_original_process_directory(tmp_path):
    from pathlib import Path
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
    )

    service = fixture_service(tmp_path)
    config = Path(service["source_root"]) / "default_SRC" / "config.json"
    value = json.loads(config.read_text())
    value["agents"]["profiles"]["agent"]["workspace_dir"] = "workspaces/agent"
    config.chmod(0o644)
    config.write_text(json.dumps(value))
    config.chmod(0o444)
    report = discover_services([service])
    assert not report["ready"]
    service["original_cwd"] = str(
        Path(service["original_root"]) / "default_SRC",
    )
    report = discover_services([service])
    assert report["ready"], report["blockers"]


def test_invalid_registry_json_is_reported_as_blocker(tmp_path):
    from pathlib import Path
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
    )

    service = fixture_service(tmp_path)
    registry = (
        Path(service["source_root"])
        / "default_SRC"
        / "workspaces"
        / "agent"
        / "chats.json"
    )
    registry.chmod(0o644)
    registry.write_text("{broken")
    registry.chmod(0o444)
    report = discover_services([service])
    assert not report["ready"]
    assert any(
        item["code"] == "registry_invalid" for item in report["blockers"]
    )


def test_registered_workspace_accepts_evidence_bound_orphan_session_mapping(
    tmp_path,
):
    from pathlib import Path
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
        source_key,
    )

    service = fixture_service(tmp_path)
    workspace = (
        Path(service["source_root"]) / "default_SRC" / "workspaces" / "agent"
    )
    workspace.chmod(0o755)
    sessions = workspace / "sessions"
    sessions.mkdir()
    (sessions / "legacy-name.json").write_text(
        '{"schema_version": 1, "future_module": {"value": 7}}',
    )
    (sessions / "legacy-name.json").chmod(0o444)
    sessions.chmod(0o555)
    workspace.chmod(0o555)
    override = {
        "position": source_key(
            "workspace",
            "SERVICE",
            "default_SRC/workspaces/agent",
        ),
        "discovery_version": 1,
        "evidence_refs": ["historical-session-identity"],
        "reason": "non-reversible legacy filename",
        "tenant_id": "default",
        "source_id": "SRC",
        "agent_id": "agent",
        "session_paths": [
            {
                "user_id": "u",
                "channel": "console",
                "session_id": "session",
                "path": "sessions/legacy-name.json",
            },
        ],
    }
    report = discover_services([service], overrides=[override])
    assert report["ready"], report["blockers"]
    assert report["workspaces"][0]["counts"]["sessions"] == 1
    override["tenant_id"] = "different"
    result = discover_services([service], overrides=[override])
    assert not result["ready"]
    assert any(
        item["code"] == "override_invalid" for item in result["blockers"]
    )


def test_share_access_count_requires_original_integer(tmp_path):
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
    )

    service = fixture_service(tmp_path)
    share = {
        "token": "token",
        "chat_id": "chat",
        "creator_id": "u",
        "tenant_id": "tenant",
        "snapshot_key": "tenant/chat_shares/token.json",
        "created_at": "2026-11-01T00:00:00+00:00",
        "access_count": "4",
        "last_access_at": None,
    }
    report = discover_services([service], shares=[share])
    assert not report["ready"]
    assert any("access count" in item["detail"] for item in report["blockers"])


def test_symlink_config_is_rejected_before_any_metadata_read(
    tmp_path,
    monkeypatch,
):
    from pathlib import Path
    from swe.app.conversation_storage.migration import discovery

    service = fixture_service(tmp_path)
    config = Path(service["source_root"]) / "default_SRC" / "config.json"
    config.parent.chmod(0o755)
    config.unlink()
    active = tmp_path / "active-config.json"
    active.write_text("{}")
    config.symlink_to(active)
    config.parent.chmod(0o555)

    def forbidden(_path):
        pytest.fail("unsafe source metadata was read before tree validation")

    monkeypatch.setattr(discovery, "_read_json", forbidden)
    report = discovery.discover_services([service])
    assert not report["ready"]
    assert any(item["code"] == "source_invalid" for item in report["blockers"])


def test_tenant_isolation_preserves_failed_config_and_parses_healthy(tmp_path):
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
    )

    service = fixture_service(tmp_path)
    source = Path(service["source_root"])
    source.chmod(0o755)
    broken = source / "broken"
    broken.mkdir()
    (broken / "config.json").write_text("{invalid")
    service["tenant_sources"] = {"broken": ["SRC"]}
    report = discover_services([service], tenant_isolation=True)
    assert not report["ready"]
    assert report["status"] == "partial_success"
    states = {t["tenant_id"]: t["state"] for t in report["tenants"]}
    assert states == {"broken": "failed", "default": "discovered"}
    assert report["workspaces"][0]["counts"] == {"sessions": 0, "chats": 0}
    assert report["declared_services"] == [service]


def test_tenant_isolation_rejects_mutable_original_inputs(tmp_path):
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
    )

    service = fixture_service(tmp_path)
    service["original_root"] = service["source_root"]
    with pytest.raises(ValueError, match="frozen inputs separate"):
        discover_services([service], tenant_isolation=True)


def test_tenant_isolation_does_not_swallow_shared_io_failure(tmp_path):
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
    )

    service = fixture_service(tmp_path)

    def shared_failure(_report):
        raise OSError(5, "storage unavailable")

    with pytest.raises(OSError, match="storage unavailable"):
        discover_services(
            [service],
            tenant_isolation=True,
            semantic_validator=shared_failure,
        )


def test_partial_freeze_keeps_failed_tenant_evidence(tmp_path):
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
        freeze_discovery,
    )

    service = fixture_service(tmp_path)
    source = Path(service["source_root"])
    source.chmod(0o755)
    broken = source / "broken"
    broken.mkdir()
    (broken / "config.json").write_text("{invalid")
    service["tenant_sources"] = {"broken": ["SRC"]}
    report = discover_services([service], tenant_isolation=True)
    boundary = SourceBoundary(
        "snapshot",
        "2026-11-02T00:00:00Z",
        "old@sha256:" + "a" * 64,
        ("stop", "readonly"),
    )
    manifest = freeze_discovery(
        report,
        tmp_path / "partial.json",
        boundary,
        "business",
    )
    assert manifest.data["tenant_isolation"] is True
    assert manifest.data["tenants"] == report["tenants"]
    (broken / "config.json").write_text('{"agents": {"profiles": {}}}')
    repaired = freeze_discovery(
        report,
        tmp_path / "changed.json",
        boundary,
        "business",
    )
    assert (
        next(
            t for t in repaired.data["tenants"] if t["tenant_id"] == "broken"
        )["state"]
        == "failed"
    )


def in_place_fixture(tmp_path):
    service = fixture_service(tmp_path)
    source = Path(service["source_root"])
    config = source / "default_SRC" / "config.json"
    config.chmod(0o644)
    data = json.loads(config.read_text())
    data["agents"]["profiles"]["agent"]["workspace_dir"] = str(
        source / "default_SRC" / "workspaces" / "agent",
    )
    config.write_text(json.dumps(data))
    config.chmod(0o444)
    service.update(original_root=str(source), snapshot_root=str(source))
    return service


def test_explicit_in_place_discovery_and_freeze_bind_mode(tmp_path):
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
        freeze_discovery,
    )

    service = in_place_fixture(tmp_path)
    report = discover_services([service], tenant_isolation=True, in_place=True)
    assert report["ready"], report["blockers"]
    assert report["in_place"] is True
    manifest = freeze_discovery(
        report,
        tmp_path / "in-place.json",
        SourceBoundary(
            "snapshot",
            "2026-11-13T00:00:00Z",
            "old@sha256:" + "a" * 64,
            ("stop", "readonly"),
        ),
        "business",
    )
    assert manifest.data["in_place"] is True
    from swe.app.conversation_storage.migration.journal import MigrationJournal

    assert (
        json.loads(MigrationJournal(None, manifest)._bindings()[1])["in_place"]
        is True
    )


def test_in_place_requires_explicit_isolation_and_identical_four_roots(
    tmp_path,
):
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
    )

    service = in_place_fixture(tmp_path)
    with pytest.raises(ValueError, match="tenant isolation"):
        discover_services([service], in_place=True)
    service["snapshot_root"] = service["nas_root"]
    report = discover_services([service], tenant_isolation=True, in_place=True)
    assert not report["ready"]
    assert any(b["code"] == "service_invalid" for b in report["blockers"])


def test_published_pruning_never_reads_live_config_and_keeps_unknown_candidates(
    tmp_path,
    monkeypatch,
):
    from swe.app.conversation_storage.migration.in_place_review import (
        published_pruning,
    )
    from swe.app.conversation_storage.migration.failure_scope import (
        config_candidates,
        strict_tenant_io,
    )
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
    )

    service = in_place_fixture(tmp_path)
    report = discover_services([service], tenant_isolation=True, in_place=True)
    source = Path(service["source_root"])
    source.chmod(0o755)
    unknown = source / "unknown"
    unknown.mkdir()
    (unknown / "config.json").write_text("{bad")
    real_scandir = __import__("os").scandir

    def guarded(path):
        assert Path(path) != source / "default_SRC"
        return real_scandir(path)

    monkeypatch.setattr("os.scandir", guarded)
    with (
        published_pruning(report, {("SERVICE", "default")}),
        strict_tenant_io(),
    ):
        candidates = config_candidates(source)
    assert source / "default_SRC" / "config.json" not in candidates
    assert unknown / "config.json" in candidates


def test_shared_in_place_tenant_boundary_only_fails_affected_accounts(
    tmp_path,
):
    from swe.app.conversation_storage.migration.tenant_discovery import (
        isolate_discovery,
    )

    root = tmp_path / "root"
    root.mkdir()
    service = {
        "service_unit_id": "svc",
        "source_root": str(root),
        "config_root": str(root),
        "snapshot_root": str(root),
        "original_root": str(root),
        "nas_root": str(tmp_path / "nas"),
    }
    workspaces = []
    for tenant, relative in (
        ("bob", "shared"),
        ("carol", "shared/child"),
        ("dave", "independent"),
    ):
        path = root / relative
        path.mkdir(parents=True, exist_ok=True)
        workspaces.append(
            {
                "service_unit_id": "svc",
                "tenant_id": tenant,
                "root": str(path),
                "runtime_root": str(path),
                "position": tenant,
                "evidence_refs": [],
            },
        )
    report = {
        "in_place": True,
        "services": [service],
        "workspaces": workspaces,
        "shares": [],
        "blockers": [],
    }
    isolate_discovery(
        report,
        [],
        lambda data: {
            "blockers": [],
            "workspaces": [
                {"sessions": [], "chats": []} for _ in data["workspaces"]
            ],
        },
    )
    assert {t["tenant_id"]: t["state"] for t in report["tenants"]} == {
        "bob": "failed",
        "carol": "failed",
        "dave": "discovered",
    }


@pytest.mark.parametrize(
    "attack",
    ["profile", "nested", "ancestor", "evidence", "session"],
)
def test_explicit_retry_candidate_never_touches_published_inputs(
    tmp_path,
    monkeypatch,
    attack,
):
    from swe.app.conversation_storage.migration.discovery import (
        discover_services,
        source_key,
    )
    from swe.app.conversation_storage.migration.in_place_review import (
        published_pruning,
    )

    from swe.config.context import encode_scope_id

    root, nas = tmp_path / "root", tmp_path / "nas"
    root.mkdir()
    nas.mkdir()
    configs, workspaces = {}, {}
    for name in ("alice", "bob", "dave"):
        tenant = root / encode_scope_id(name, "SRC")
        workspace = (
            (root / "external-a")
            if name == "alice"
            else tenant / "workspaces" / "agent"
        )
        workspace.mkdir(parents=True)
        (workspace / "agent.json").write_text('{"id":"agent"}')
        (workspace / "chats.json").write_text('{"version":1,"chats":[]}')
        tenant.mkdir(exist_ok=True)
        config = tenant / "config.json"
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
        configs[name], workspaces[name] = config, workspace
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
    frozen = discover_services([service], tenant_isolation=True, in_place=True)
    assert frozen["ready"], frozen["blockers"]
    overrides = []
    if attack in ("profile", "nested", "ancestor"):
        value = json.loads(configs["bob"].read_text())
        value["agents"]["profiles"]["agent"]["workspace_dir"] = str(
            (
                (workspaces["alice"] / "child")
                if attack == "nested"
                else workspaces["alice"] if attack == "profile" else root
            ),
        )
        configs["bob"].chmod(0o644)
        configs["bob"].write_text(json.dumps(value))
        configs["bob"].chmod(0o444)
    else:
        overrides = [
            {
                "position": source_key(
                    "workspace",
                    "svc",
                    workspaces["bob"].relative_to(root).as_posix(),
                ),
                "discovery_version": 1,
                "reason": "reviewed override",
                "tenant_id": "bob",
                "source_id": "SRC",
                "agent_id": "agent",
                "evidence_refs": [str(configs["bob"])],
                "session_paths": [],
            },
        ]
        if attack == "evidence":
            overrides[0]["evidence_refs"].append(
                str(workspaces["alice"] / "agent.json"),
            )
        else:
            overrides[0]["session_paths"] = [
                {
                    "path": str(workspaces["alice"] / "sessions" / "s.json"),
                    "user_id": "u",
                    "channel": "console",
                    "session_id": "s",
                },
            ]
    protected = (configs["alice"].parent, workspaces["alice"])
    original_stat, original_open, original_read = (
        Path.stat,
        Path.open,
        Path.read_bytes,
    )

    def check(path):
        if any(
            path == base or path.is_relative_to(base) for base in protected
        ):
            pytest.fail(
                "published filesystem input touched before rejection: "
                + str(path),
            )

    def guarded_stat(path, *args, **kwargs):
        check(path)
        return original_stat(path, *args, **kwargs)

    def guarded_open(path, *args, **kwargs):
        check(path)
        return original_open(path, *args, **kwargs)

    def guarded_read(path):
        check(path)
        return original_read(path)

    monkeypatch.setattr(Path, "stat", guarded_stat)
    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    with published_pruning(frozen, {("svc", "alice")}):
        report = discover_services(
            [service],
            overrides=overrides,
            tenant_isolation=True,
            in_place=True,
        )
    states = {t["tenant_id"]: t["state"] for t in report["tenants"]}
    assert states == {"bob": "failed", "dave": "discovered"}


def test_share_candidate_rejected_before_stat_of_published_snapshot(
    tmp_path,
    monkeypatch,
):
    from swe.app.conversation_storage.migration.discovery import _shares
    from swe.app.conversation_storage.migration.in_place_review import (
        published_pruning,
    )

    path = tmp_path / "bob" / "chat_shares" / "token.json"
    service = {
        "service_unit_id": "svc",
        "source_root": str(tmp_path),
        "snapshot_root": str(tmp_path),
    }
    frozen = {
        "services": [service],
        "tenants": [],
        "workspaces": [
            {
                "service_unit_id": "svc",
                "tenant_id": "alice",
                "root": str(tmp_path / "external-a"),
                "evidence_refs": [str(tmp_path / "alice" / "config.json")],
            },
        ],
        "shares": [
            {
                "service_unit_id": "svc",
                "tenant_id": "alice",
                "snapshot_path": str(path),
                "token": "token",
            },
        ],
    }
    source = {
        "token": "token",
        "chat_id": "chat",
        "creator_id": "u",
        "tenant_id": "bob",
        "snapshot_key": "bob/chat_shares/token.json",
        "created_at": "2026-11-01T00:00:00+00:00",
        "access_count": 0,
        "last_access_at": None,
    }
    original_stat = Path.stat

    def guarded_stat(candidate, *args, **kwargs):
        if candidate == path:
            pytest.fail("published share snapshot stat before rejection")
        return original_stat(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", guarded_stat)
    report = {"shares": [], "blockers": []}
    with published_pruning(frozen, {("svc", "alice")}):
        _shares([service], [source], report)
    assert report["shares"] == []
    assert len(report["blockers"]) == 1
    assert report["blockers"][0]["code"] == "share_invalid"
    assert report["blockers"][0]["position"] == "token"
    assert "published tenant" in report["blockers"][0]["detail"]


@pytest.mark.parametrize("ownership", ["known", "unknown", "ambiguous"])
def test_review_share_uses_frozen_service_without_probing_published_namesake(
    tmp_path,
    monkeypatch,
    ownership,
):
    from swe.app.conversation_storage.migration.discovery import _shares
    from swe.app.conversation_storage.migration.in_place_review import (
        published_pruning,
    )

    services = [
        {
            "service_unit_id": name,
            "source_root": str(tmp_path / name),
            "snapshot_root": str(tmp_path / name),
        }
        for name in ("svcA", "svcB")
    ]
    a_root = tmp_path / "svcA" / "alice"
    b_snapshot = tmp_path / "svcB" / "alice" / "chat_shares" / "token.json"
    b_snapshot.parent.mkdir(parents=True)
    b_snapshot.write_text('{"chat_name":"old share","messages":[]}')
    frozen = {
        "services": services,
        "workspaces": [],
        "tenants": [
            {
                "service_unit_id": "svcA",
                "tenant_id": "alice",
                "evidence_refs": [str(a_root / "config.json")],
            },
        ],
        "shares": (
            []
            if ownership == "unknown"
            else [
                {
                    "token": "token",
                    "service_unit_id": "svcB",
                    "tenant_id": "alice",
                    "snapshot_path": str(b_snapshot),
                },
            ]
        ),
    }
    if ownership == "ambiguous":
        frozen["shares"].append(
            {
                "token": "token",
                "service_unit_id": "svcA",
                "tenant_id": "alice",
                "snapshot_path": str(a_root / "chat_shares" / "token.json"),
            },
        )
    source = {
        "token": "token",
        "chat_id": "chat",
        "creator_id": "u",
        "tenant_id": "alice",
        "snapshot_key": "alice/chat_shares/token.json",
        "created_at": "2026-11-01T00:00:00+00:00",
        "access_count": 0,
        "last_access_at": None,
    }
    original_stat, original_read = Path.stat, Path.read_bytes

    def check(path):
        if path == a_root or path.is_relative_to(a_root):
            pytest.fail("published same-name tenant share input touched")

    def guarded_stat(path, *args, **kwargs):
        check(path)
        return original_stat(path, *args, **kwargs)

    def guarded_read(path):
        check(path)
        return original_read(path)

    monkeypatch.setattr(Path, "stat", guarded_stat)
    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    report = {"shares": [], "blockers": []}
    with published_pruning(frozen, {("svcA", "alice")}):
        _shares(services, [source], report)
    if ownership == "known":
        assert report["blockers"] == []
        assert report["shares"][0]["service_unit_id"] == "svcB"
    else:
        assert report["shares"] == []
        assert len(report["blockers"]) == 1
        assert "absent or ambiguous" in report["blockers"][0]["detail"]
