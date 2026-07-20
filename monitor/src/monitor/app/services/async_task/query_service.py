# -*- coding: utf-8 -*-
"""异步任务中心只读查询服务。"""

import json
from typing import Any

from ...database.connection import get_db_connection
from ...models.async_task import (
    AsyncTaskDetailModel,
    AsyncTaskItemModel,
    AsyncTaskModel,
    PaginatedResponse,
)

TASK_TIME_FIELDS = ["created_at", "updated_at", "finished_at"]
ITEM_TIME_FIELDS = ["created_at", "updated_at"]


def _parse_json_field(value: Any) -> Any:
    """解析数据库 JSON 字段，解析失败时返回 None。"""
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="ignore")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _build_task_model(row: dict[str, Any]) -> AsyncTaskModel:
    """将任务主表行转换为响应模型。"""
    data = dict(row)
    data["result_json"] = _parse_json_field(data.get("result_json"))
    return AsyncTaskModel(**data)


def _build_item_model(row: dict[str, Any]) -> AsyncTaskItemModel:
    """将任务明细行转换为响应模型。"""
    data = dict(row)
    data["result_json"] = _parse_json_field(data.get("result_json"))
    return AsyncTaskItemModel(**data)


class AsyncTaskQueryService:
    """异步任务中心查询服务。"""

    def __init__(self, db=None) -> None:
        """初始化查询服务。

        Args:
            db: 数据库连接；为空时使用 Monitor 默认连接
        """
        self.db = db or get_db_connection()

    async def list_tasks(
        self,
        *,
        source_id: str | None = None,
        service: str | None = None,
        task_type: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[AsyncTaskModel]:
        """分页查询异步任务列表。"""
        where_clause, params = self._build_where_clause(
            source_id=source_id,
            service=service,
            task_type=task_type,
            status=status,
            keyword=keyword,
        )
        count_sql = f"""
            SELECT COUNT(*) AS total
            FROM swe_async_tasks
            WHERE {where_clause}
        """
        total_row = await self.db.fetch_one(count_sql, tuple(params))
        total = int(total_row.get("total", 0)) if total_row else 0

        offset = (page - 1) * page_size
        list_sql = f"""
            SELECT task_id, service, task_type, status, title, summary,
                   source_id, tenant_id, actor_user_id, actor_user_name,
                   target_count, done_count, failed_count, error_message,
                   result_json, created_at, updated_at, finished_at
            FROM swe_async_tasks
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        rows = await self.db.fetch_all(
            list_sql,
            tuple([*params, page_size, offset]),
        )
        return PaginatedResponse[AsyncTaskModel](
            items=[_build_task_model(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_task(
        self,
        task_id: str,
        *,
        source_id: str | None = None,
    ) -> AsyncTaskDetailModel | None:
        """查询单个异步任务详情。"""
        where_clause = "task_id = %s"
        params: list[str] = [task_id]
        if source_id:
            where_clause = f"{where_clause} AND source_id = %s"
            params.append(source_id)
        task_sql = f"""
            SELECT task_id, service, task_type, status, title, summary,
                   source_id, tenant_id, actor_user_id, actor_user_name,
                   target_count, done_count, failed_count, error_message,
                   result_json, created_at, updated_at, finished_at
            FROM swe_async_tasks
            WHERE {where_clause}
        """
        row = await self.db.fetch_one(task_sql, tuple(params))
        if not row:
            return None

        item_sql = """
            SELECT task_id, target_id, target_name, status, error_message,
                   result_json, created_at, updated_at
            FROM swe_async_task_items
            WHERE task_id = %s
            ORDER BY created_at ASC, target_id ASC
        """
        item_rows = await self.db.fetch_all(item_sql, (task_id,))
        task = _build_task_model(row)
        return AsyncTaskDetailModel(
            **task.model_dump(),
            items=[_build_item_model(item) for item in item_rows],
        )

    def _build_where_clause(
        self,
        *,
        source_id: str | None,
        service: str | None,
        task_type: str | None,
        status: str | None,
        keyword: str | None = None,
    ) -> tuple[str, list[str]]:
        """按可选筛选条件构造 WHERE 子句。"""
        conditions = ["1 = 1"]
        params: list[str] = []
        if source_id:
            conditions.append("source_id = %s")
            params.append(source_id)
        if service:
            conditions.append("service = %s")
            params.append(service)
        if task_type:
            conditions.append("task_type = %s")
            params.append(task_type)
        if status:
            conditions.append("status = %s")
            params.append(status)
        normalized_keyword = (keyword or "").strip()
        if normalized_keyword:
            like_keyword = f"%{normalized_keyword}%"
            conditions.append(
                "("
                "title LIKE %s OR summary LIKE %s OR task_id LIKE %s OR "
                "source_id LIKE %s OR tenant_id LIKE %s OR actor_user_name LIKE %s"
                ")",
            )
            params.extend([like_keyword] * 6)
        return " AND ".join(conditions), params


def get_async_task_query_service() -> AsyncTaskQueryService:
    """获取异步任务查询服务实例。"""
    return AsyncTaskQueryService()
