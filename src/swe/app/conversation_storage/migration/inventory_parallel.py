# -*- coding: utf-8 -*-
"""Bounded independent workspace parsing into disposable inventory records."""

from collections import Counter
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path

from ..bundle import MAX_READ_BYTES
from .inventory_v3 import inventory_workspace
from .freshness import changed_source, tenant_key
from .in_place_source import shared_service_roots
from .parallel import MigrationCoordinator, MigrationResources
from .progress import current_progress
from .source_inputs import (
    SourceInputInvalid,
    safe_input_entries,
    session_input_roots,
)
from .spool import MigrationCapacityError


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
    """Parse and spool with fixed fan-out and no retained conversation bodies.

    Each parser gets one equal share of the memory budget. The old reader still
    needs a separate preflight size check before this API is used by the CLI.
    """
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
            async with shared_resources.reserve() as allowance:
                source_bytes = 0
                if data.get("source_binding_storage") != "manifest-v1":
                    source_bytes = await io.call(
                        _preflight_workspace,
                        data["workspaces"][index],
                        allowance,
                    )
                result = await io.call(inventory_workspace, data, index)
                record = await io.call(spool.write, index, result)
                workspace = result["workspaces"][0]
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
    """Scan shared evidence parents once per inventory, never across runs.

    Whole-source fingerprints still bracket the inventory. Unique workspace
    paths retain their own checks, including the workspace directory mtime.
    """
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


def _preflight_workspace(workspace, allowance, *, require_readonly=False):
    """Bound raw inputs before legacy parsers allocate decoded object graphs."""
    root = Path(workspace["root"])
    total = 0
    count = 0
    source_limit = allowance // 16
    count_limit = allowance // 512
    roots = session_input_roots(
        root,
        [entry["path"] for entry in workspace.get("session_paths", [])],
        registry_path=workspace.get("registry_path", "chats.json"),
        sessions_dir=workspace.get("sessions_dir", "sessions"),
        dialog_dir=workspace.get("dialog_dir", "dialog"),
        max_session_bytes=min(MAX_READ_BYTES, source_limit),
    )
    for path in safe_input_entries(
        root,
        roots,
        entry_limit=count_limit,
        max_file_bytes=MAX_READ_BYTES,
        max_total_file_bytes=source_limit,
    ):
        if not path.is_file():
            if (
                require_readonly
                and path != root
                and path.stat().st_mode & 0o222
            ):
                raise SourceInputInvalid(
                    "conversation input directories must be read-only",
                )
            continue
        if require_readonly and path.stat().st_mode & 0o222:
            raise SourceInputInvalid(
                "conversation input files must be read-only",
            )
        size = path.stat().st_size
        if size > MAX_READ_BYTES:
            raise MigrationCapacityError(
                "workspace source file exceeds the bounded reader limit: "
                + str(path),
            )
        total += size
        count += 1
        if total > source_limit or count > count_limit:
            raise MigrationCapacityError(
                "workspace source exceeds its migration memory allowance",
            )
    return total
