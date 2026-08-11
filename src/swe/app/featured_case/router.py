# -*- coding: utf-8 -*-
"""Featured case API router (simplified - no case_id)."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from .models import (
    FeaturedCaseCreate,
    FeaturedCaseListResponse,
    FeaturedCaseReorderRequest,
    FeaturedCaseUpdate,
)
from .service import FeaturedCaseService
from .store import FeaturedCaseStore, normalize_featured_case_bbk_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/featured-cases", tags=["featured-cases"])

# Global instances
_store: Optional[FeaturedCaseStore] = None
_service: Optional[FeaturedCaseService] = None


def init_featured_case_module(db=None) -> None:
    """Initialize featured case module.

    Args:
        db: Database connection (TDSQLConnection)

    Raises:
        RuntimeError: If database is not connected
    """
    global _store, _service

    if db is None or not getattr(db, "is_connected", False):
        raise RuntimeError(
            "Featured case module requires a connected database.",
        )

    _store = FeaturedCaseStore(db)
    _service = FeaturedCaseService(_store)
    logger.info("Featured case module initialized")


def get_service() -> FeaturedCaseService:
    """Get featured case service.

    Returns:
        FeaturedCaseService instance

    Raises:
        RuntimeError: If module not initialized
    """
    global _service
    if _service is None:
        raise RuntimeError("Featured case module not initialized")
    return _service


def _require_source_id(request: Request) -> str:
    """Return the request source or raise a management validation error."""
    source_id = request.headers.get("X-Source-Id")
    if not source_id:
        raise HTTPException(
            status_code=400,
            detail="X-Source-Id header required",
        )
    return source_id


def _request_bbk_scope(request: Request) -> str:
    """Return the caller's canonical writable BBK scope."""
    return normalize_featured_case_bbk_id(
        request.headers.get("X-Bbk-Id"),
    )


# ==================== Client endpoints (for frontend display) ====================


@router.get(
    "",
    summary="Get cases for current context",
    description="Returns cases matched by X-Source-Id and X-Bbk-Id headers",
)
async def list_cases_for_display(request: Request) -> list[dict]:
    """Get cases for display.

    Headers:
        X-Source-Id: Source ID (required)
        X-Bbk-Id: BBK ID (optional)
    """
    source_id = request.headers.get("X-Source-Id")
    bbk_id = request.headers.get("X-Bbk-Id")

    if not source_id:
        return []

    service = get_service()
    return await service.get_cases_for_dimension(source_id, bbk_id)


@router.get(
    "/{case_id}",
    summary="Get case detail",
)
async def get_case_detail(case_id: int) -> dict:
    """Get case detail by id."""
    service = get_service()
    case = await service.get_case_by_id(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case.model_dump()


# ==================== Admin endpoints ====================


@router.get(
    "/admin/cases",
    response_model=FeaturedCaseListResponse,
    summary="List all cases (admin)",
)
async def list_all_cases(
    request: Request,
    bbk_id: Optional[str] = Query(None, description="Filter by BBK ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> FeaturedCaseListResponse:
    """List all cases for the current source_id context.

    Headers:
        X-Source-Id: Source ID (required, used as filter)
        X-Bbk-Id: BBK ID (optional, used when query param not provided)
    """
    source_id = request.headers.get("X-Source-Id")
    if not source_id:
        raise HTTPException(
            status_code=400,
            detail="X-Source-Id header required",
        )

    # Management queries are exact-scope. Explicit bbk_id enables the
    # read-only head-office tab in branch contexts.
    effective_bbk_id = normalize_featured_case_bbk_id(
        bbk_id if bbk_id is not None else request.headers.get("X-Bbk-Id"),
    )

    service = get_service()
    cases, total = await service.list_cases(
        source_id=source_id,
        bbk_id=effective_bbk_id,
        page=page,
        page_size=page_size,
    )
    return FeaturedCaseListResponse(cases=cases, total=total)


@router.post(
    "/admin/cases",
    summary="Create case (admin)",
)
async def create_case(request: Request, case: FeaturedCaseCreate) -> dict:
    """Create case definition.

    source_id comes from X-Source-Id header (not from request body).
    """
    source_id = _require_source_id(request)
    bbk_id = _request_bbk_scope(request)
    service = get_service()
    created = await service.create_case(source_id, bbk_id, case)
    return {"success": True, "data": created.model_dump()}


@router.put(
    "/admin/cases/{case_id}",
    summary="Update case (admin)",
)
async def update_case(
    request: Request,
    case_id: int,
    updates: FeaturedCaseUpdate,
) -> dict:
    """Update case definition."""
    service = get_service()
    try:
        updated = await service.update_case(
            case_id,
            _require_source_id(request),
            _request_bbk_scope(request),
            updates,
        )
        return {"success": True, "data": updated.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put(
    "/admin/cases/{case_id}/order",
    summary="Reorder case (admin)",
)
async def reorder_case(
    request: Request,
    case_id: int,
    reorder: FeaturedCaseReorderRequest,
) -> dict:
    """Atomically move a case within the caller's exact BBK scope."""
    service = get_service()
    try:
        result = await service.reorder_case(
            case_id,
            _require_source_id(request),
            _request_bbk_scope(request),
            reorder.sort_order,
        )
        return {"success": True, "data": result.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete(
    "/admin/cases/{case_id}",
    summary="Delete case (admin)",
)
async def delete_case(request: Request, case_id: int) -> dict:
    """Delete case definition."""
    service = get_service()
    try:
        await service.delete_case(
            case_id,
            _require_source_id(request),
            _request_bbk_scope(request),
        )
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
