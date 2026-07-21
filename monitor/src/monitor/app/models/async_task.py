# -*- coding: utf-8 -*-
"""异步任务中心的查询模型。"""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


class AsyncTaskItemModel(BaseModel):
    """异步任务的单个目标执行明细。"""

    task_id: str = Field(..., description="任务ID")
    target_id: str = Field(..., description="目标ID")
    target_name: str | None = Field(default=None, description="目标名称")
    status: str = Field(..., description="目标执行状态")
    error_message: str | None = Field(default=None, description="错误信息")
    result_json: Any = Field(default=None, description="执行结果")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")


class AsyncTaskModel(BaseModel):
    """异步任务主表记录。"""

    task_id: str = Field(..., description="任务ID")
    service: str = Field(..., description="写入服务")
    task_type: str = Field(..., description="任务类型")
    status: str = Field(..., description="任务状态")
    title: str = Field(..., description="任务标题")
    summary: str | None = Field(default=None, description="任务摘要")
    source_id: str | None = Field(default=None, description="来源标识")
    actor_user_id: str | None = Field(default=None, description="操作人ID")
    actor_user_name: str | None = Field(default=None, description="操作人名称")
    target_count: int = Field(default=0, description="目标总数")
    done_count: int = Field(default=0, description="完成数量")
    failed_count: int = Field(default=0, description="失败数量")
    error_message: str | None = Field(default=None, description="错误信息")
    result_json: Any = Field(default=None, description="任务结果")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")
    finished_at: datetime | None = Field(default=None, description="完成时间")


class AsyncTaskDetailModel(AsyncTaskModel):
    """异步任务详情，包含目标明细列表。"""

    items: list[AsyncTaskItemModel] = Field(
        default_factory=list,
        description="目标明细列表",
    )


ItemT = TypeVar("ItemT")


class PaginatedResponse(BaseModel, Generic[ItemT]):
    """通用分页响应。"""

    items: list[ItemT] = Field(default_factory=list, description="数据列表")
    total: int = Field(default=0, description="总数")
    page: int = Field(default=1, description="页码")
    page_size: int = Field(default=20, description="每页数量")
