# -*- coding: utf-8 -*-
"""Broadcast workspace MD files to selected tenants.

Provides a service class that copies template files (AGENTS.md, SOUL.md, etc.)
from a source tenant's workspace to one or more target tenants, creating the
target tenant directory structure on demand via ``TenantInitializer``.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from pydantic import BaseModel, Field

from .tenant_initializer import TenantInitializer
from ..agent_context import get_current_agent_id

logger = logging.getLogger(__name__)

# Only these files may be broadcast — prevents accidental spread of daily
# memories, session data, or other workspace artefacts.
BROADCASTABLE_FILES = (
    "AGENTS.md",
    "BOOTSTRAP.md",
    "HEARTBEAT.md",
    "MEMORY.md",
    "PROFILE.md",
    "SOUL.md",
)


# ---------------------------------------------------------------------------
# Public data models
# ---------------------------------------------------------------------------


class BroadcastFileTenantResult(BaseModel):
    tenant_id: str
    success: bool
    bootstrapped: bool = False
    files_updated: list[str] = Field(default_factory=list)
    error: str = ""


class BroadcastFilesResponse(BaseModel):
    results: list[BroadcastFileTenantResult] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FileBroadcastService:
    """Copy workspace MD files from a source tenant to target tenants."""

    def __init__(
        self,
        source_workspace_dir: Path,
        *,
        source_id: str | None = None,
        tenant_workspace_pool: object,
    ):
        """
        Args:
            source_workspace_dir: Absolute path to the source workspace
                directory, e.g. ``~/.swe/default/workspaces/default``.
            source_id: Optional ``X-Source-Id`` header value used to resolve
                the correct default template for target tenants.
        """
        self.source_workspace_dir = Path(source_workspace_dir)
        # ~/.swe/<tenant>/workspaces/default → ~/.swe
        self.base_working_dir = self.source_workspace_dir.parent.parent.parent
        self.source_id = source_id
        self._tenant_workspace_pool = tenant_workspace_pool

    # -- public API ---------------------------------------------------------

    async def broadcast(
        self,
        *,
        file_names: list[str],
        target_tenant_ids: list[str],
        overwrite: bool = False,
    ) -> BroadcastFilesResponse:
        """Broadcast *file_names* to every tenant in *target_tenant_ids*.

        Each tenant is processed independently — a failure for one tenant does
        not block the others.  Results are aggregated into a single response.
        """
        results: list[BroadcastFileTenantResult] = []
        for tenant_id in target_tenant_ids:
            try:
                validated = self._validate_tenant_id(tenant_id)
                initializer = TenantInitializer(
                    self.base_working_dir,
                    validated,
                    source_id=self.source_id,
                )
                was_bootstrapped = initializer.has_seeded_bootstrap()
                if not was_bootstrapped:
                    await self._tenant_workspace_pool.ensure_bootstrap(
                        validated,
                        source_id=self.source_id,
                    )
                result = await asyncio.to_thread(
                    self._copy_to_tenant,
                    target_tenant_id=validated,
                    file_names=file_names,
                    overwrite=overwrite,
                    was_bootstrapped=was_bootstrapped,
                )
                results.append(result)
            except Exception as exc:
                logger.warning(
                    "File broadcast to tenant %s failed: %s",
                    tenant_id,
                    exc,
                )
                results.append(
                    BroadcastFileTenantResult(
                        tenant_id=str(tenant_id),
                        success=False,
                        error=str(exc),
                    ),
                )
        return BroadcastFilesResponse(results=results)

    # -- internal -----------------------------------------------------------

    @staticmethod
    def _validate_tenant_id(tenant_id: str) -> str:
        tenant_id = str(tenant_id or "").strip()
        if not tenant_id:
            raise ValueError("tenant_id is required")
        if len(tenant_id) > 256:
            raise ValueError(f"Invalid tenant ID format: {tenant_id}")
        if ".." in tenant_id or "/" in tenant_id or "\\" in tenant_id:
            raise ValueError(f"Invalid tenant ID format: {tenant_id}")
        if any(ord(c) < 32 for c in tenant_id):
            raise ValueError(f"Invalid tenant ID format: {tenant_id}")
        return tenant_id

    def _copy_to_tenant(
        self,
        *,
        target_tenant_id: str,
        file_names: list[str],
        overwrite: bool,
        was_bootstrapped: bool,
    ) -> BroadcastFileTenantResult:
        """Blocking: copy files from source to a single target tenant."""
        initializer = TenantInitializer(
            self.base_working_dir,
            target_tenant_id,
            source_id=self.source_id,
        )
        target_ws = (
            initializer.tenant_dir / "workspaces" / get_current_agent_id()
        )

        updated: list[str] = []
        for name in file_names:
            src = self.source_workspace_dir / name
            if not src.exists():
                continue
            dst = target_ws / name
            if not overwrite and dst.exists():
                continue
            target_ws.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            updated.append(name)
            logger.debug("Broadcast %s → %s", name, target_tenant_id)

        return BroadcastFileTenantResult(
            tenant_id=target_tenant_id,
            success=True,
            bootstrapped=not was_bootstrapped,
            files_updated=updated,
        )
