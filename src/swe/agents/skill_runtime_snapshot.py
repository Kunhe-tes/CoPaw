# -*- coding: utf-8 -*-
"""Process-local, immutable snapshots for workspace skill resolution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from pathlib import Path
from threading import RLock
from types import MappingProxyType
from typing import Any, Mapping

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ManifestStat:
    mtime_ns: int
    size: int
    inode: int


@dataclass(frozen=True)
class SkillRuntimeSnapshot:
    directory: Path
    metadata: Mapping[str, Any]
    content_signature: str
    freshness_token: str
    runtime_profile: Any
    config: Mapping[str, Any]
    requirements: Mapping[str, Any]
    channels: tuple[str, ...]


@dataclass(frozen=True)
class WorkspaceSkillSnapshot:
    workspace_dir: Path
    generation: int
    manifest_stat: ManifestStat
    skills: Mapping[str, SkillRuntimeSnapshot]


_LOCK = RLock()
_CACHE: dict[Path, WorkspaceSkillSnapshot] = {}
_GENERATION = 0


def _stat(path: Path) -> ManifestStat:
    try:
        value = path.stat()
    except OSError:
        return ManifestStat(0, 0, 0)
    return ManifestStat(value.st_mtime_ns, value.st_size, value.st_ino)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _freeze(item) for key, item in value.items()},
        )
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _fresh(snapshot: WorkspaceSkillSnapshot, manifest_path: Path) -> bool:
    if snapshot.manifest_stat != _stat(manifest_path):
        return False
    from .skills_manager import get_skill_freshness_token

    return all(
        get_skill_freshness_token(skill.directory) == skill.freshness_token
        for skill in snapshot.skills.values()
    )


def get_workspace_skill_snapshot(
    workspace_dir: Path,
    *,
    reconcile: bool = True,
) -> WorkspaceSkillSnapshot:
    """Return a cached workspace snapshot, reconciling only on invalidation."""
    global _GENERATION
    workspace_dir = workspace_dir.expanduser().resolve()
    from .skills_manager import (
        _build_signature,
        _build_skill_metadata,
        get_workspace_skill_manifest_path,
        get_skill_freshness_token,
        read_skill_manifest,
        resolve_workspace_managed_skill_dir,
    )

    manifest_path = get_workspace_skill_manifest_path(workspace_dir)
    with _LOCK:
        previous = _CACHE.get(workspace_dir)
        if previous is not None and _fresh(previous, manifest_path):
            return previous
        manifest = read_skill_manifest(workspace_dir, reconcile=reconcile)
        entries = manifest.get("skills", {})
        skills: dict[str, SkillRuntimeSnapshot] = {}
        for name, entry in sorted(entries.items()):
            if not isinstance(entry, dict) or not entry.get("enabled", False):
                continue
            try:
                directory = resolve_workspace_managed_skill_dir(
                    workspace_dir,
                    name,
                    enabled=True,
                )
                if not directory.is_dir():
                    continue
                signature = _build_signature(directory)
                freshness = get_skill_freshness_token(directory)
                metadata = entry.get("metadata")
                if not isinstance(metadata, dict) or not metadata.get(
                    "description",
                ):
                    metadata = _build_skill_metadata(
                        name,
                        directory,
                        source=str(entry.get("source", "customized")),
                        compute_signature=False,
                    )
                from .skill_runtime_profile import build_skill_runtime_profile

                skills[name] = SkillRuntimeSnapshot(
                    directory=directory.resolve(),
                    metadata=_freeze(dict(metadata)),
                    content_signature=signature,
                    freshness_token=freshness,
                    runtime_profile=build_skill_runtime_profile(
                        directory.resolve(),
                        name,
                    ),
                    config=_freeze(dict(entry.get("config") or {})),
                    requirements=_freeze(
                        dict(entry.get("requirements") or {}),
                    ),
                    channels=tuple(entry.get("channels") or ("all",)),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Workspace skill '%s' excluded from snapshot: %s",
                    name,
                    exc,
                )
        _GENERATION += 1
        snapshot = WorkspaceSkillSnapshot(
            workspace_dir=workspace_dir,
            generation=_GENERATION,
            manifest_stat=_stat(manifest_path),
            skills=MappingProxyType(skills),
        )
        _CACHE[workspace_dir] = snapshot
        return snapshot


def invalidate_workspace_skill_snapshot(workspace_dir: Path) -> None:
    with _LOCK:
        _CACHE.pop(workspace_dir.expanduser().resolve(), None)


async def get_workspace_skill_snapshot_async(
    workspace_dir: Path,
    *,
    reconcile: bool = True,
) -> WorkspaceSkillSnapshot:
    """Build or fetch a snapshot without blocking the event loop."""
    return await asyncio.to_thread(
        get_workspace_skill_snapshot,
        workspace_dir,
        reconcile=reconcile,
    )
