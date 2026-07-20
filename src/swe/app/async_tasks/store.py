# -*- coding: utf-8 -*-
"""统一异步任务表的本地写入器。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ...database.connection import DatabaseConnection


def _json_dumps(value: Any) -> str | None:
    """将结果对象序列化为数据库 JSON 字段。"""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


class AsyncTaskStore:
    """SWE 服务内的异步任务写入器。

    第一版采用层级一共享方式：SWE 直接写统一表，Monitor 只读查询。
    """

    def __init__(self, db: DatabaseConnection) -> None:
        """初始化写入器。

        Args:
            db: SWE 服务当前数据库连接
        """
        self.db = db

    async def start_task(
        self,
        *,
        task_id: str,
        service: str,
        task_type: str,
        title: str,
        target_ids: list[str],
        summary: str | None = None,
        source_id: str | None = None,
        tenant_id: str | None = None,
        actor_user_id: str | None = None,
        actor_user_name: str | None = None,
    ) -> None:
        """创建主任务并批量写入目标明细。"""
        insert_task_sql = """
            INSERT INTO swe_async_tasks (
                task_id, service, task_type, status, title, summary,
                source_id, tenant_id, actor_user_id, actor_user_name,
                target_count, done_count, failed_count
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0)
        """
        await self.db.execute(
            insert_task_sql,
            (
                task_id,
                service,
                task_type,
                "queued",
                title,
                summary,
                source_id,
                tenant_id,
                actor_user_id,
                actor_user_name,
                len(target_ids),
            ),
        )
        insert_items_sql = """
            INSERT INTO swe_async_task_items (
                task_id, target_id, target_name, status, error_message,
                result_json
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        await self.db.execute_many(
            insert_items_sql,
            [
                (task_id, target_id, None, "queued", None, None)
                for target_id in target_ids
            ],
        )

    async def mark_running(self, task_id: str) -> None:
        """将主任务标记为运行中。"""
        await self.db.execute(
            """
            UPDATE swe_async_tasks
            SET status = %s
            WHERE task_id = %s
            """,
            ("running", task_id),
        )

    async def mark_item_running(
        self,
        *,
        task_id: str,
        target_id: str,
    ) -> None:
        """将单个目标标记为运行中。"""
        await self.db.execute(
            """
            UPDATE swe_async_task_items
            SET status = %s
            WHERE task_id = %s AND target_id = %s
            """,
            ("running", task_id, target_id),
        )

    async def record_item_result(
        self,
        *,
        task_id: str,
        target_id: str,
        success: bool,
        result: Any = None,
        error_message: str | None = None,
    ) -> None:
        """记录单个目标的执行结果。"""
        status = "succeeded" if success else "failed"
        await self.db.execute(
            """
            UPDATE swe_async_task_items
            SET status = %s,
                result_json = %s,
                error_message = %s
            WHERE task_id = %s AND target_id = %s
            """,
            (
                status,
                _json_dumps(result),
                error_message,
                task_id,
                target_id,
            ),
        )

    async def finish_task(
        self,
        *,
        task_id: str,
        status: str,
        done_count: int,
        failed_count: int,
        error_message: str | None = None,
        result: Any = None,
        finished_at: datetime | None = None,
    ) -> None:
        """汇总更新主任务最终状态。"""
        await self.db.execute(
            """
            UPDATE swe_async_tasks
            SET status = %s,
                done_count = %s,
                failed_count = %s,
                error_message = %s,
                result_json = %s,
                finished_at = %s
            WHERE task_id = %s
            """,
            (
                status,
                done_count,
                failed_count,
                error_message,
                _json_dumps(result),
                finished_at or datetime.now(),
                task_id,
            ),
        )

    async def fail_task(
        self,
        task_id: str,
        error_message: str,
    ) -> None:
        """在任务级异常时直接标记主任务失败。"""
        await self.finish_task(
            task_id=task_id,
            status="failed",
            done_count=0,
            failed_count=0,
            error_message=error_message,
        )
