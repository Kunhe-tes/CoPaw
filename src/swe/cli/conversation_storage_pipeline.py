# -*- coding: utf-8 -*-
"""Bounded read-ahead; SQL and publication stay in the calling task."""

import asyncio
from contextlib import asynccontextmanager

from swe.app.conversation_storage.migration.parallel import (
    MigrationIO,
    MigrationResources,
    _drain,
)


def _resource_views(resources, shared, io, allowance):
    common = {
        **resources,
        "workers": 1,
        "memory_bytes": allowance,
        "_shared_io": io,
    }
    return (
        {**common, "_shared_resources": shared},
        {
            **common,
            "_shared_resources": MigrationResources(
                workers=1,
                memory_bytes=allowance,
                io=io,
            ),
        },
    )


async def _close_pipeline(stream, tasks, live):
    try:
        await stream.aclose()
    finally:
        for task in tasks:
            task.cancel()
        cleanup = asyncio.ensure_future(
            asyncio.gather(*tasks, return_exceptions=True),
        )
        try:
            await _drain(cleanup, propagate_cancel=True)
        finally:
            for spool in live.values():
                spool.__exit__(None, None, None)


@asynccontextmanager
async def tenant_pipeline(tenants, base, data, resources):
    from .conversation_storage_tenants import (
        TenantManifest,
        TenantFailure,
        _inventory,
        _spool,
        MigrationCapacityError,
        MigrationDiskCapacityError,
        TenantInputError,
    )

    count = resources["workers"]
    allowance = resources["memory_bytes"] // count
    width = max(1, count - 1)
    pending = []
    tasks = set()
    iterator = iter(tenants)
    live = {}
    async with MigrationIO(resources["io_workers"]) as io:
        async with MigrationResources(
            workers=width,
            io=io,
            memory_bytes=allowance * width,
        ) as shared:
            parser, owner = _resource_views(resources, shared, io, allowance)

            async def read(tenant):
                spool = _spool(base, data.data, allowance, 1)
                spool.__enter__()
                live[id(tenant)] = spool
                try:
                    result = await _inventory(
                        TenantManifest(data, tenant),
                        spool,
                        parser,
                    )
                except MigrationDiskCapacityError:
                    raise
                except (
                    TenantFailure,
                    TenantInputError,
                    MigrationCapacityError,
                ) as error:
                    return tenant, None, error
                return tenant, result, None

            def fill():
                while len(pending) < width:
                    tenant = next(iterator, None)
                    if tenant is None:
                        break
                    task = asyncio.create_task(read(tenant))
                    tasks.add(task)
                    pending.append(task)

            async def health():
                for task in tasks:
                    if task.done():
                        task.result()

            async def results():
                fill()
                while pending:
                    # Shared failures must not hide behind an earlier slow tenant.
                    await health()
                    task = pending.pop(0)
                    while not task.done():
                        await asyncio.wait(
                            [item for item in tasks if not item.done()],
                            timeout=0.1,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        await health()
                    tenant, inventory, error = task.result()
                    if count > 1:
                        fill()
                    try:
                        yield tenant, {
                            **owner,
                            "_prefetched": inventory,
                            "_pipeline_health": health,
                        }, error
                    finally:
                        live.pop(id(tenant)).__exit__(None, None, None)
                        tasks.discard(task)
                    if count == 1:
                        fill()

            stream = results()
            try:
                yield stream
            finally:
                await _close_pipeline(stream, tasks, live)
