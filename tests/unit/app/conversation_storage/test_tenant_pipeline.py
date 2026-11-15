# -*- coding: utf-8 -*-
"""Read-ahead overlaps tenants without moving SQL to worker tasks."""

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, Mock

from swe.cli import conversation_storage_tenants as cli
from swe.cli.conversation_storage_pipeline import tenant_pipeline
from swe.app.conversation_storage.migration.spool_report import (
    WorkspaceRecords,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tenant_count, expected",
    [(1, [4]), (3, [2, 3, 4]), (5, [1, 1, 2, 3, 4])],
)
async def test_pipeline_lends_unused_slots_to_large_tenant(
    monkeypatch,
    tenant_count,
    expected,
):
    @contextmanager
    def spool(*_args):
        yield None

    async def inventory(*_args):
        return {}

    monkeypatch.setattr(cli, "_spool", spool)
    monkeypatch.setattr(cli, "_inventory", inventory)
    monkeypatch.setattr(cli, "TenantManifest", lambda *_: None)
    resources = {"workers": 4, "io_workers": 4, "memory_bytes": 400}
    widths = []
    async with tenant_pipeline(
        [{"tenant_id": str(i)} for i in range(tenant_count)],
        None,
        SimpleNamespace(data={}),
        resources,
    ) as results:
        async for _, local, _ in results:
            width = local["workers"]
            widths.append(width)
            assert local["memory_bytes"] == width * 100
            assert local["_shared_resources"].workers == width
            assert local["_shared_resources"].allowance == 100
    assert widths == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("preview", [True, False])
async def test_single_tenant_uses_available_workspace_workers(
    monkeypatch,
    preview,
):
    @contextmanager
    def spool(*_args):
        yield None

    async def inventory(_view, _spool, local):
        assert local["workers"] == 4
        assert local["memory_bytes"] == 400
        assert local["_shared_resources"].allowance == 100
        return {}

    monkeypatch.setattr(cli, "_spool", spool)
    monkeypatch.setattr(cli, "_inventory", inventory)
    monkeypatch.setattr(cli, "TenantManifest", lambda *_: None)
    async with tenant_pipeline(
        [{}],
        None,
        SimpleNamespace(data={}),
        {"workers": 4, "io_workers": 4, "memory_bytes": 400},
        preview=preview,
    ) as results:
        async for _, _, error in results:
            assert error is None


@pytest.mark.asyncio
async def test_preview_overlaps_tenants_skips_published_and_isolates_failure(
    monkeypatch,
):
    active, peak = 0, 0
    both = asyncio.Event()
    visited = []
    owner = asyncio.current_task()

    @contextmanager
    def spool(*_args):
        yield None

    async def inventory(view, _spool, resources):
        nonlocal active, peak
        assert resources["workers"] == 1
        visited.append(view.key[1])
        active += 1
        peak = max(peak, active)
        if active == 2:
            both.set()
        try:
            await asyncio.wait_for(both.wait(), 1)
            if view.key[1] == "bad":
                raise cli.TenantFailure("bad input")
            return {}
        finally:
            active -= 1

    async def state(_service, tenant):
        assert asyncio.current_task() is owner
        return {"state": "published" if tenant == "live" else "discovered"}

    tenants = [
        {
            "service_unit_id": "s",
            "tenant_id": name,
            "state": "failed" if name == "failed" else "discovered",
        }
        for name in ("live", "failed", "bad", "good", "last")
    ]
    monkeypatch.setattr(cli, "_spool", spool)
    monkeypatch.setattr(cli, "_inventory", inventory)
    monkeypatch.setattr(
        cli,
        "TenantManifest",
        lambda _, t: SimpleNamespace(key=("s", t["tenant_id"])),
    )
    writer = Mock(return_value="failures.json")
    monkeypatch.setattr(cli, "_write_failures", writer)
    result = await cli._preview(
        "preflight",
        SimpleNamespace(data={"tenants": tenants}, migration_id="job"),
        None,
        {"workers": 2, "io_workers": 2, "memory_bytes": 256},
        states=SimpleNamespace(get=AsyncMock(side_effect=state)),
    )
    assert peak == 2
    assert visited == ["bad", "good", "last"]
    assert result["completed"] == 3
    assert result["failed"] == 2
    assert {f["tenant_id"] for f in writer.call_args.args[2]} == {
        "failed",
        "bad",
    }


