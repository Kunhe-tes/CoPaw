# -*- coding: utf-8 -*-
"""Bounded read-ahead; SQL and publication stay in the calling task."""

import asyncio
from contextlib import asynccontextmanager

from swe.app.conversation_storage.migration.parallel import (
    MigrationIO,
    MigrationResources,
    _drain,
)
from swe.app.conversation_storage.migration.spool_report import (
    WorkspaceRecords,
)


def _owner_resources(resources, io, allowance, workers):
    return {
        **resources,
        "workers": workers,
        "memory_bytes": allowance * workers,
        "_shared_io": io,
        "_shared_resources": MigrationResources(
            workers=workers,
            memory_bytes=allowance * workers,
            io=io,
        ),
    }


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


def _pipeline_limits(resources, tenants, preview):
    count = resources["workers"]
    allowance = resources["memory_bytes"] // count
    width = min(count, max(1, len(tenants))) if preview else max(1, count - 1)
    parser_workers = (
        max(1, count // width)
        if preview
        else count if len(tenants) == 1 else 1
    )
    shared_workers = count if preview else max(width, parser_workers)
    return count, allowance, width, parser_workers, shared_workers


@asynccontextmanager
async def tenant_pipeline(tenants, base, data, resources, *, preview=False):
    from .conversation_storage_tenants import (
        TenantManifest,
        TenantFailure,
        _inventory,
        _spool,
        MigrationCapacityError,
        MigrationDiskCapacityError,
        TenantInputError,
    )

    count, allowance, width, parser_workers, shared_workers = _pipeline_limits(
        resources,
        tenants,
        preview,
    )
    pending = []
    tasks = set()
    iterator = iter(tenants)
    live = {}
    async with MigrationIO(resources["io_workers"]) as io:
        async with MigrationResources(
            workers=shared_workers,
            io=io,
            memory_bytes=allowance * shared_workers,
        ) as shared:
            parser = {
                **resources,
                "workers": parser_workers,
                "memory_bytes": allowance * parser_workers,
                "_shared_io": io,
                "_shared_resources": shared,
            }

            async def read(tenant):
                spool = _spool(
                    base,
                    data.data,
                    allowance * parser_workers,
                    parser_workers,
                )
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
                workspaces = result.get("workspaces")
                if isinstance(workspaces, WorkspaceRecords):
                    workspaces.clear_cache()
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
                    if count > 1 and not preview:
                        fill()
                    # Pending readers retain one allowance each, including
                    # completed spools. The owner borrows the remainder.
                    owner_workers = max(1, count - len(pending))
                    local_owner = _owner_resources(
                        resources,
                        io,
                        allowance,
                        owner_workers,
                    )
                    try:
                        yield tenant, {
                            **local_owner,
                            "_prefetched": inventory,
                            "_pipeline_health": health,
                        }, error
                    finally:
                        live.pop(id(tenant)).__exit__(None, None, None)
                        tasks.discard(task)
                    if count == 1 or preview:
                        fill()

            stream = results()
            try:
                yield stream
            finally:
                await _close_pipeline(stream, tasks, live)
