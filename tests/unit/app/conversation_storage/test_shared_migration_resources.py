# -*- coding: utf-8 -*-
import asyncio
import threading

import pytest

from swe.app.conversation_storage.migration.parallel import (
    MigrationIO,
    MigrationResources,
)
from swe.app.conversation_storage.migration.spool import InventorySpool
from swe.app.conversation_storage.migration.inventory_parallel import (
    spool_workspaces,
)
from swe.app.conversation_storage.migration.tenant_discovery import (
    map_tenant_semantics,
)


async def test_tenants_share_parser_slots_memory_and_borrowed_io(
    tmp_path,
    monkeypatch,
):
    from swe.app.conversation_storage.migration import inventory_parallel

    lock, barrier = threading.Lock(), threading.Barrier(2)
    active = peak = 0

    def parse(data, _index):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            barrier.wait(timeout=3)
            tenant = data["workspaces"][0]["tenant_id"]
            return {
                "workspaces": [
                    {
                        "scope": ["svc", tenant, "src", "a"],
                        "position": tenant,
                        "sessions": [],
                        "chats": [],
                    },
                ],
                "files": [],
                "blockers": [],
            }
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(inventory_parallel, "inventory_workspace", parse)
    monkeypatch.setattr(
        inventory_parallel,
        "_preflight_workspace",
        lambda *_: 0,
    )
    spools = [
        InventorySpool(tmp_path, max_bytes=1000000, record_limit=100000)
        for _ in range(4)
    ]
    async with MigrationIO(2) as io:
        async with MigrationResources(
            workers=2,
            memory_bytes=200000,
            io=io,
        ) as shared:
            for spool in spools:
                spool.__enter__()
            try:
                results = await asyncio.gather(
                    *[
                        spool_workspaces(
                            {
                                "workspaces": [
                                    {
                                        "service_unit_id": "svc",
                                        "tenant_id": str(i),
                                        "position": str(i),
                                    },
                                ],
                            },
                            spool,
                            workers=1,
                            shared_resources=shared,
                        )
                        for i, spool in enumerate(spools)
                    ],
                )
            finally:
                for spool in spools:
                    spool.__exit__(None, None, None)
            assert len(results) == 4
            assert peak == 2
            assert shared.memory.peak == 200000
            assert shared.memory.used == 0
        assert await io.call(lambda: "still open") == "still open"


def test_discovery_tenant_pool_is_bounded_and_keeps_local_failures(
    monkeypatch,
):
    from swe.app.conversation_storage.migration import (
        inventory_parallel,
        inventory_v3,
    )
    from swe.app.conversation_storage.migration.source_inputs import (
        SourceInputInvalid,
    )

    barrier = threading.Barrier(2)
    lock = threading.Lock()
    active = peak = 0

    def inventory(data, _index):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            barrier.wait(timeout=3)
            if data["tenant"] == "bad":
                raise SourceInputInvalid("bad tenant")
            return {
                "blockers": [],
                "workspaces": [{"sessions": [1], "chats": [], "scope": []}],
            }
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(inventory_v3, "inventory_workspace", inventory)
    monkeypatch.setattr(
        inventory_parallel,
        "_preflight_workspace",
        lambda *_: 0,
    )
    data = [
        {"tenant": name, "workspaces": [{}], "shares": []}
        for name in ("a", "bad", "c", "d")
    ]
    results = list(
        map_tenant_semantics(
            data,
            workers=4,
            io_workers=2,
            memory_bytes=400000,
        ),
    )
    assert peak == 2
    assert len(results[0]["workspaces"][0]["sessions"]) == 1
    assert isinstance(results[1], SourceInputInvalid)
    assert results[2]["blockers"] == results[3]["blockers"] == []


def test_discovery_pool_copies_readonly_boundary_context_and_propagates_shared(
    monkeypatch,
):
    from contextvars import ContextVar
    from swe.app.conversation_storage.migration import (
        inventory_v3,
        inventory_parallel,
    )

    boundary = ContextVar("test_boundary", default=False)
    boundary.set(True)

    def inventory(_data, _index):
        assert boundary.get() is True
        raise OSError("shared mount failed")

    monkeypatch.setattr(inventory_v3, "inventory_workspace", inventory)
    monkeypatch.setattr(
        inventory_parallel,
        "_preflight_workspace",
        lambda *_: 0,
    )
    with pytest.raises(OSError, match="shared mount"):
        list(
            map_tenant_semantics(
                [{"workspaces": [{}], "shares": []}],
                workers=2,
            ),
        )


async def test_shared_budget_waiter_cancellation_releases_gate():
    entered = asyncio.Event()
    release = asyncio.Event()
    async with MigrationResources(workers=1, memory_bytes=100) as shared:

        async def hold():
            async with shared.reserve():
                entered.set()
                await release.wait()

        owner = asyncio.create_task(hold())
        await entered.wait()
        waiting = asyncio.create_task(hold())
        await asyncio.sleep(0)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        release.set()
        await owner
        async with shared.reserve():
            assert shared.memory.used == 100
        assert shared.memory.used == 0


def test_discovery_keeps_single_workspace_budget_for_large_tenant(monkeypatch):
    from swe.app.conversation_storage.migration import (
        inventory_parallel,
        inventory_v3,
    )

    allowances = []

    def preflight(_workspace, allowance):
        allowances.append(allowance)
        return allowance // 16

    def inventory(_data, index):
        return {
            "workspaces": [
                {
                    "scope": ["svc", "tenant", "src", str(index)],
                    "sessions": [index],
                    "chats": [],
                },
            ],
            "blockers": [],
        }

    monkeypatch.setattr(inventory_parallel, "_preflight_workspace", preflight)
    monkeypatch.setattr(inventory_v3, "inventory_workspace", inventory)
    results = list(
        map_tenant_semantics(
            [{"workspaces": [{}] * 12, "shares": []}],
            workers=4,
            memory_bytes=400000,
        ),
    )
    assert len(results[0]["workspaces"]) == 12
    assert allowances == [100000] * 12


def test_input_digests_share_bounded_pool_and_skip_retained(monkeypatch):
    from copy import deepcopy
    from functools import partial
    from swe.app.conversation_storage.migration import tenant_inputs
    from swe.app.conversation_storage.migration.tenant_discovery import (
        map_tenant_calls,
    )

    lock, barrier = threading.Lock(), threading.Barrier(2)
    active = peak = 0
    seen = []

    def digest(_data, key):
        nonlocal active, peak
        assert key[1] != "published"
        with lock:
            active += 1
            peak = max(peak, active)
            seen.append(key[1])
        try:
            barrier.wait(timeout=3)
            return key[1] + "-hash"
        finally:
            with lock:
                active -= 1

    report = {
        "tenants": [
            {
                "service_unit_id": "svc",
                "tenant_id": name,
                "state": "discovered",
                "blockers": [],
                "input_digest": "old",
            }
            for name in ("published", "a", "b", "c", "d")
        ],
        "blockers": [],
    }
    monkeypatch.setattr(tenant_inputs, "input_digest", digest)
    with tenant_inputs.retained_input_digests(
        deepcopy(report),
        {("svc", "published")},
    ):
        tenant_inputs.capture_input_digests(
            report,
            mapper=partial(map_tenant_calls, workers=4, io_workers=2),
        )
    assert peak == 2
    assert sorted(seen) == ["a", "b", "c", "d"]
    assert report["tenants"][0]["input_digest"] == "old"
