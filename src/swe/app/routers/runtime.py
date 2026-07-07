# -*- coding: utf-8 -*-
"""Runtime diagnostic HTTP endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from swe.app.runtime_diagnostic import RuntimeDiagnosticManager

router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/memory-diagnostic")
def get_memory_diagnostic(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    collect_gc: bool = Query(True),
) -> dict[str, object]:
    """Return an on-demand process memory diagnostic snapshot."""
    manager = getattr(
        request.app.state,
        "runtime_diagnostic_manager",
        None,
    )
    if not isinstance(manager, RuntimeDiagnosticManager):
        raise HTTPException(
            status_code=503,
            detail="Runtime diagnostic manager is unavailable",
        )
    return manager.collect_memory_diagnostic(
        limit=limit,
        collect_gc=collect_gc,
    )
