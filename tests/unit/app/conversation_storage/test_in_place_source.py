# -*- coding: utf-8 -*-
import os
import time

import pytest

from swe.app.conversation_storage.migration.in_place_source import (
    evidence_paths,
    freeze_evidence,
    verify_evidence,
)
from swe.app.conversation_storage.migration.inventory_parallel import (
    _shared_freshness,
)
from swe.app.conversation_storage.migration.inventory_v3 import (
    inventory_discovery,
)
from swe.app.conversation_storage.migration.source_inputs import (
    SourceInputInvalid,
)


@pytest.fixture
def in_place_data(tmp_path):
    source = tmp_path / "source"
    workspace = source / "B" / "workspaces" / "agent"
    workspace.mkdir(parents=True)
    config = source / "B" / "config.json"
    config.write_text("{}")
    agent = workspace / "agent.json"
    agent.write_text('{"id":"agent"}')
    (workspace / "chats.json").write_text('{"version":1,"chats":[]}')
    shared_config = source / "config.json"
    shared_config.write_text("{}")
    for path in source.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    item = {
        "root": str(workspace),
        "service_unit_id": "S",
        "tenant_id": "B",
        "source_id": "SRC",
        "agent_id": "agent",
        "position": "B-agent",
        "evidence_refs": [str(config), str(agent), str(shared_config)],
    }
    item["in_place_evidence"] = freeze_evidence(item)
    cutoff = time.time_ns()
    return {
        "in_place": True,
        "tenant_isolation": True,
        "services": [
            {
                key: str(source)
                for key in (
                    "source_root",
                    "config_root",
                    "snapshot_root",
                    "original_root",
                )
            },
        ],
        "workspaces": [item],
        "shares": [],
        "tenant_sync_started_at_ns": {"S\x00B": cutoff},
    }


def test_shared_service_root_changes_do_not_taint_unpublished_tenant(
    in_place_data,
):
    data = in_place_data
    root = data["services"][0]["source_root"]
    cutoff = data["tenant_sync_started_at_ns"]["S\x00B"]
    os.utime(root, ns=(cutoff + 1, cutoff + 1))
    assert root not in evidence_paths(data, data["workspaces"][0])
    assert inventory_discovery(data)["ready"]
    # The parallel cache must use exactly the same shallow-root exemption.
    data["workspaces"].append(dict(data["workspaces"][0]))
    assert (root, cutoff) not in _shared_freshness(data)


@pytest.mark.parametrize("relative", ["B", "B/workspaces/agent/chats.json"])
def test_private_parent_and_conversation_changes_remain_blocking(
    in_place_data,
    relative,
):
    from pathlib import Path

    data = in_place_data
    path = Path(data["services"][0]["source_root"]) / relative
    cutoff = data["tenant_sync_started_at_ns"]["S\x00B"]
    os.utime(path, ns=(cutoff + 1, cutoff + 1))
    report = inventory_discovery(data)
    assert not report["ready"]
    assert report["blockers"][0]["path"] == str(path)


def test_default_mode_keeps_shared_parent_freshness(in_place_data):
    data = in_place_data
    data["in_place"] = False
    root = data["services"][0]["source_root"]
    cutoff = data["tenant_sync_started_at_ns"]["S\x00B"]
    os.utime(root, ns=(cutoff + 1, cutoff + 1))
    assert not inventory_discovery(data)["ready"]


def test_evidence_content_change_cannot_hide_behind_old_mtime(in_place_data):
    from pathlib import Path

    data = in_place_data
    config = Path(data["workspaces"][0]["evidence_refs"][0])
    before = config.stat()
    config.chmod(0o644)
    config.write_text('{"changed":true}')
    config.chmod(0o444)
    os.utime(config, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(SourceInputInvalid, match="evidence changed"):
        inventory_discovery(data)


def test_evidence_must_remain_readonly(in_place_data):
    from pathlib import Path

    data = in_place_data
    Path(data["workspaces"][0]["evidence_refs"][0]).chmod(0o644)
    with pytest.raises(SourceInputInvalid, match="writable"):
        verify_evidence(data, data["workspaces"][0])


def test_evidence_reader_is_bounded(in_place_data, monkeypatch):
    from swe.app.conversation_storage.migration import in_place_source
    from swe.app.conversation_storage.migration.spool import (
        MigrationCapacityError,
    )

    monkeypatch.setattr(in_place_source, "MAX_READ_BYTES", 1)
    with pytest.raises(MigrationCapacityError, match="bounded reader limit"):
        freeze_evidence(in_place_data["workspaces"][0])


def test_workspace_inventory_does_not_read_other_tenant_evidence(
    in_place_data,
    monkeypatch,
):
    from swe.app.conversation_storage.migration import inventory_v3

    data = in_place_data
    data["tenants"] = [
        {"service_unit_id": "S", "tenant_id": "A"},
        {"service_unit_id": "S", "tenant_id": "B"},
    ]
    checked = []
    original = inventory_v3.verify_evidence

    def record(scope, item):
        checked.append(item["tenant_id"])
        original(scope, item)

    monkeypatch.setattr(inventory_v3, "verify_evidence", record)
    assert inventory_v3.inventory_workspace(data, 0)["ready"]
    assert checked == ["B", "B"]


def test_identity_replacement_during_hash_is_rejected(
    in_place_data,
    monkeypatch,
):
    from swe.app.conversation_storage.migration import in_place_source

    original = in_place_source.os.fstat

    def changed_fstat(fd):
        from types import SimpleNamespace

        details = original(fd)
        return SimpleNamespace(
            **{
                key: getattr(details, key) + (key == "st_ino")
                for key in (
                    "st_dev",
                    "st_ino",
                    "st_size",
                    "st_mtime_ns",
                    "st_ctime_ns",
                    "st_mode",
                )
            },
        )

    monkeypatch.setattr(in_place_source.os, "fstat", changed_fstat)
    with pytest.raises(SourceInputInvalid, match="changed while reading"):
        freeze_evidence(in_place_data["workspaces"][0])
