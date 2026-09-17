# -*- coding: utf-8 -*-
"""Gateway-facing Monitor APIs for external consumers.

Authentication and source ownership are validated by the API Gateway. Every
source-scoped endpoint in this router must still require the Gateway-provided
source scope before reading Monitor data.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from ..models.cron import LatestExecutionSubtaskCountResponse
from ..services.cron import QueryService, get_query_service

router = APIRouter(prefix="/monitor/external", tags=["external"])


def require_external_source_id(request: Request) -> str:
    """Return the non-empty source scope supplied by the API Gateway."""
    source_id = str(request.headers.get("X-Source-Id") or "").strip()
    if not source_id:
        raise HTTPException(
            status_code=400,
            detail="X-Source-Id header is required",
        )
    return source_id


@router.get(
    "/cron/jobs/{job_id}/latest-execution/subtask-count",
    response_model=LatestExecutionSubtaskCountResponse,
    responses={
        400: {"description": "X-Source-Id header is missing or empty"},
        404: {"description": "Job not found in the current source scope"},
    },
    openapi_extra={
        "parameters": [
            {
                "name": "X-Source-Id",
                "in": "header",
                "required": True,
                "schema": {"type": "string", "minLength": 1},
                "description": "Source scope validated by the API Gateway",
            },
        ],
    },
)
async def get_latest_execution_subtask_count(
    job_id: str,
    source_id: str = Depends(require_external_source_id),
    service: QueryService = Depends(get_query_service),
) -> LatestExecutionSubtaskCountResponse:
    """Return the latest execution's subtask count for a source-scoped job."""
    result = await service.get_latest_execution_subtask_count(
        job_id=job_id,
        source_id=source_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return result
