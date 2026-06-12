# -*- coding: utf-8 -*-
"""Workspace API – download / upload the entire WORKING_DIR as a zip,
and broadcast workspace files to selected tenants."""

from __future__ import annotations

import asyncio
import io
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from .skills import BroadcastTenantListResponse
from ..agent_context import get_current_agent_id
from ...config.context import resolve_scope_preferred_tenant_id
from ...config.utils import (
    get_tenant_working_dir_strict,
    list_logical_tenant_ids,
)

from ..workspace.file_broadcast import (
    BROADCASTABLE_FILES,
    BroadcastFilesResponse,
    FileBroadcastService,
)

router = APIRouter(prefix="/workspace", tags=["workspace"])


class BroadcastFilesRequest(BaseModel):
    file_names: list[str] = Field(default_factory=list)
    target_tenant_ids: list[str] = Field(default_factory=list)
    overwrite: bool = False


def _zip_directory(root: Path) -> io.BytesIO:
    """Create an in-memory zip archive of *root* and return the buffer.

    All files **and** directories (including empty ones) are included.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in sorted(root.rglob("*")):
            arcname = entry.relative_to(root).as_posix()
            if entry.is_file():
                zf.write(entry, arcname)
            elif entry.is_dir():
                # Zip spec: directory entries end with '/'
                zf.write(entry, arcname + "/")
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_zip_data(data: bytes, workspace_dir: Path) -> None:
    """Ensure *data* is a valid zip without path-traversal entries."""
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a valid zip archive",
        )
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            resolved = (workspace_dir / name).resolve()
            if not str(resolved).startswith(str(workspace_dir)):
                raise HTTPException(
                    status_code=400,
                    detail=f"Zip contains unsafe path: {name}",
                )


def _extract_and_merge_zip(data: bytes, workspace_dir: Path) -> None:
    """Extract zip data and merge into workspace_dir (blocking operation)."""
    tmp_dir = None
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="swe_upload_"))
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(tmp_dir)

        top_entries = list(tmp_dir.iterdir())
        extract_root = tmp_dir
        if len(top_entries) == 1 and top_entries[0].is_dir():
            extract_root = top_entries[0]

        workspace_dir.mkdir(parents=True, exist_ok=True)

        for item in extract_root.iterdir():
            dest = workspace_dir / item.name
            if item.is_file():
                shutil.copy2(item, dest)
            else:
                if dest.exists() and dest.is_file():
                    dest.unlink()
                shutil.copytree(item, dest, dirs_exist_ok=True)
    finally:
        if tmp_dir and tmp_dir.is_dir():
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _validate_and_extract_zip(data: bytes, workspace_dir: Path) -> None:
    """Validate and extract zip data (blocking operation)."""
    _validate_zip_data(data, workspace_dir)
    _extract_and_merge_zip(data, workspace_dir)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/download",
    summary="Download workspace as zip",
    description=(
        "Package the current tenant workspace into a zip archive and stream "
        "it back as a downloadable file."
    ),
    responses={
        200: {
            "content": {"application/zip": {}},
            "description": "Zip archive of tenant workspace",
        },
    },
)
async def download_workspace(request: Request):
    """Stream tenant workspace as a zip file."""
    # Get tenant workspace from request state (set by TenantWorkspaceMiddleware)
    workspace = getattr(request.state, "workspace", None)
    if workspace is None:
        raise HTTPException(
            status_code=503,
            detail="Tenant workspace not available",
        )

    workspace_dir = workspace.workspace_dir

    if not workspace_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"Workspace does not exist: {workspace_dir}",
        )

    buf = await asyncio.to_thread(_zip_directory, workspace_dir)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tenant_id = getattr(request.state, "tenant_id", "default")
    filename = f"swe_workspace_{tenant_id}_{timestamp}.zip"

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post(
    "/upload",
    response_model=dict,
    summary="Upload zip and merge into workspace",
    description=(
        "Upload a zip archive.  Paths present in the zip are merged into "
        "tenant workspace (files overwritten, dirs merged).  Paths not in "
        "the zip are left unchanged. Download packs the entire workspace; "
        "upload only overwrites/merges zip contents."
    ),
)
async def upload_workspace(
    request: Request,
    file: UploadFile = File(
        ...,
        description="Zip archive to merge into tenant workspace",
    ),
) -> dict:
    """
    Merge uploaded zip contents into tenant workspace (overwrite, not clear).
    """
    # Get tenant workspace from request state (set by TenantWorkspaceMiddleware)
    workspace = getattr(request.state, "workspace", None)
    if workspace is None:
        raise HTTPException(
            status_code=503,
            detail="Tenant workspace not available",
        )

    if file.content_type and file.content_type not in (
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Expected a zip file, got content-type: {file.content_type}"
            ),
        )

    workspace_dir = workspace.workspace_dir
    data = await file.read()

    try:
        await asyncio.to_thread(_validate_and_extract_zip, data, workspace_dir)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to merge workspace: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Broadcast endpoints
# ---------------------------------------------------------------------------


# @router.get(
#     "/broadcast/tenants",
#     response_model=dict[str, Any],
#     summary="List tenants available for file broadcast",
# )
# async def list_workspace_broadcast_tenants(
#     request: Request,
# ) -> dict[str, Any]:
#     """Return tenant IDs that can receive broadcast files."""
#     from ...config.utils import list_logical_tenant_ids
#
#     source_id = getattr(request.state, "source_id", None)
#     tenant_ids = await list_logical_tenant_ids(
#         source_id,
#         source_filter=True,
#     )
#     return {"tenant_ids": tenant_ids}


@router.get(
    "/broadcast/tenants",
    response_model=BroadcastTenantListResponse,
)
async def list_broadcast_tenants(
    request: Request,
) -> BroadcastTenantListResponse:
    return BroadcastTenantListResponse(
        tenant_ids=await list_logical_tenant_ids(
            getattr(request.state, "source_id", None),
            source_filter=True,
            include_templates=True,
        ),
    )


@router.post(
    "/broadcast/files",
    response_model=BroadcastFilesResponse,
    summary="Broadcast workspace files to selected tenants",
)
async def broadcast_workspace_files(
    request: Request,
    body: BroadcastFilesRequest,
) -> BroadcastFilesResponse:
    """Copy selected workspace MD files to target tenants' default workspace."""
    if not body.overwrite:
        raise HTTPException(
            status_code=400,
            detail="overwrite=true is required for file broadcast",
        )
    if not body.target_tenant_ids:
        raise HTTPException(
            status_code=400,
            detail="No target tenant IDs provided",
        )
    if not body.file_names:
        raise HTTPException(
            status_code=400,
            detail="No file names provided",
        )

    invalid_names = [
        n for n in body.file_names if n not in BROADCASTABLE_FILES
    ]
    if invalid_names:
        raise HTTPException(
            status_code=400,
            detail=f"Files not broadcastable: {', '.join(invalid_names)}",
        )

    # Resolve tenant working dir the same way as skill broadcast:
    # use effective_tenant_id (handles source_id → default_{source_id})
    # and get_tenant_working_dir_strict to get the tenant root.
    tenant_id = str(getattr(request.state, "tenant_id", None) or "default")
    raw_source_id = getattr(request.state, "source_id", None)
    source_id = str(raw_source_id) if raw_source_id else None
    effective_tenant_id = resolve_scope_preferred_tenant_id(
        tenant_id,
        source_id,
        getattr(request.state, "scope_id", None),
    )
    source_working_dir = get_tenant_working_dir_strict(effective_tenant_id)

    # MD files live in the default agent workspace, not the tenant root.
    default_ws_dir = source_working_dir / "workspaces" / get_current_agent_id()

    # Verify source files exist before starting broadcast
    for name in body.file_names:
        if not (default_ws_dir / name).exists():
            raise HTTPException(
                status_code=400,
                detail=f"Source file not found: {name}",
            )

    service = FileBroadcastService(
        default_ws_dir,
        source_id=source_id,
    )
    return await service.broadcast(
        file_names=body.file_names,
        target_tenant_ids=body.target_tenant_ids,
        overwrite=body.overwrite,
    )
