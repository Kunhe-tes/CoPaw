# -*- coding: utf-8 -*-
"""Source 级系统任务绑定存储。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from .store import SourceSystemConfigStoreUnavailable

_STORAGE_UNAVAILABLE_PREFIX = "source system task binding storage unavailable"


@dataclass(frozen=True, slots=True)
class SourceSystemTaskBinding:
    """Source 级系统任务与外部调度任务的绑定记录。"""

    source_id: str
    task_type: str
    external_job_id: str
    cron: str
    enabled: bool
    scheduler_tenant_id: str | None = None
    scheduler_scope_id: str | None = None
    scheduler_from_id: str | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None

    def replace(self, **changes: Any) -> "SourceSystemTaskBinding":
        """返回带有局部字段更新的新绑定对象。"""
        return replace(self, **changes)


class SourceSystemTaskBindingStore:
    """按 source_id 与 task_type 读写系统任务绑定。"""

    def __init__(self, db: Any | None = None):
        """初始化绑定存储。"""
        self.db = db

    @property
    def is_available(self) -> bool:
        """返回当前存储是否可用。"""
        return self.db is not None and bool(
            getattr(self.db, "is_connected", False),
        )

    def _require_db(self) -> Any:
        """校验 DB 可用性并返回连接对象。"""
        if not self.is_available:
            raise SourceSystemConfigStoreUnavailable(
                f"{_STORAGE_UNAVAILABLE_PREFIX}: db is not connected",
            )
        return self.db

    async def _call_db(
        self,
        operation: str,
        db_call: Any,
        *args: Any,
    ) -> Any:
        """执行数据库调用并统一包装底层异常。"""
        try:
            return await db_call(*args)
        except SourceSystemConfigStoreUnavailable:
            raise
        except Exception as exc:
            raise SourceSystemConfigStoreUnavailable(
                f"{_STORAGE_UNAVAILABLE_PREFIX}: {operation} failed: {exc}",
            ) from exc

    async def get_binding(
        self,
        source_id: str,
        task_type: str,
    ) -> SourceSystemTaskBinding | None:
        """读取指定 source 系统任务绑定。"""
        db = self._require_db()
        query = """
            SELECT
                source_id,
                task_type,
                external_job_id,
                cron,
                enabled,
                scheduler_tenant_id,
                scheduler_scope_id,
                scheduler_from_id,
                updated_by,
                updated_at
            FROM swe_source_system_task_binding
            WHERE source_id = %s AND task_type = %s
        """
        row = await self._call_db(
            "fetch binding",
            db.fetch_one,
            query,
            (source_id, task_type),
        )
        if row is None:
            return None
        return self._row_to_binding(row)

    async def upsert_binding(
        self,
        binding: SourceSystemTaskBinding,
    ) -> SourceSystemTaskBinding:
        """创建或更新 source 系统任务绑定。"""
        db = self._require_db()
        query = """
            INSERT INTO swe_source_system_task_binding (
                source_id,
                task_type,
                external_job_id,
                cron,
                enabled,
                scheduler_tenant_id,
                scheduler_scope_id,
                scheduler_from_id,
                updated_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                external_job_id = VALUES(external_job_id),
                cron = VALUES(cron),
                enabled = VALUES(enabled),
                scheduler_tenant_id = VALUES(scheduler_tenant_id),
                scheduler_scope_id = VALUES(scheduler_scope_id),
                scheduler_from_id = VALUES(scheduler_from_id),
                updated_by = VALUES(updated_by),
                updated_at = CURRENT_TIMESTAMP
        """
        await self._call_db(
            "upsert binding",
            db.execute,
            query,
            (
                binding.source_id,
                binding.task_type,
                binding.external_job_id,
                binding.cron,
                int(binding.enabled),
                binding.scheduler_tenant_id,
                binding.scheduler_scope_id,
                binding.scheduler_from_id,
                binding.updated_by,
            ),
        )
        persisted = await self.get_binding(binding.source_id, binding.task_type)
        if persisted is None:
            raise ValueError(
                "source system task binding upsert did not return row: "
                f"{binding.source_id}/{binding.task_type}",
            )
        return persisted

    def _row_to_binding(
        self,
        row: dict[str, Any],
    ) -> SourceSystemTaskBinding:
        """将数据库行转换为绑定记录。"""
        return SourceSystemTaskBinding(
            source_id=row["source_id"],
            task_type=row["task_type"],
            external_job_id=row["external_job_id"],
            cron=row["cron"],
            enabled=bool(row["enabled"]),
            scheduler_tenant_id=row.get("scheduler_tenant_id"),
            scheduler_scope_id=row.get("scheduler_scope_id"),
            scheduler_from_id=row.get("scheduler_from_id"),
            updated_by=row.get("updated_by"),
            updated_at=row.get("updated_at"),
        )
