# -*- coding: utf-8 -*-
"""定时任务广播分发进度存储。"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Any, Literal, cast

from ..async_tasks.store import AsyncTaskStore

BroadcastTaskStatus = Literal["running", "completed", "failed"]
BroadcastTargetStatus = Literal["pending", "running", "succeeded", "failed"]

logger = logging.getLogger(__name__)

_TASK_TABLE = "swe_cron_broadcast_tasks"
_ITEM_TABLE = "swe_cron_broadcast_task_items"
_UNAVAILABLE_PREFIX = "cron broadcast task storage unavailable"


@dataclass(slots=True)
class CronBroadcastTaskSnapshot:
    """一次定时任务广播分发的进度快照。"""

    task_id: str
    agent_id: str
    source_id: str
    tenant_id: str
    job_id: str
    target_key: str
    status: BroadcastTaskStatus = "running"
    tenant_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    results: list[dict[str, Any]] = field(default_factory=list)
    failure_summary: str | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class _TargetItem:
    tenant_id: str
    status: BroadcastTargetStatus = "pending"
    result: dict[str, Any] | None = None


class CronBroadcastTaskStoreUnavailable(RuntimeError):
    """定时任务广播分发进度存储不可用。"""


class CronBroadcastTaskStore:
    """读写定时任务广播分发进度。"""

    def __init__(self, db: Any | None = None):
        """初始化存储；无数据库时退化为进程内存储。"""
        self.db = db
        self._async_task_store = AsyncTaskStore(db) if db is not None else None
        self._tasks: dict[str, CronBroadcastTaskSnapshot] = {}
        self._items: dict[str, dict[str, _TargetItem]] = {}

    @property
    def is_available(self) -> bool:
        """返回当前数据库连接是否可用。"""
        return self.db is not None and bool(
            getattr(self.db, "is_connected", False),
        )

    async def initialize(self) -> None:
        """幂等初始化广播任务进度表。"""
        if not self.is_available:
            return
        await self._call_db(
            "initialize tasks table",
            self.db.execute,
            _CREATE_TASK_TABLE_SQL,
        )
        await self._call_db(
            "initialize task items table",
            self.db.execute,
            _CREATE_ITEM_TABLE_SQL,
        )

    async def start_task(
        self,
        *,
        agent_id: str,
        source_id: str,
        tenant_id: str,
        job_id: str,
        target_tenant_ids: list[str],
        target_names: dict[str, str | None] | None = None,
        actor_user_id: str | None = None,
        actor_user_name: str | None = None,
    ) -> tuple[CronBroadcastTaskSnapshot, bool]:
        """创建或复用同一源任务和目标集合下仍在运行的广播任务。"""
        targets = _normalize_targets(target_tenant_ids)
        target_key = _target_key(targets)
        if not self.is_available:
            return self._start_memory_task(
                agent_id=agent_id,
                source_id=source_id,
                tenant_id=tenant_id,
                job_id=job_id,
                target_key=target_key,
                targets=targets,
            )
        return await self._start_db_task(
            agent_id=agent_id,
            source_id=source_id,
            tenant_id=tenant_id,
            job_id=job_id,
            target_key=target_key,
            targets=targets,
            target_names=target_names,
            actor_user_id=actor_user_id,
            actor_user_name=actor_user_name,
        )

    async def get_task(
        self,
        task_id: str,
    ) -> CronBroadcastTaskSnapshot | None:
        """按任务 ID 读取广播进度。"""
        if not self.is_available:
            task = self._tasks.get(task_id)
            return self._build_memory_snapshot(task) if task else None
        return await self._get_db_task(task_id)

    async def mark_running(self, task_id: str) -> None:
        """将广播任务标记为运行中。"""
        if not self.is_available:
            task = self._tasks.get(task_id)
            if task is not None:
                task.status = "running"
                task.updated_at = datetime.now()
            return
        await self._call_db(
            "mark task running",
            self.db.execute,
            f"""
                UPDATE {_TASK_TABLE}
                SET status = 'running',
                    updated_at = CURRENT_TIMESTAMP
                WHERE task_id = %s
            """,
            (task_id,),
        )
        await self._mirror_async_task_running(task_id)

    async def mark_target_running(
        self,
        task_id: str,
        tenant_id: str,
    ) -> None:
        """标记某个目标租户开始处理。"""
        if not self.is_available:
            item = self._items.get(task_id, {}).get(tenant_id)
            if item is not None and item.status == "pending":
                item.status = "running"
                self._touch_memory_task(task_id)
            return
        await self._call_db(
            "mark target running",
            self.db.execute,
            f"""
                INSERT INTO {_ITEM_TABLE} (
                    task_id, tenant_id, status, result_json
                )
                VALUES (%s, %s, 'running', NULL)
                ON DUPLICATE KEY UPDATE
                    status = CASE
                        WHEN status = 'pending' THEN 'running'
                        ELSE status
                    END,
                    updated_at = CURRENT_TIMESTAMP
            """,
            (task_id, tenant_id),
        )
        await self._mirror_async_task_item_running(task_id, tenant_id)

    async def record_target_result(
        self,
        task_id: str,
        result: dict[str, Any],
    ) -> None:
        """记录某个目标租户的最终分发结果。"""
        tenant_id = str(result.get("tenant_id") or "")
        if not tenant_id:
            return
        status: BroadcastTargetStatus = (
            "succeeded" if bool(result.get("success")) else "failed"
        )
        if not self.is_available:
            items = self._items.get(task_id)
            if items is None:
                return
            item = items.get(tenant_id)
            if item is None:
                item = _TargetItem(tenant_id=tenant_id)
                items[tenant_id] = item
            item.status = status
            item.result = dict(result)
            self._touch_memory_task(task_id)
            return
        await self._call_db(
            "record target result",
            self.db.execute,
            f"""
                INSERT INTO {_ITEM_TABLE} (
                    task_id, tenant_id, status, result_json
                )
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    status = VALUES(status),
                    result_json = VALUES(result_json),
                    updated_at = CURRENT_TIMESTAMP
            """,
            (
                task_id,
                tenant_id,
                status,
                json.dumps(result, ensure_ascii=False),
            ),
        )
        await self._mirror_async_task_item_result(task_id, result)

    async def finish_task(self, task_id: str) -> None:
        """根据目标结果汇总并结束广播任务。"""
        if not self.is_available:
            task = self._tasks.get(task_id)
            if task is None:
                return
            snapshot = self._build_memory_snapshot(task)
            task.status = "failed" if snapshot.failed_count else "completed"
            task.completed_count = snapshot.completed_count
            task.failed_count = snapshot.failed_count
            task.results = snapshot.results
            task.updated_at = datetime.now()
            return
        snapshot = await self._get_db_task(task_id)
        if snapshot is None:
            return
        status = "failed" if snapshot.failed_count else "completed"
        await self._call_db(
            "finish task",
            self.db.execute,
            f"""
                UPDATE {_TASK_TABLE}
                SET status = %s,
                    claim_key = NULL,
                    completed_count = %s,
                    failed_count = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE task_id = %s
            """,
            (
                status,
                snapshot.completed_count,
                snapshot.failed_count,
                task_id,
            ),
        )
        await self._mirror_async_task_finished(
            task_id=task_id,
            done_count=snapshot.completed_count,
            failed_count=snapshot.failed_count,
            results=snapshot.results,
            failure_summary=snapshot.failure_summary,
        )

    async def record_task_failed(
        self,
        task_id: str,
        failure_summary: str,
    ) -> None:
        """记录任务级失败，用于目标循环外的异常。"""
        if not self.is_available:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.status = "failed"
            task.failure_summary = failure_summary
            task.updated_at = datetime.now()
            return
        await self._call_db(
            "record task failed",
            self.db.execute,
            f"""
                UPDATE {_TASK_TABLE}
                SET status = 'failed',
                    claim_key = NULL,
                    failure_summary = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE task_id = %s
            """,
            (failure_summary, task_id),
        )
        await self._mirror_async_task_failed(task_id, failure_summary)

    def _start_memory_task(
        self,
        *,
        agent_id: str,
        source_id: str,
        tenant_id: str,
        job_id: str,
        target_key: str,
        targets: list[str],
        actor_user_id: str | None = None,
        actor_user_name: str | None = None,
    ) -> tuple[CronBroadcastTaskSnapshot, bool]:
        for task in self._tasks.values():
            if (
                task.agent_id == agent_id
                and task.source_id == source_id
                and task.tenant_id == tenant_id
                and task.job_id == job_id
                and task.status == "running"
            ):
                snapshot = self._build_memory_snapshot(task)
                return snapshot, True

        task_id = str(uuid.uuid4())
        snapshot = CronBroadcastTaskSnapshot(
            task_id=task_id,
            agent_id=agent_id,
            source_id=source_id,
            tenant_id=tenant_id,
            job_id=job_id,
            target_key=target_key,
            status="running",
            tenant_count=len(targets),
            updated_at=datetime.now(),
        )
        self._tasks[task_id] = snapshot
        self._items[task_id] = {
            target: _TargetItem(tenant_id=target) for target in targets
        }
        return self._build_memory_snapshot(snapshot), False

    async def _start_db_task(
        self,
        *,
        agent_id: str,
        source_id: str,
        tenant_id: str,
        job_id: str,
        target_key: str,
        targets: list[str],
        target_names: dict[str, str | None] | None,
        actor_user_id: str | None,
        actor_user_name: str | None,
    ) -> tuple[CronBroadcastTaskSnapshot, bool]:
        claim_key = _claim_key(
            agent_id,
            source_id,
            tenant_id,
            job_id,
        )
        for _attempt in range(2):
            running_snapshot = await self._find_running_db_task(claim_key)
            if running_snapshot is not None:
                return running_snapshot, True

            task_id = str(uuid.uuid4())
            inserted = await self._insert_db_task(
                task_id=task_id,
                agent_id=agent_id,
                source_id=source_id,
                tenant_id=tenant_id,
                job_id=job_id,
                target_key=target_key,
                claim_key=claim_key,
                tenant_count=len(targets),
            )
            if inserted:
                await self._mirror_async_task_started(
                    task_id=task_id,
                    source_id=source_id,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    target_ids=targets,
                    target_names=target_names,
                    actor_user_id=actor_user_id,
                    actor_user_name=actor_user_name,
                )
                return (
                    CronBroadcastTaskSnapshot(
                        task_id=task_id,
                        agent_id=agent_id,
                        source_id=source_id,
                        tenant_id=tenant_id,
                        job_id=job_id,
                        target_key=target_key,
                        status="running",
                        tenant_count=len(targets),
                        updated_at=datetime.now(),
                    ),
                    False,
                )

            running_snapshot = await self._find_running_db_task(claim_key)
            if running_snapshot is not None:
                return running_snapshot, True

        raise CronBroadcastTaskStoreUnavailable(
            "cron broadcast task storage unavailable: "
            "running claim insert was ignored",
        )

    async def _insert_db_task(
        self,
        *,
        task_id: str,
        agent_id: str,
        source_id: str,
        tenant_id: str,
        job_id: str,
        target_key: str,
        claim_key: str,
        tenant_count: int,
    ) -> Any:
        return await self._call_db(
            "insert task",
            self.db.execute,
            f"""
                INSERT IGNORE INTO {_TASK_TABLE} (
                    task_id, agent_id, source_id, tenant_id, job_id,
                    target_key, claim_key, status, tenant_count,
                    completed_count, failed_count, failure_summary
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, 'running', %s, 0, 0, NULL
                )
            """,
            (
                task_id,
                agent_id,
                source_id,
                tenant_id,
                job_id,
                target_key,
                claim_key,
                tenant_count,
            ),
        )

    def _build_memory_snapshot(
        self,
        task: CronBroadcastTaskSnapshot,
    ) -> CronBroadcastTaskSnapshot:
        items = list(self._items.get(task.task_id, {}).values())
        results = [
            dict(item.result)
            for item in items
            if item.status in {"succeeded", "failed"} and item.result
        ]
        failed_count = sum(1 for item in items if item.status == "failed")
        completed_count = sum(
            1 for item in items if item.status in {"succeeded", "failed"}
        )
        return CronBroadcastTaskSnapshot(
            task_id=task.task_id,
            agent_id=task.agent_id,
            source_id=task.source_id,
            tenant_id=task.tenant_id,
            job_id=task.job_id,
            target_key=task.target_key,
            status=task.status,
            tenant_count=task.tenant_count,
            completed_count=completed_count,
            failed_count=failed_count,
            results=results,
            failure_summary=task.failure_summary,
            updated_at=task.updated_at,
        )

    async def _get_db_task(
        self,
        task_id: str,
    ) -> CronBroadcastTaskSnapshot | None:
        row = await self._call_db(
            "get task",
            self.db.fetch_one,
            f"""
                SELECT task_id, agent_id, source_id, tenant_id, job_id,
                       target_key, status, tenant_count, completed_count,
                       failed_count, failure_summary, updated_at
                FROM {_TASK_TABLE}
                WHERE task_id = %s
            """,
            (task_id,),
        )
        if not row:
            return None
        item_rows = await self._call_db(
            "list task items",
            self.db.fetch_all,
            f"""
                SELECT tenant_id, status, result_json
                FROM {_ITEM_TABLE}
                WHERE task_id = %s
                ORDER BY tenant_id ASC
            """,
            (task_id,),
        )
        return _db_snapshot(row, item_rows)

    async def _find_running_db_task(
        self,
        claim_key: str,
    ) -> CronBroadcastTaskSnapshot | None:
        row = await self._call_db(
            "find running task",
            self.db.fetch_one,
            f"""
                SELECT task_id
                FROM {_TASK_TABLE}
                WHERE claim_key = %s
                  AND status = 'running'
                ORDER BY created_at DESC
                LIMIT 1
            """,
            (claim_key,),
        )
        if not row:
            return None
        task_id = str(row.get("task_id") or "")
        return await self._get_db_task(task_id) if task_id else None

    async def get_running_task(
        self,
        *,
        agent_id: str,
        source_id: str,
        tenant_id: str,
        job_id: str,
    ) -> CronBroadcastTaskSnapshot | None:
        """读取同一源定时任务当前仍在运行的广播分发任务。"""
        if not self.is_available:
            for task in self._tasks.values():
                if (
                    task.agent_id == agent_id
                    and task.source_id == source_id
                    and task.tenant_id == tenant_id
                    and task.job_id == job_id
                    and task.status == "running"
                ):
                    return self._build_memory_snapshot(task)
            return None
        return await self._find_running_db_task(
            _claim_key(agent_id, source_id, tenant_id, job_id),
        )

    def _touch_memory_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is not None:
            task.updated_at = datetime.now()

    async def _call_db(
        self,
        operation: str,
        db_call: Any,
        *args: Any,
    ) -> Any:
        try:
            return await db_call(*args)
        except Exception as exc:
            raise CronBroadcastTaskStoreUnavailable(
                f"{_UNAVAILABLE_PREFIX}: {operation} failed: {exc}",
            ) from exc

    async def _mirror_async_task_started(
        self,
        *,
        task_id: str,
        source_id: str,
        tenant_id: str,
        job_id: str,
        target_ids: list[str],
        target_names: dict[str, str | None] | None = None,
        actor_user_id: str | None = None,
        actor_user_name: str | None = None,
    ) -> None:
        """同步统一异步任务主记录。"""
        if self._async_task_store is None:
            return
        try:
            await self._async_task_store.start_task(
                task_id=task_id,
                service="swe",
                task_type="cron.broadcast.distribute",
                source_id=source_id,
                actor_user_id=actor_user_id,
                actor_user_name=actor_user_name,
                target_ids=target_ids,
                target_names=target_names,
            )
        except Exception:
            logger.warning(
                "Failed to mirror cron broadcast task %s into async_tasks",
                task_id,
                exc_info=True,
            )

    async def _mirror_async_task_item_running(
        self,
        task_id: str,
        tenant_id: str,
    ) -> None:
        """同步统一异步任务明细的运行状态。"""
        if self._async_task_store is None:
            return
        try:
            await self._async_task_store.mark_item_running(
                task_id=task_id,
                target_id=tenant_id,
            )
        except Exception:
            logger.warning(
                "Failed to mirror cron broadcast item running: task_id=%s tenant_id=%s",
                task_id,
                tenant_id,
                exc_info=True,
            )

    async def _mirror_async_task_running(self, task_id: str) -> None:
        """同步统一异步任务运行状态。"""
        if self._async_task_store is None:
            return
        try:
            await self._async_task_store.mark_running(task_id)
        except Exception:
            logger.warning(
                "Failed to mirror cron broadcast task running: task_id=%s",
                task_id,
                exc_info=True,
            )

    async def _mirror_async_task_item_result(
        self,
        task_id: str,
        result: dict[str, Any],
    ) -> None:
        """同步统一异步任务明细结果。"""
        if self._async_task_store is None:
            return
        tenant_id = str(result.get("tenant_id") or "")
        if not tenant_id:
            return
        try:
            await self._async_task_store.record_item_result(
                task_id=task_id,
                target_id=tenant_id,
                success=bool(result.get("success")),
                result=result,
                error_message=str(result.get("error") or "") or None,
            )
        except Exception:
            logger.warning(
                "Failed to mirror cron broadcast item result: task_id=%s tenant_id=%s",
                task_id,
                tenant_id,
                exc_info=True,
            )

    async def _mirror_async_task_finished(
        self,
        *,
        task_id: str,
        done_count: int,
        failed_count: int,
        results: list[dict[str, Any]],
        failure_summary: str | None,
    ) -> None:
        """同步统一异步任务完成状态。"""
        if self._async_task_store is None:
            return
        async_task_status = "succeeded"
        succeeded_count = max(done_count - failed_count, 0)
        if failed_count > 0 and succeeded_count > 0:
            async_task_status = "partial_failed"
        elif failed_count > 0:
            async_task_status = "failed"
        try:
            await self._async_task_store.finish_task(
                task_id=task_id,
                status=async_task_status,
                done_count=done_count,
                failed_count=failed_count,
                error_message=failure_summary,
                result=results,
            )
        except Exception:
            logger.warning(
                "Failed to mirror cron broadcast task finished: task_id=%s",
                task_id,
                exc_info=True,
            )

    async def _mirror_async_task_failed(
        self,
        task_id: str,
        failure_summary: str,
    ) -> None:
        """同步统一异步任务失败状态。"""
        if self._async_task_store is None:
            return
        try:
            await self._async_task_store.fail_task(task_id, failure_summary)
        except Exception:
            logger.warning(
                "Failed to mirror cron broadcast task failed: task_id=%s",
                task_id,
                exc_info=True,
            )


def _normalize_targets(target_tenant_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    targets: list[str] = []
    for raw_tenant_id in target_tenant_ids:
        tenant_id = str(raw_tenant_id or "").strip()
        if not tenant_id or tenant_id in seen:
            continue
        seen.add(tenant_id)
        targets.append(tenant_id)
    return targets


def _target_key(targets: list[str]) -> str:
    return json.dumps(
        sorted(targets),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _claim_key(
    agent_id: str,
    source_id: str,
    tenant_id: str,
    job_id: str,
) -> str:
    raw_key = "\0".join([agent_id, source_id, tenant_id, job_id])
    return sha256(raw_key.encode("utf-8")).hexdigest()


def _db_snapshot(
    row: dict[str, Any],
    item_rows: list[dict[str, Any]],
) -> CronBroadcastTaskSnapshot:
    results: list[dict[str, Any]] = []
    completed_count = 0
    failed_count = 0
    for item in item_rows:
        status = str(item.get("status") or "")
        if status in {"succeeded", "failed"}:
            completed_count += 1
        if status == "failed":
            failed_count += 1
        result = _decode_result(item.get("result_json"))
        if result is not None:
            results.append(result)
    return CronBroadcastTaskSnapshot(
        task_id=str(row.get("task_id") or ""),
        agent_id=str(row.get("agent_id") or ""),
        source_id=str(row.get("source_id") or ""),
        tenant_id=str(row.get("tenant_id") or ""),
        job_id=str(row.get("job_id") or ""),
        target_key=str(row.get("target_key") or ""),
        status=_task_status(row.get("status")),
        tenant_count=int(row.get("tenant_count") or len(item_rows)),
        completed_count=completed_count,
        failed_count=failed_count,
        results=results,
        failure_summary=row.get("failure_summary"),
        updated_at=row.get("updated_at"),
    )


def _decode_result(value: Any) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _task_status(value: Any) -> BroadcastTaskStatus:
    text = str(value or "").strip()
    if text in {"running", "completed", "failed"}:
        return cast(BroadcastTaskStatus, text)
    return "running"


_CREATE_TASK_TABLE_SQL = f"""
    CREATE TABLE IF NOT EXISTS {_TASK_TABLE} (
        task_id VARCHAR(64) NOT NULL,
        agent_id VARCHAR(128) NOT NULL,
        source_id VARCHAR(128) NOT NULL,
        tenant_id VARCHAR(128) NOT NULL,
        job_id VARCHAR(128) NOT NULL,
        target_key VARCHAR(1024) NOT NULL,
        claim_key VARCHAR(64) NULL,
        status VARCHAR(20) NOT NULL,
        tenant_count INT NOT NULL DEFAULT 0,
        completed_count INT NOT NULL DEFAULT 0,
        failed_count INT NOT NULL DEFAULT 0,
        failure_summary TEXT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (task_id),
        UNIQUE KEY uniq_broadcast_task_claim (claim_key),
        INDEX idx_broadcast_task_running (
            agent_id, source_id, tenant_id, job_id, target_key, status
        )
    )
"""

_CREATE_ITEM_TABLE_SQL = f"""
    CREATE TABLE IF NOT EXISTS {_ITEM_TABLE} (
        task_id VARCHAR(64) NOT NULL,
        tenant_id VARCHAR(128) NOT NULL,
        status VARCHAR(20) NOT NULL,
        result_json MEDIUMTEXT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (task_id, tenant_id)
    )
"""