@pytest.mark.asyncio
async def test_pipeline_overlaps_next_tenant_with_owner_and_closes_spools(
    monkeypatch,
):
    opened, closed = [], []
    second = asyncio.Event()
    owner = asyncio.current_task()

    @contextmanager
    def spool(*_args):
        marker = len(opened)
        opened.append(marker)
        try:
            yield marker
        finally:
            closed.append(marker)

    async def inventory(view, _spool, resources):
        assert resources["workers"] == 1
        if view.key[1] == "b":
            second.set()
        await asyncio.sleep(0)
        return {"tenant": view.key[1]}

    monkeypatch.setattr(cli, "_spool", spool)
    monkeypatch.setattr(cli, "_inventory", inventory)
    monkeypatch.setattr(
        cli,
        "TenantManifest",
        lambda _, t: SimpleNamespace(key=("s", t["tenant_id"])),
    )
    resources = {"workers": 2, "io_workers": 2, "memory_bytes": 256}
    tenants = [{"tenant_id": name} for name in ("a", "b", "c")]
    async with tenant_pipeline(
        tenants,
        None,
        SimpleNamespace(data={}),
        resources,
    ) as results:
        visited = []
        async for tenant, local, error in results:
            assert asyncio.current_task() is owner
            assert error is None
            assert local["memory_bytes"] == 128 * local["workers"]
            visited.append(tenant["tenant_id"])
            if tenant["tenant_id"] == "a":
                await asyncio.wait_for(second.wait(), 1)
    assert visited == ["a", "b", "c"]
    assert sorted(opened) == sorted(closed)


@pytest.mark.asyncio
async def test_pipeline_releases_prefetched_workspace_body_cache(monkeypatch):
    workspaces = WorkspaceRecords(None, [])
    workspaces._cached_index = 0
    workspaces._cached_record = {"body": "prefetched session"}

    @contextmanager
    def spool(*_args):
        yield None

    async def inventory(*_args):
        return {"workspaces": workspaces}

    monkeypatch.setattr(cli, "_spool", spool)
    monkeypatch.setattr(cli, "_inventory", inventory)
    monkeypatch.setattr(cli, "TenantManifest", lambda *_: None)
    resources = {"workers": 2, "io_workers": 2, "memory_bytes": 256}
    async with tenant_pipeline(
        [{"tenant_id": "a"}],
        None,
        SimpleNamespace(data={}),
        resources,
    ) as results:
        async for _tenant, local, error in results:
            assert error is None
            assert local["_prefetched"]["workspaces"] is workspaces
            assert workspaces._cached_index is None
            assert workspaces._cached_record is None


@pytest.mark.asyncio
async def test_pipeline_shared_failure_drains_running_reader(monkeypatch):
    drained = asyncio.Event()

    @contextmanager
    def spool(*_args):
        yield None

    async def inventory(view, *_args):
        if view.key[1] == "b":
            raise OSError("shared disk")
        try:
            await asyncio.sleep(10)
        finally:
            drained.set()

    monkeypatch.setattr(cli, "_spool", spool)
    monkeypatch.setattr(cli, "_inventory", inventory)
    monkeypatch.setattr(
        cli,
        "TenantManifest",
        lambda _, t: SimpleNamespace(key=("s", t["tenant_id"])),
    )
    resources = {"workers": 3, "io_workers": 2, "memory_bytes": 300}
    tenants = [{"tenant_id": name} for name in ("b", "c")]
    with pytest.raises(OSError, match="shared disk"):
        async with tenant_pipeline(
            tenants,
            None,
            SimpleNamespace(data={}),
            resources,
        ) as results:
            async for _result in results:
                pass
    assert drained.is_set()


@pytest.mark.asyncio
async def test_pipeline_owner_failure_closes_current_and_pending_spools(
    monkeypatch,
):
    opened, closed = [], []
    pending = asyncio.Event()

    @contextmanager
    def spool(*_args):
        marker = len(opened)
        opened.append(marker)
        try:
            yield marker
        finally:
            closed.append(marker)

    async def inventory(view, *_args):
        if view.key[1] == "b":
            pending.set()
            await asyncio.sleep(10)
        return {}

    monkeypatch.setattr(cli, "_spool", spool)
    monkeypatch.setattr(cli, "_inventory", inventory)
    monkeypatch.setattr(
        cli,
        "TenantManifest",
        lambda _, t: SimpleNamespace(key=("s", t["tenant_id"])),
    )
    resources = {"workers": 2, "io_workers": 2, "memory_bytes": 256}
    with pytest.raises(RuntimeError, match="owner failed"):
        async with tenant_pipeline(
            [{"tenant_id": "a"}, {"tenant_id": "b"}],
            None,
            SimpleNamespace(data={}),
            resources,
        ) as results:
            async for _result in results:
                await asyncio.wait_for(pending.wait(), 1)
                raise RuntimeError("owner failed")
    assert sorted(opened) == sorted(closed)
