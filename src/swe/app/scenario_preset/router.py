# -*- coding: utf-8 -*-
"""HTTP endpoints for source-owned scenario preset catalogs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from .models import (
    CatalogNodeCreate,
    CatalogNodeMove,
    CatalogNodeReorder,
    CatalogNodeUpdate,
    ScenarioBindingsUpdate,
)
from .service import ScenarioPresetCatalogService
from .store import ScenarioPresetStore

router = APIRouter(prefix="/scenario-presets", tags=["scenario-presets"])
_service: ScenarioPresetCatalogService | None = None


async def init_scenario_preset_module(db) -> None:
    """Initialize persistent scenario catalog storage at application startup."""
    global _service
    store = ScenarioPresetStore(db)
    await store.initialize()
    _service = ScenarioPresetCatalogService(store)


def get_service() -> ScenarioPresetCatalogService:
    """Return initialized catalog service or a clear temporary-unavailable error."""
    if _service is None:
        raise HTTPException(
            status_code=503,
            detail="Scenario preset service unavailable",
        )
    return _service


@router.get("/catalog")
async def get_effective_catalog(request: Request) -> dict:
    """Read the current Source's selectable, complete enabled catalog tree."""
    source_id = _require_source(request)
    catalog = await get_service().get_effective_catalog(source_id)
    return catalog.model_dump()


@router.get("/admin/catalog")
async def get_admin_catalog(request: Request) -> dict:
    """Read the complete catalog tree for administration, including disabled nodes."""
    _require_manager(request)
    source_id = _require_source(request)
    nodes = await get_service().store.list_nodes(source_id)
    return {"nodes": [node.model_dump() for node in nodes]}


@router.post("/admin/nodes")
async def create_node(request: Request, payload: CatalogNodeCreate) -> dict:
    """Append an administrator-created Source catalog node."""
    _require_manager(request)
    try:
        node = await get_service().create_node(
            _require_source(request),
            payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return node.model_dump()


@router.patch("/admin/nodes/{node_id}")
async def update_node(
    node_id: str,
    request: Request,
    payload: CatalogNodeUpdate,
) -> dict:
    """Change name, state, or scenario prompt draft without changing identity."""
    _require_manager(request)
    try:
        node = await get_service().update_node(
            _require_source(request),
            node_id,
            payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return node.model_dump()


@router.post("/admin/nodes/{node_id}/move")
async def move_node(
    node_id: str,
    request: Request,
    payload: CatalogNodeMove,
) -> dict:
    """Move a capability or scenario into a compatible parent."""
    _require_manager(request)
    try:
        node = await get_service().move_node(
            _require_source(request),
            node_id,
            payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return node.model_dump()


@router.post("/admin/nodes/{node_id}/reorder")
async def reorder_node(
    node_id: str,
    request: Request,
    payload: CatalogNodeReorder,
) -> dict:
    """Move one node to an absolute sibling position."""
    _require_manager(request)
    try:
        node = await get_service().reorder_node(
            _require_source(request),
            node_id,
            payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return node.model_dump()


@router.delete("/admin/nodes/{node_id}", status_code=204)
async def delete_node(node_id: str, request: Request) -> None:
    """Delete only a leaf node in the current Source."""
    _require_manager(request)
    try:
        await get_service().delete_node(_require_source(request), node_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/admin/scenarios/{scenario_id}/bindings")
async def get_bindings(scenario_id: str, request: Request) -> dict:
    """Return a scenario's stable market resource bindings."""
    _require_manager(request)
    try:
        bindings = await get_service().get_bindings(
            _require_source(request),
            scenario_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"bindings": [binding.model_dump() for binding in bindings]}


@router.put("/admin/scenarios/{scenario_id}/bindings", status_code=204)
async def replace_bindings(
    scenario_id: str,
    request: Request,
    payload: ScenarioBindingsUpdate,
) -> None:
    """Replace resource IDs; neither request nor storage accepts credentials."""
    _require_manager(request)
    try:
        await get_service().replace_bindings(
            _require_source(request),
            scenario_id,
            payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _require_source(request: Request) -> str:
    source_id = getattr(
        request.state,
        "source_id",
        None,
    ) or request.headers.get("X-Source-Id", "")
    source_id = source_id.strip() if isinstance(source_id, str) else ""
    if not source_id:
        raise HTTPException(status_code=400, detail="Source context missing")
    return source_id


def _require_manager(request: Request) -> None:
    role = request.headers.get("X-User-Role", "").strip().lower()
    if role not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Manager role required")
