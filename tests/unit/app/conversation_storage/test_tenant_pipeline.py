# -*- coding: utf-8 -*-
"""Read-ahead overlaps tenants without moving SQL to worker tasks."""

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from swe.cli import conversation_storage_tenants as cli
from swe.cli.conversation_storage_pipeline import tenant_pipeline
from swe.app.conversation_storage.migration.spool_report import (
    WorkspaceRecords,
)


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
            assert local["memory_bytes"] == 128
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
