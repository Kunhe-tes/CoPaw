# -*- coding: utf-8 -*-
"""HTML 预览点击统计业务服务。"""

from datetime import datetime
from typing import Optional

from .models import (
    HtmlPreviewClickEventCreate,
    HtmlPreviewClickEventItem,
    HtmlPreviewClickSummaryItem,
    HtmlPreviewCustomerClickItem,
    HtmlPreviewCustomerClickSummaryItem,
    HtmlPreviewListSnapshotCreate,
    HtmlPreviewListSummaryItem,
)
from .store import HtmlPreviewClickStore


class HtmlPreviewClickService:
    """封装 HTML 预览点击统计的保存和查询逻辑。"""

    def __init__(self, store: HtmlPreviewClickStore):
        """初始化点击统计服务。

        Args:
            store: 点击统计存储实例
        """
        self.store = store

    async def create_event(
        self,
        event: HtmlPreviewClickEventCreate,
    ) -> None:
        """保存一条 HTML 预览按钮点击事件。"""
        await self.store.create_event(event)

    async def list_summary(
        self,
        *,
        source_id: Optional[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        bbk_ids: Optional[list[str]] = None,
        cron_task_id: Optional[str] = None,
        file_url: Optional[str] = None,
        list_key: Optional[str] = None,
        limit: int = 100,
    ) -> list[HtmlPreviewClickSummaryItem]:
        """查询 HTML 预览按钮点击聚合结果。"""
        return await self.store.list_summary(
            source_id=source_id,
            start_time=start_time,
            end_time=end_time,
            bbk_ids=bbk_ids,
            cron_task_id=cron_task_id,
            file_url=file_url,
            list_key=list_key,
            limit=limit,
        )

    async def list_events(
        self,
        *,
        source_id: Optional[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        bbk_ids: Optional[list[str]] = None,
        cron_task_id: Optional[str] = None,
        file_url: Optional[str] = None,
        list_key: Optional[str] = None,
        limit: int = 100,
    ) -> list[HtmlPreviewClickEventItem]:
        """查询 HTML 预览按钮点击明细。"""
        return await self.store.list_events(
            source_id=source_id,
            start_time=start_time,
            end_time=end_time,
            bbk_ids=bbk_ids,
            cron_task_id=cron_task_id,
            file_url=file_url,
            list_key=list_key,
            limit=limit,
        )

    async def list_customer_summary(
        self,
        *,
        source_id: Optional[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        bbk_ids: Optional[list[str]] = None,
        cron_task_id: Optional[str] = None,
        file_url: Optional[str] = None,
        list_key: Optional[str] = None,
        limit: int = 100,
    ) -> list[HtmlPreviewCustomerClickSummaryItem]:
        """按客户查询洞察和电访按钮点击聚合结果。"""
        return await self.store.list_customer_summary(
            source_id=source_id,
            start_time=start_time,
            end_time=end_time,
            bbk_ids=bbk_ids,
            cron_task_id=cron_task_id,
            file_url=file_url,
            list_key=list_key,
            limit=limit,
        )

    async def create_list_snapshot(
        self,
        snapshot: HtmlPreviewListSnapshotCreate,
    ) -> int:
        """保存 HTML 名单客户快照。"""
        return await self.store.create_list_snapshot(snapshot)

    async def list_lists(
        self,
        *,
        source_id: Optional[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        bbk_ids: Optional[list[str]] = None,
        limit: int = 100,
    ) -> list[HtmlPreviewListSummaryItem]:
        """查询名单维度统计。"""
        return await self.store.list_lists(
            source_id=source_id,
            start_time=start_time,
            end_time=end_time,
            bbk_ids=bbk_ids,
            limit=limit,
        )

    async def list_customer_clicks(
        self,
        *,
        source_id: Optional[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        bbk_ids: Optional[list[str]] = None,
        cron_task_id: Optional[str] = None,
        file_url: Optional[str] = None,
        list_key: Optional[str] = None,
        include_unclicked: bool = False,
        limit: int = 100,
    ) -> list[HtmlPreviewCustomerClickItem]:
        """查询客户维度洞察和电访点击明细。"""
        return await self.store.list_customer_clicks(
            source_id=source_id,
            start_time=start_time,
            end_time=end_time,
            bbk_ids=bbk_ids,
            cron_task_id=cron_task_id,
            file_url=file_url,
            list_key=list_key,
            include_unclicked=include_unclicked,
            limit=limit,
        )
