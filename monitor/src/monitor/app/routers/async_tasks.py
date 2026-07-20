# -*- coding: utf-8 -*-
"""异步任务中心查询路由。"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..models.async_task import (
    AsyncTaskDetailModel,
    AsyncTaskModel,
    PaginatedResponse,
)
from ..services.async_task import (
    AsyncTaskQueryService,
    get_async_task_query_service,
)

router = APIRouter(prefix="/tasks", tags=["async-tasks"])


def _get_source_id_from_header(request: Request) -> str:
    """从请求头读取来源标识，缺省使用 default。"""
    return request.headers.get("X-Source-Id") or "default"


@router.get("", response_model=PaginatedResponse[AsyncTaskModel])
async def list_async_tasks(
    request: Request,
    service_name: str | None = Query(default=None, alias="service"),
    task_type: str | None = Query(default=None, description="任务类型"),
    status: str | None = Query(default=None, description="任务状态"),
    keyword: str | None = Query(default=None, description="关键词"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    service: AsyncTaskQueryService = Depends(get_async_task_query_service),
) -> PaginatedResponse[AsyncTaskModel]:
    """分页查询当前来源下的异步任务。"""
    return await service.list_tasks(
        source_id=_get_source_id_from_header(request),
        service=service_name,
        task_type=task_type,
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )


@router.get("/{task_id}", response_model=AsyncTaskDetailModel)
async def get_async_task(
    request: Request,
    task_id: str,
    service: AsyncTaskQueryService = Depends(get_async_task_query_service),
) -> AsyncTaskDetailModel:
    """查询单个异步任务详情。"""
    result = await service.get_task(
        task_id,
        source_id=_get_source_id_from_header(request),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result
