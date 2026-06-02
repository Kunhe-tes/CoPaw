# -*- coding: utf-8 -*-
"""HTML 预览点击统计数据库存储。"""

import json
from datetime import datetime
from typing import Any, Optional

from .models import (
    HtmlPreviewClickEventCreate,
    HtmlPreviewClickEventItem,
    HtmlPreviewClickSummaryItem,
    HtmlPreviewCustomerClickItem,
    HtmlPreviewCustomerClickSummaryItem,
    HtmlPreviewListSnapshotCreate,
    HtmlPreviewListSummaryItem,
)

CUSTOMER_SUMMARY_SCAN_LIMIT = 10000


class HtmlPreviewClickStore:
    """负责 HTML 预览点击事件、名单快照的落库与聚合查询。"""

    def __init__(self, db: Optional[Any] = None):
        """初始化点击统计存储。

        Args:
            db: 已连接的数据库对象
        """
        self.db = db
        self._use_db = db is not None and db.is_connected

    @staticmethod
    def _clean_text(value: Optional[str]) -> Optional[str]:
        """清理空字符串，避免聚合字段里混入无意义值。"""
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped or None

    @classmethod
    def _list_key(cls, file_url: str, list_key: Optional[str]) -> str:
        """统一名单主键，默认用文件 URL 兼容老数据。"""
        return cls._clean_text(list_key) or file_url

    @classmethod
    def _list_name(
        cls,
        file_name: Optional[str],
        list_name: Optional[str],
        file_url: Optional[str] = None,
    ) -> str:
        """统一名单展示名，优先使用显式名单名。"""
        return (
            cls._clean_text(list_name)
            or cls._clean_text(file_name)
            or cls._clean_text(file_url)
            or "未知名单"
        )

    @staticmethod
    def _encode_json(value: Optional[dict[str, str]]) -> Optional[str]:
        """把扩展信息序列化为 JSON，避免数据库驱动差异影响写入。"""
        if not value:
            return None
        cleaned = {
            str(key).strip(): str(item).strip()
            for key, item in value.items()
            if str(key).strip() and str(item).strip()
        }
        return json.dumps(cleaned, ensure_ascii=False) if cleaned else None

    @staticmethod
    def _decode_json(value: Any) -> Optional[dict[str, str]]:
        """解析数据库中的 JSON 扩展字段。"""
        if not value:
            return None
        if isinstance(value, dict):
            return {str(key): str(item) for key, item in value.items()}
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return None
        if not isinstance(parsed, dict):
            return None
        return {str(key): str(item) for key, item in parsed.items()}

    @staticmethod
    def _encode_customer_info(
        value: Optional[dict[str, str]],
    ) -> Optional[str]:
        """序列化点击事件里的客户扩展信息。"""
        return HtmlPreviewClickStore._encode_json(value)

    @staticmethod
    def _decode_customer_info(value: Any) -> Optional[dict[str, str]]:
        """解析点击事件里的客户扩展信息。"""
        return HtmlPreviewClickStore._decode_json(value)

    @classmethod
    def _get_customer_identity(
        cls,
        customer_info: Any,
        customer_id: Optional[str] = None,
        customer_name: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        """从结构化字段和扩展信息中提取客户 ID 与展示姓名。"""
        info = cls._decode_customer_info(customer_info) or {}
        resolved_id = cls._clean_text(customer_id) or cls._clean_text(
            info.get("customer_id"),
        )
        resolved_name = (
            cls._clean_text(customer_name)
            or cls._clean_text(info.get("name"))
            or cls._clean_text(info.get("customer_name"))
            or cls._clean_text(info.get("客户姓名"))
            or cls._clean_text(info.get("客户名称"))
            or cls._clean_text(info.get("姓名"))
        )
        return resolved_id, resolved_name

    @classmethod
    def _classify_button(cls, row: dict[str, Any]) -> str:
        """把按钮点击归类为洞察、电访、查看方案或其他。"""
        explicit = cls._clean_text(row.get("button_type"))
        if explicit in {"insight", "phone", "plan", "other"}:
            return explicit

        button_id = (cls._clean_text(row.get("button_id")) or "").lower()
        button_name = cls._clean_text(row.get("button_name")) or ""
        button_text = cls._clean_text(row.get("button_text")) or ""
        if (
            "plan" in button_id
            or "查看方案" in button_name
            or "查看方案" in button_text
        ):
            return "plan"
        if (
            "phone" in button_id
            or "电访" in button_name
            or "电访" in button_text
            or "电话访问" in button_name
            or "电话访问" in button_text
        ):
            return "phone"
        if (
            "insight" in button_id
            or "洞察" in button_name
            or "洞察" in button_text
        ):
            return "insight"
        return "other"

    @classmethod
    def _normalize_event(
        cls,
        event: HtmlPreviewClickEventCreate,
    ) -> dict[str, Any]:
        """补齐点击事件的核心分析字段。"""
        customer_id, customer_name = cls._get_customer_identity(
            event.customer_info,
            event.customer_id,
            event.customer_name,
        )
        list_key = cls._list_key(event.file_url, event.list_key)
        list_name = cls._list_name(
            event.file_name,
            event.list_name,
            event.file_url,
        )
        button_type = cls._classify_button(
            {
                "button_type": event.button_type,
                "button_id": event.button_id,
                "button_name": event.button_name,
                "button_text": event.button_text,
            },
        )
        return {
            "list_key": list_key,
            "list_name": list_name,
            "button_type": button_type,
            "customer_id": customer_id,
            "customer_name": customer_name,
        }

    @staticmethod
    def _to_summary_item(row: dict[str, Any]) -> HtmlPreviewClickSummaryItem:
        """把数据库行转换为点击聚合模型。"""
        return HtmlPreviewClickSummaryItem(
            button_label=row.get("button_label") or "未知按钮",
            button_id=row.get("button_id"),
            button_name=row.get("button_name"),
            button_text=row.get("button_text"),
            bbk_id=row.get("bbk_id"),
            cron_task_id=row.get("cron_task_id"),
            cron_task_name=row.get("cron_task_name"),
            list_key=row.get("list_key"),
            list_name=row.get("list_name"),
            file_url=row.get("file_url"),
            file_name=row.get("file_name"),
            click_count=int(row.get("click_count") or 0),
            last_clicked_at=row.get("last_clicked_at"),
        )

    @staticmethod
    def _to_customer_summary_item(
        row: dict[str, Any],
    ) -> HtmlPreviewCustomerClickSummaryItem:
        """把数据库行转换为客户维度点击聚合模型。"""
        return HtmlPreviewCustomerClickSummaryItem(
            customer_id=row.get("customer_id"),
            customer_name=row.get("customer_name") or "未知客户",
            insight_count=int(row.get("insight_count") or 0),
            phone_count=int(row.get("phone_count") or 0),
            plan_count=int(row.get("plan_count") or 0),
            total_click_count=int(row.get("total_click_count") or 0),
            last_clicked_at=row.get("last_clicked_at"),
        )

    @classmethod
    def _to_event_item(cls, row: dict[str, Any]) -> HtmlPreviewClickEventItem:
        """把数据库行转换为点击明细模型。"""
        customer_id, customer_name = cls._get_customer_identity(
            row.get("customer_info"),
            row.get("customer_id"),
            row.get("customer_name"),
        )
        return HtmlPreviewClickEventItem(
            id=int(row.get("id") or 0),
            source_id=row.get("source_id"),
            user_id=row.get("user_id"),
            bbk_id=row.get("bbk_id"),
            cron_task_id=row.get("cron_task_id"),
            cron_task_name=row.get("cron_task_name"),
            file_url=row.get("file_url") or "",
            file_name=row.get("file_name"),
            list_key=row.get("list_key"),
            list_name=row.get("list_name"),
            button_id=row.get("button_id"),
            button_name=row.get("button_name"),
            button_text=row.get("button_text"),
            button_type=row.get("button_type"),
            customer_id=customer_id,
            customer_name=customer_name,
            customer_info=cls._decode_customer_info(row.get("customer_info")),
            clicked_at=row.get("clicked_at"),
        )

    async def create_event(
        self,
        event: HtmlPreviewClickEventCreate,
    ) -> None:
        """保存一条 HTML 预览按钮点击明细。"""
        if not self._use_db:
            return

        normalized = self._normalize_event(event)
        query = """
            INSERT INTO swe_html_preview_click_events (
                source_id,
                user_id,
                bbk_id,
                cron_task_id,
                cron_task_name,
                file_url,
                file_name,
                list_key,
                list_name,
                button_id,
                button_name,
                button_text,
                button_type,
                customer_id,
                customer_name,
                customer_info,
                clicked_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
        """
        await self.db.execute(
            query,
            (
                self._clean_text(event.source_id),
                self._clean_text(event.user_id),
                self._clean_text(event.bbk_id),
                self._clean_text(event.cron_task_id),
                self._clean_text(event.cron_task_name),
                event.file_url,
                self._clean_text(event.file_name),
                normalized["list_key"],
                normalized["list_name"],
                self._clean_text(event.button_id),
                self._clean_text(event.button_name),
                self._clean_text(event.button_text),
                normalized["button_type"],
                normalized["customer_id"],
                normalized["customer_name"],
                self._encode_customer_info(event.customer_info),
                event.clicked_at or datetime.now(),
            ),
        )

    async def create_list_snapshot(
        self,
        snapshot: HtmlPreviewListSnapshotCreate,
    ) -> int:
        """保存一份 HTML 名单客户快照。"""
        if not self._use_db:
            return 0

        list_key = self._list_key(snapshot.file_url, snapshot.list_key)
        list_name = self._list_name(
            snapshot.file_name,
            snapshot.list_name,
            snapshot.file_url,
        )
        snapshot_at = snapshot.snapshot_at or datetime.now()
        delete_query = """
            DELETE FROM swe_html_preview_list_snapshots
            WHERE source_id <=> %s AND bbk_id <=> %s AND list_key = %s
        """
        await self.db.execute(
            delete_query,
            (
                self._clean_text(snapshot.source_id),
                self._clean_text(snapshot.bbk_id),
                list_key,
            ),
        )

        insert_query = """
            INSERT INTO swe_html_preview_list_snapshots (
                source_id,
                bbk_id,
                cron_task_id,
                cron_task_name,
                list_key,
                list_name,
                file_url,
                file_name,
                customer_id,
                customer_name,
                extra_info,
                snapshot_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        inserted = 0
        seen: set[str] = set()
        for customer in snapshot.customers:
            customer_id = self._clean_text(customer.customer_id)
            customer_name = self._clean_text(customer.customer_name)
            if not customer_id and not customer_name:
                continue
            unique_key = customer_id or f"name:{customer_name}"
            if unique_key in seen:
                continue
            seen.add(unique_key)
            await self.db.execute(
                insert_query,
                (
                    self._clean_text(snapshot.source_id),
                    self._clean_text(snapshot.bbk_id),
                    self._clean_text(snapshot.cron_task_id),
                    self._clean_text(snapshot.cron_task_name),
                    list_key,
                    list_name,
                    snapshot.file_url,
                    self._clean_text(snapshot.file_name),
                    customer_id,
                    customer_name or "未知客户",
                    self._encode_json(customer.extra_info),
                    snapshot_at,
                ),
            )
            inserted += 1
        return inserted

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
        if not self._use_db:
            return []

        where_sql, params = self._build_event_where_clause(
            source_id=source_id,
            start_time=start_time,
            end_time=end_time,
            bbk_ids=bbk_ids,
            cron_task_id=cron_task_id,
            file_url=file_url,
            list_key=list_key,
        )
        safe_limit = max(1, min(limit, 200))
        query = f"""
            SELECT
                id,
                source_id,
                user_id,
                bbk_id,
                cron_task_id,
                cron_task_name,
                file_url,
                file_name,
                list_key,
                list_name,
                button_id,
                button_name,
                button_text,
                button_type,
                customer_id,
                customer_name,
                customer_info,
                clicked_at
            FROM swe_html_preview_click_events
            {where_sql}
            ORDER BY clicked_at DESC, id DESC
            LIMIT {safe_limit}
        """
        rows = await self.db.fetch_all(query, tuple(params))
        return [self._to_event_item(row) for row in rows]

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
        """按按钮、任务和 HTML 文件聚合点击次数。"""
        if not self._use_db:
            return []

        where_sql, params = self._build_event_where_clause(
            source_id=source_id,
            start_time=start_time,
            end_time=end_time,
            bbk_ids=bbk_ids,
            cron_task_id=cron_task_id,
            file_url=file_url,
            list_key=list_key,
        )
        safe_limit = max(1, min(limit, 200))

        query = f"""
            SELECT
                COALESCE(
                    NULLIF(button_name, ''),
                    NULLIF(button_text, ''),
                    NULLIF(button_id, ''),
                    '未知按钮'
                ) AS button_label,
                button_id,
                button_name,
                button_text,
                cron_task_id,
                cron_task_name,
                list_key,
                list_name,
                file_url,
                file_name,
                COUNT(*) AS click_count,
                MAX(clicked_at) AS last_clicked_at
            FROM swe_html_preview_click_events
            {where_sql}
            GROUP BY
                button_id,
                button_name,
                button_text,
                cron_task_id,
                cron_task_name,
                list_key,
                list_name,
                file_url,
                file_name
            ORDER BY click_count DESC, last_clicked_at DESC
            LIMIT {safe_limit}
        """
        rows = await self.db.fetch_all(query, tuple(params))
        return [self._to_summary_item(row) for row in rows]

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
        """按客户聚合洞察和电访按钮点击次数。"""
        items = await self.list_customer_clicks(
            source_id=source_id,
            start_time=start_time,
            end_time=end_time,
            bbk_ids=bbk_ids,
            cron_task_id=cron_task_id,
            file_url=file_url,
            list_key=list_key,
            include_unclicked=False,
            limit=limit,
        )
        return [
            HtmlPreviewCustomerClickSummaryItem(
                customer_id=item.customer_id,
                customer_name=item.customer_name,
                insight_count=item.insight_count,
                phone_count=item.phone_count,
                plan_count=item.plan_count,
                total_click_count=item.total_click_count,
                last_clicked_at=item.last_clicked_at,
            )
            for item in items
        ]

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
        if not self._use_db:
            return []

        snapshot_rows = await self._fetch_snapshot_rows(
            source_id=source_id,
            bbk_ids=bbk_ids,
            list_key=None,
        )
        event_rows = await self._fetch_event_rows(
            source_id=source_id,
            start_time=start_time,
            end_time=end_time,
            bbk_ids=bbk_ids,
            cron_task_id=None,
            file_url=None,
            list_key=None,
        )
        grouped = self._build_list_summary(snapshot_rows, event_rows)
        return grouped[: max(1, min(limit, 200))]

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
        if not self._use_db:
            return []

        snapshot_rows = []
        if include_unclicked:
            snapshot_rows = await self._fetch_snapshot_rows(
                source_id=source_id,
                bbk_ids=bbk_ids,
                list_key=list_key,
            )
        event_rows = await self._fetch_event_rows(
            source_id=source_id,
            start_time=start_time,
            end_time=end_time,
            bbk_ids=bbk_ids,
            cron_task_id=cron_task_id,
            file_url=file_url,
            list_key=list_key,
        )
        rows = self._build_customer_click_items(
            snapshot_rows=snapshot_rows,
            event_rows=event_rows,
            include_unclicked=include_unclicked,
        )
        return rows[: max(1, min(limit, 500))]

    async def _fetch_event_rows(
        self,
        *,
        source_id: Optional[str],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        bbk_ids: Optional[list[str]],
        cron_task_id: Optional[str],
        file_url: Optional[str],
        list_key: Optional[str],
    ) -> list[dict[str, Any]]:
        """查询用于应用层聚合的点击明细。"""
        where_sql, params = self._build_event_where_clause(
            source_id=source_id,
            start_time=start_time,
            end_time=end_time,
            bbk_ids=bbk_ids,
            cron_task_id=cron_task_id,
            file_url=file_url,
            list_key=list_key,
        )
        query = f"""
            SELECT
                id,
                cron_task_id,
                cron_task_name,
                file_url,
                file_name,
                list_key,
                list_name,
                button_id,
                button_name,
                button_text,
                button_type,
                customer_id,
                customer_name,
                customer_info,
                clicked_at
            FROM swe_html_preview_click_events
            {where_sql}
            ORDER BY clicked_at DESC, id DESC
            LIMIT {CUSTOMER_SUMMARY_SCAN_LIMIT}
        """
        return await self.db.fetch_all(query, tuple(params))

    async def _fetch_snapshot_rows(
        self,
        *,
        source_id: Optional[str],
        bbk_ids: Optional[list[str]],
        list_key: Optional[str],
    ) -> list[dict[str, Any]]:
        """查询名单客户快照。"""
        where_sql, params = self._build_snapshot_where_clause(
            source_id=source_id,
            bbk_ids=bbk_ids,
            list_key=list_key,
        )
        query = f"""
            SELECT
                source_id,
                bbk_id,
                cron_task_id,
                cron_task_name,
                list_key,
                list_name,
                file_url,
                file_name,
                customer_id,
                customer_name,
                extra_info,
                snapshot_at
            FROM swe_html_preview_list_snapshots
            {where_sql}
            ORDER BY snapshot_at DESC
            LIMIT {CUSTOMER_SUMMARY_SCAN_LIMIT}
        """
        return await self.db.fetch_all(query, tuple(params))

    @classmethod
    def _build_list_summary(
        cls,
        snapshot_rows: list[dict[str, Any]],
        event_rows: list[dict[str, Any]],
    ) -> list[HtmlPreviewListSummaryItem]:
        """组合名单快照和点击事件，生成名单维度统计。"""
        grouped: dict[str, dict[str, Any]] = {}
        for row in snapshot_rows:
            list_key = cls._list_key(
                row.get("file_url") or "",
                row.get("list_key"),
            )
            item = grouped.setdefault(
                list_key,
                {
                    "list_key": list_key,
                    "list_name": cls._list_name(
                        row.get("file_name"),
                        row.get("list_name"),
                        row.get("file_url"),
                    ),
                    "file_url": row.get("file_url"),
                    "file_name": row.get("file_name"),
                    "cron_task_id": row.get("cron_task_id"),
                    "cron_task_name": row.get("cron_task_name"),
                    "customers": set(),
                    "clicked_customers": set(),
                    "insight_count": 0,
                    "phone_count": 0,
                    "plan_count": 0,
                    "total_click_count": 0,
                    "last_clicked_at": None,
                },
            )
            customer_key = (
                row.get("customer_id") or f"name:{row.get('customer_name')}"
            )
            if customer_key:
                item["customers"].add(customer_key)

        for row in event_rows:
            list_key = cls._list_key(
                row.get("file_url") or "",
                row.get("list_key"),
            )
            item = grouped.setdefault(
                list_key,
                {
                    "list_key": list_key,
                    "list_name": cls._list_name(
                        row.get("file_name"),
                        row.get("list_name"),
                        row.get("file_url"),
                    ),
                    "file_url": row.get("file_url"),
                    "file_name": row.get("file_name"),
                    "cron_task_id": row.get("cron_task_id"),
                    "cron_task_name": row.get("cron_task_name"),
                    "customers": set(),
                    "clicked_customers": set(),
                    "insight_count": 0,
                    "phone_count": 0,
                    "plan_count": 0,
                    "total_click_count": 0,
                    "last_clicked_at": None,
                },
            )
            cls._apply_event_to_group(item, row)

        items = [
            HtmlPreviewListSummaryItem(
                list_key=row["list_key"],
                list_name=row["list_name"],
                file_url=row.get("file_url"),
                file_name=row.get("file_name"),
                cron_task_id=row.get("cron_task_id"),
                cron_task_name=row.get("cron_task_name"),
                customer_count=len(row["customers"]),
                clicked_customer_count=len(row["clicked_customers"]),
                insight_count=row["insight_count"],
                phone_count=row["phone_count"],
                plan_count=row["plan_count"],
                total_click_count=row["total_click_count"],
                last_clicked_at=row.get("last_clicked_at"),
            )
            for row in grouped.values()
        ]
        return sorted(
            items,
            key=lambda item: (
                item.total_click_count,
                item.last_clicked_at or datetime.min,
            ),
            reverse=True,
        )

    @classmethod
    def _build_customer_click_items(
        cls,
        *,
        snapshot_rows: list[dict[str, Any]],
        event_rows: list[dict[str, Any]],
        include_unclicked: bool,
    ) -> list[HtmlPreviewCustomerClickItem]:
        """组合名单快照和点击事件，生成客户维度统计。"""
        grouped: dict[str, dict[str, Any]] = {}
        if include_unclicked:
            for row in snapshot_rows:
                key = cls._customer_group_key(
                    row.get("customer_id"),
                    row.get("customer_name"),
                )
                if not key:
                    continue
                grouped.setdefault(
                    key,
                    cls._empty_customer_group(
                        customer_id=row.get("customer_id"),
                        customer_name=row.get("customer_name"),
                        list_key=row.get("list_key"),
                        list_name=row.get("list_name"),
                    ),
                )

        for row in event_rows:
            customer_id, customer_name = cls._get_customer_identity(
                row.get("customer_info"),
                row.get("customer_id"),
                row.get("customer_name"),
            )
            key = cls._customer_group_key(customer_id, customer_name)
            if not key:
                continue
            item = grouped.setdefault(
                key,
                cls._empty_customer_group(
                    customer_id=customer_id,
                    customer_name=customer_name,
                    list_key=row.get("list_key"),
                    list_name=row.get("list_name"),
                ),
            )
            cls._apply_event_to_group(item, row)

        items = [
            HtmlPreviewCustomerClickItem(
                customer_id=row.get("customer_id"),
                customer_name=row.get("customer_name") or "未知客户",
                list_key=row.get("list_key"),
                list_name=row.get("list_name"),
                insight_count=row["insight_count"],
                phone_count=row["phone_count"],
                plan_count=row["plan_count"],
                total_click_count=row["total_click_count"],
                last_clicked_at=row.get("last_clicked_at"),
            )
            for row in grouped.values()
            if include_unclicked or row["total_click_count"] > 0
        ]
        return sorted(
            items,
            key=lambda item: (
                item.total_click_count,
                item.last_clicked_at or datetime.min,
            ),
            reverse=True,
        )

    @classmethod
    def _customer_group_key(
        cls,
        customer_id: Optional[str],
        customer_name: Optional[str],
    ) -> Optional[str]:
        """构造客户去重键，优先按客户 ID 去重。"""
        cleaned_id = cls._clean_text(customer_id)
        cleaned_name = cls._clean_text(customer_name)
        if cleaned_id:
            return cleaned_id
        if cleaned_name:
            return f"name:{cleaned_name}"
        return None

    @classmethod
    def _empty_customer_group(
        cls,
        *,
        customer_id: Optional[str],
        customer_name: Optional[str],
        list_key: Optional[str],
        list_name: Optional[str],
    ) -> dict[str, Any]:
        """创建客户统计空行。"""
        return {
            "customer_id": cls._clean_text(customer_id),
            "customer_name": cls._clean_text(customer_name) or "未知客户",
            "list_key": cls._clean_text(list_key),
            "list_name": cls._clean_text(list_name),
            "insight_count": 0,
            "phone_count": 0,
            "plan_count": 0,
            "total_click_count": 0,
            "last_clicked_at": None,
        }

    @classmethod
    def _apply_event_to_group(
        cls,
        item: dict[str, Any],
        row: dict[str, Any],
    ) -> None:
        """把一条点击事件累加到聚合行。"""
        button_type = cls._classify_button(row)
        if button_type == "insight":
            item["insight_count"] += 1
        elif button_type == "phone":
            item["phone_count"] += 1
        elif button_type == "plan":
            item["plan_count"] += 1
        else:
            return

        item["total_click_count"] += 1
        customer_id, customer_name = cls._get_customer_identity(
            row.get("customer_info"),
            row.get("customer_id"),
            row.get("customer_name"),
        )
        customer_key = cls._customer_group_key(customer_id, customer_name)
        if customer_key and "clicked_customers" in item:
            item["clicked_customers"].add(customer_key)
        if customer_key and "customers" in item:
            item["customers"].add(customer_key)

        clicked_at = row.get("clicked_at")
        last_clicked_at = item.get("last_clicked_at")
        if clicked_at and (
            not last_clicked_at or clicked_at > last_clicked_at
        ):
            item["last_clicked_at"] = clicked_at
            if customer_name and "customer_name" in item:
                item["customer_name"] = customer_name

    def _build_event_where_clause(
        self,
        *,
        source_id: Optional[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        bbk_ids: Optional[list[str]] = None,
        cron_task_id: Optional[str] = None,
        file_url: Optional[str] = None,
        list_key: Optional[str] = None,
    ) -> tuple[str, list[Any]]:
        """构造点击查询的公共筛选条件。"""
        return self._build_where_clause(
            source_id=source_id,
            time_column="clicked_at",
            start_time=start_time,
            end_time=end_time,
            bbk_ids=bbk_ids,
            cron_task_id=cron_task_id,
            file_url=file_url,
            list_key=list_key,
        )

    def _build_snapshot_where_clause(
        self,
        *,
        source_id: Optional[str],
        bbk_ids: Optional[list[str]] = None,
        list_key: Optional[str] = None,
    ) -> tuple[str, list[Any]]:
        """构造名单快照查询的公共筛选条件。"""
        return self._build_where_clause(
            source_id=source_id,
            time_column="snapshot_at",
            bbk_ids=bbk_ids,
            list_key=list_key,
        )

    def _build_where_clause(
        self,
        *,
        source_id: Optional[str],
        time_column: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        bbk_ids: Optional[list[str]] = None,
        cron_task_id: Optional[str] = None,
        file_url: Optional[str] = None,
        list_key: Optional[str] = None,
    ) -> tuple[str, list[Any]]:
        """构造查询的公共筛选条件。"""
        where_clauses: list[str] = []
        params: list[Any] = []
        if source_id:
            where_clauses.append("source_id <=> %s")
            params.append(source_id)
        if start_time:
            where_clauses.append(f"{time_column} >= %s")
            params.append(start_time)
        if end_time:
            where_clauses.append(f"{time_column} <= %s")
            params.append(end_time)
        if bbk_ids:
            placeholders = ", ".join(["%s"] * len(bbk_ids))
            where_clauses.append(f"bbk_id IN ({placeholders})")
            params.extend(bbk_ids)
        if cron_task_id:
            where_clauses.append("cron_task_id = %s")
            params.append(cron_task_id)
        if file_url:
            where_clauses.append("file_url = %s")
            params.append(file_url)
        if list_key:
            where_clauses.append("list_key = %s")
            params.append(list_key)

        where_sql = (
            f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        )
        return where_sql, params
