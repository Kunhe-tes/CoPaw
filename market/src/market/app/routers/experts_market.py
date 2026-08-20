# -*- coding: utf-8 -*-
"""Expert Community admin routes."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Header, HTTPException, Request, status

from ...marketplace.schemas import (
    MarketExpertDetail,
    MarketExpertResponse,
    PublishExpertRequest,
)
from ...marketplace.service import ExpertDependencyError, ExpertNameConflictError
from ..deps import require_source_id

router = APIRouter()


def _require_manager(x_manager: Optional[str]) -> None:
    if x_manager != "true":
        raise HTTPException(status_code=403, detail="Manager access required")


@router.post(
    "/market/experts",
    response_model=MarketExpertResponse,
    status_code=status.HTTP_201_CREATED,
)
async def publish_expert(
    req: PublishExpertRequest,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
):
    """Publish a community expert."""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace
    try:
        item, version_unchanged = await svc.publish_expert(
            source_id,
            Path(req.source_dir),
            overwrite=req.overwrite,
            operator_id="manager",
            operator_name="Manager",
        )
    except ExpertNameConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "existing_item_id": exc.existing_item_id,
                "existing_name": exc.existing_name,
                "existing_creator_id": exc.existing_creator_id,
                "existing_creator_name": exc.existing_creator_name,
                "existing_version": exc.existing_version,
            },
        ) from exc
    except ExpertDependencyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MarketExpertResponse(
        item_id=item.item_id,
        name=item.name,
        description=item.description,
        version=item.version,
        creator_id=item.creator_id,
        creator_name=item.creator_name,
        category_id=item.category_id,
        bbk_ids=item.bbk_ids,
        status=item.status,
        created_at=item.created_at,
        updated_at=item.updated_at,
        version_unchanged=version_unchanged,
    )


@router.post(
    "/market/experts/{item_id}/versions/{version_id}/restore",
    response_model=MarketExpertDetail,
)
async def restore_expert_version(
    item_id: str,
    version_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
):
    """Restore a historical expert version."""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace
    item = await svc.restore_expert_version(
        source_id,
        item_id,
        version_id,
        operator_id="manager",
        operator_name="Manager",
    )
    detail = await svc.get_expert_detail(source_id, item_id, "100")
    if detail is None:
        raise HTTPException(status_code=404, detail="Expert not found")
    return MarketExpertDetail.model_validate(
        detail,
        from_attributes=True,
    ).model_copy(update={"version": item.version})


@router.delete("/market/experts/{item_id}")
async def unpublish_expert(
    item_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
):
    """Unpublish a community expert."""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace
    success = await svc.unpublish_expert(
        source_id,
        item_id,
        operator_id="manager",
        operator_name="Manager",
    )
    if not success:
        raise HTTPException(status_code=404, detail="Expert not found")
    return {"success": True}
