# -*- coding: utf-8 -*-
"""Bounded selection and grouped views retain exact source evidence."""

from types import SimpleNamespace

import pytest

from swe.app.conversation_storage.migration.source_state import SourceState
from swe.app.conversation_storage.migration.tenant_state import TenantState
from swe.app.conversation_storage.migration.disk_manifest import (
    disk_index_policy,
    DiskGroups,
)
from swe.app.conversation_storage.migration.spool import MigrationCapacityError
from swe.cli import conversation_storage_tenants as cli

JOB = "00000000-0000-4000-8000-000000000001"


class StateDatabase:
    def __init__(self, width):
        self.width = width
        self.reads = []

    async def fetch_all(self, query, params):
        self.reads.append((query, params))
        fields = ("service_unit_key", "tenant_key", "source_key")[: self.width]
        return [
            dict(zip(fields, params[i : i + self.width]), state="published")
            for i in range(1, len(params), self.width)
        ]


@pytest.mark.parametrize("store,width", [(TenantState, 2), (SourceState, 3)])
async def test_bulk_state_reads_are_bounded_and_keep_full_identity(
    store,
    width,
):
    db = StateDatabase(width)
    states = store(db, JOB)
    keys = [
        ("svc", str(i), *(("source",) if width == 3 else ()))
        for i in range(601)
    ]
    rows = {key: row async for key, row in states.get_many(keys)}
    assert len(rows) == 601
    assert rows[keys[-1]]["state"] == "published"
    assert len(db.reads) == 3
    assert all(len(params) <= 1 + width * 256 for _, params in db.reads)
    assert [row async for row in states.get_many([])] == []
    assert len(db.reads) == 3


async def test_selection_uses_bulk_states_and_skips_published_before_views(
    tmp_path,
    monkeypatch,
):
    tenants = [
        {
            "service_unit_id": "svc",
            "tenant_id": "alice",
            "source_id": str(i),
            "state": "discovered",
        }
        for i in range(601)
    ]
    manifest = SimpleNamespace(
        data={"source_isolation": True, "tenants": tenants},
    )
    states = SourceState(StateDatabase(3), JOB)
    monkeypatch.setattr(
        cli,
        "TenantManifest",
        lambda *_: pytest.fail("published source constructed a reader view"),
    )
    selected, failures, published = await cli._select_registered_tenants(
        manifest,
        states,
        {},
        [],
        0,
    )
    assert (selected, failures, published) == ([], [], 601)
    assert len(states.db.reads) == 3


class CountedList(list):
    def __iter__(self):
        self.scans += 1
        return super().__iter__()

    scans = 0


def test_grouped_views_scan_once_and_rebuild_after_evidence_revision(tmp_path):
    tenants = [
        {"service_unit_id": "svc", "tenant_id": "alice", "source_id": str(i)}
        for i in range(40)
    ]
    workspaces = CountedList(
        [{**tenant, "root": str(i)} for i, tenant in enumerate(tenants)],
    )
    parent = SimpleNamespace(
        migration_id=JOB,
        path=tmp_path / "manifest.json",
        data={
            "source_isolation": True,
            "tenants": tenants,
            "workspaces": workspaces,
            "shares": [],
        },
    )
    with disk_index_policy(tmp_path.resolve(), 1024 * 1024) as policy:
        for tenant in tenants:
            view = cli.TenantManifest(parent, tenant)
            assert (
                view.data["workspaces"][0]["source_id"] == tenant["source_id"]
            )
        assert workspaces.scans == 1
        assert 0 < policy.used_bytes() <= 1024 * 1024
        parent.data = {
            **parent.data,
            "tenant_review_revision": "revised",
            "workspaces": [{**tenants[0], "root": "revised"}],
        }
        assert (
            cli.TenantManifest(parent, tenants[0]).data["workspaces"][0][
                "root"
            ]
            == "revised"
        )
        assert cli.TenantManifest(parent, tenants[-1]).data["workspaces"] == []


def test_grouped_positions_share_disk_budget_and_preserve_order(tmp_path):
    with disk_index_policy(tmp_path.resolve(), 65536) as policy:
        groups = DiskGroups()
        groups.add("source", 4)
        groups.add("other", 8)
        groups.add("source", 2)
        assert list(groups.positions("source")) == [4, 2]
        with pytest.raises(MigrationCapacityError):
            for i in range(100):
                groups.add(str(i) + "x" * 4096, i)
        assert policy.used_bytes() <= 65536


def test_grouped_view_reopens_after_command_budget_closes(tmp_path):
    tenant = {"service_unit_id": "svc", "tenant_id": "alice"}
    parent = SimpleNamespace(
        migration_id=JOB,
        path=tmp_path / "manifest.json",
        data={"tenants": [tenant], "workspaces": [], "shares": []},
    )
    with disk_index_policy(tmp_path.resolve(), 65536):
        assert cli.TenantManifest(parent, tenant).data["tenants"] == [tenant]
    with disk_index_policy(tmp_path.resolve(), 65536):
        assert cli.TenantManifest(parent, tenant).data["tenants"] == [tenant]
