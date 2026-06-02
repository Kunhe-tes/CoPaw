# -*- coding: utf-8 -*-
"""HTML 预览点击统计数据模型。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class HtmlPreviewClickEventCreate(BaseModel):
    """提交 HTML 预览按钮点击事件的请求体。"""

    source_id: Optional[str] = Field(default=None, max_length=64)
    user_id: Optional[str] = Field(default=None, max_length=128)
    bbk_id: Optional[str] = Field(default=None, max_length=128)
    cron_task_id: Optional[str] = Field(default=None, max_length=128)
    cron_task_name: Optional[str] = Field(default=None, max_length=255)
    file_url: str = Field(..., min_length=1, max_length=4096)
    file_name: Optional[str] = Field(default=None, max_length=512)
    list_key: Optional[str] = Field(default=None, max_length=1024)
    list_name: Optional[str] = Field(default=None, max_length=512)
    button_id: Optional[str] = Field(default=None, max_length=255)
    button_name: Optional[str] = Field(default=None, max_length=255)
    button_text: Optional[str] = Field(default=None, max_length=512)
    button_type: Optional[str] = Field(default=None, max_length=32)
    customer_id: Optional[str] = Field(default=None, max_length=128)
    customer_name: Optional[str] = Field(default=None, max_length=255)
    customer_info: Optional[dict[str, str]] = None
    clicked_at: Optional[datetime] = None


class HtmlPreviewClickCreateResponse(BaseModel):
    """保存 HTML 预览点击事件后的响应。"""

    success: bool = True


class HtmlPreviewClickSummaryItem(BaseModel):
    """HTML 预览点击聚合结果。"""

    button_label: str
    button_id: Optional[str] = None
    button_name: Optional[str] = None
    button_text: Optional[str] = None
    bbk_id: Optional[str] = None
    cron_task_id: Optional[str] = None
    cron_task_name: Optional[str] = None
    list_key: Optional[str] = None
    list_name: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    click_count: int = 0
    last_clicked_at: Optional[datetime] = None


class HtmlPreviewClickSummaryResponse(BaseModel):
    """HTML 预览点击聚合查询响应。"""

    success: bool = True
    items: list[HtmlPreviewClickSummaryItem] = Field(default_factory=list)


class HtmlPreviewCustomerClickSummaryItem(BaseModel):
    """HTML 预览客户维度点击聚合结果。"""

    customer_id: Optional[str] = None
    customer_name: str = "未知客户"
    insight_count: int = 0
    phone_count: int = 0
    plan_count: int = 0
    total_click_count: int = 0
    last_clicked_at: Optional[datetime] = None


class HtmlPreviewCustomerClickSummaryResponse(BaseModel):
    """HTML 预览客户维度点击聚合查询响应。"""

    success: bool = True
    items: list[HtmlPreviewCustomerClickSummaryItem] = Field(
        default_factory=list,
    )


class HtmlPreviewClickEventItem(BaseModel):
    """HTML 预览点击明细。"""

    id: int
    source_id: Optional[str] = None
    user_id: Optional[str] = None
    bbk_id: Optional[str] = None
    cron_task_id: Optional[str] = None
    cron_task_name: Optional[str] = None
    file_url: str
    file_name: Optional[str] = None
    list_key: Optional[str] = None
    list_name: Optional[str] = None
    button_id: Optional[str] = None
    button_name: Optional[str] = None
    button_text: Optional[str] = None
    button_type: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_info: Optional[dict[str, str]] = None
    clicked_at: Optional[datetime] = None


class HtmlPreviewClickEventListResponse(BaseModel):
    """HTML 预览点击明细查询响应。"""

    success: bool = True
    items: list[HtmlPreviewClickEventItem] = Field(default_factory=list)


class HtmlPreviewListSnapshotCustomer(BaseModel):
    """HTML 名单快照中的客户。"""

    customer_id: Optional[str] = Field(default=None, max_length=128)
    customer_name: str = Field(..., min_length=1, max_length=255)
    extra_info: Optional[dict[str, str]] = None


class HtmlPreviewListSnapshotCreate(BaseModel):
    """提交 HTML 名单客户快照的请求体。"""

    source_id: Optional[str] = Field(default=None, max_length=64)
    bbk_id: Optional[str] = Field(default=None, max_length=128)
    cron_task_id: Optional[str] = Field(default=None, max_length=128)
    cron_task_name: Optional[str] = Field(default=None, max_length=255)
    list_key: Optional[str] = Field(default=None, max_length=1024)
    list_name: Optional[str] = Field(default=None, max_length=512)
    file_url: str = Field(..., min_length=1, max_length=4096)
    file_name: Optional[str] = Field(default=None, max_length=512)
    customers: list[HtmlPreviewListSnapshotCustomer] = Field(
        default_factory=list,
    )
    snapshot_at: Optional[datetime] = None


class HtmlPreviewListSnapshotResponse(BaseModel):
    """保存 HTML 名单快照后的响应。"""

    success: bool = True
    customer_count: int = 0


class HtmlPreviewListSummaryItem(BaseModel):
    """HTML 名单维度统计结果。"""

    list_key: str
    list_name: str
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    cron_task_id: Optional[str] = None
    cron_task_name: Optional[str] = None
    customer_count: int = 0
    clicked_customer_count: int = 0
    insight_count: int = 0
    phone_count: int = 0
    plan_count: int = 0
    total_click_count: int = 0
    last_clicked_at: Optional[datetime] = None


class HtmlPreviewListSummaryResponse(BaseModel):
    """HTML 名单维度统计查询响应。"""

    success: bool = True
    items: list[HtmlPreviewListSummaryItem] = Field(default_factory=list)


class HtmlPreviewCustomerClickItem(BaseModel):
    """HTML 名单客户维度点击明细。"""

    customer_id: Optional[str] = None
    customer_name: str = "未知客户"
    list_key: Optional[str] = None
    list_name: Optional[str] = None
    insight_count: int = 0
    phone_count: int = 0
    plan_count: int = 0
    total_click_count: int = 0
    last_clicked_at: Optional[datetime] = None


class HtmlPreviewCustomerClickResponse(BaseModel):
    """HTML 名单客户维度点击查询响应。"""

    success: bool = True
    items: list[HtmlPreviewCustomerClickItem] = Field(default_factory=list)
