# -*- coding: utf-8 -*-
"""Bounded independent workspace parsing into disposable inventory records."""

from collections import Counter
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path

from .inventory_v3 import inventory_workspace
from .freshness import changed_source, tenant_key
from .in_place_source import shared_service_roots
from .parallel import MigrationCoordinator, MigrationResources
from .progress import current_progress


@dataclass(frozen=True)
class WorkspaceInventory:
    index: int
    record: object
    scope: tuple
    position: str
    sessions: int
    chats: int
    files: int
    blockers: tuple


async def spool_workspaces(
    data,
    spool,
    *,
    workers=4,
    io_workers=4,
    memory_bytes=512 * 1024 * 1024,
    shared_resources=None,
):
    """Parse and spool with fixed fan-out and no retained conversation bodies."""
    if not 1 <= workers <= 32:
        raise ValueError("workers must be between 1 and 32")
    summaries = [None] * len(data["workspaces"])
    progress = current_progress()
    if progress and shared_resources is None:
        # These counters describe this inventory pass, including source rechecks.
        progress.data.update(
            inventory_completed_workspaces=0,
            inventoried_sessions=0,
            inventoried_chats=0,
            inventoried_source_bytes=0,
            inventory_blocker_count=0,
        )
    async with AsyncExitStack() as stack:
        if shared_resources is None:
            shared_resources = await stack.enter_async_context(
                MigrationResources(
                    workers=workers,
                    io_workers=io_workers,
                    memory_bytes=memory_bytes,
                ),
            )
        io = shared_resources.io
        data = {
            **data,
            "_freshness_cache": await io.call(_shared_freshness, data),
        }

        async def parse(index, _request):
            async with shared_resources.reserve():
                result = await io.call(inventory_workspace, data, index)
                record = await io.call(spool.write, index, result)
                workspace = result["workspaces"][0]
                source_bytes = sum(
                    item.get("bytes", 0) for item in result["files"]
                )
                summaries[index] = WorkspaceInventory(
                    index=index,
                    record=record,
                    scope=tuple(workspace["scope"]),
                    position=workspace["position"],
                    sessions=len(workspace["sessions"]),
                    chats=len(workspace["chats"]),
                    files=len(result["files"]),
                    blockers=tuple(result["blockers"]),
                )
                if progress:
                    summary = summaries[index]
                    progress.data["inventory_completed_workspaces"] += 1
                    progress.data["inventoried_sessions"] += summary.sessions
                    progress.data["inventoried_chats"] += summary.chats
                    progress.data["inventoried_source_bytes"] += source_bytes
                    progress.data["inventory_blocker_count"] += len(
                        summary.blockers,
                    )

        await MigrationCoordinator(
            {},
            workers=min(workers, shared_resources.workers),
        ).run(
            range(len(summaries)),
            parse,
        )
    positions = Counter(item.position for item in summaries)
    if any(count != 1 for count in positions.values()):
        raise ValueError("duplicate workspace inventory position")
    return summaries


def _shared_freshness(data):
    """Scan shared evidence parents once per inventory, never across runs."""
    references = Counter()
    shared = shared_service_roots(data)
    for workspace in data["workspaces"]:
        cutoff = data.get("tenant_sync_started_at_ns", {}).get(
            (
                tenant_key(
                    workspace["service_unit_id"],
                    workspace["tenant_id"],
                    workspace["source_id"],
                )
                if data.get("source_isolation")
                else tenant_key(
                    workspace["service_unit_id"],
                    workspace["tenant_id"],
                )
            ),
        )
        if cutoff is not None:
            references.update(
                (str(Path(value).parent), cutoff)
                for value in workspace.get("evidence_refs", [])
                if str(Path(value).parent) not in shared
            )
    return {
        key: changed_source([key[0]], key[1], recursive=False)
        for key, count in references.items()
        if count > 1
    }
