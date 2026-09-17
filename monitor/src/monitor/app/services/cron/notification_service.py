# -*- coding: utf-8 -*-
"""定时任务完成通知领取与状态回写服务。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field

from ...database import get_db_connection


class ClaimedCronNotification(BaseModel):
    """SWE 通知 worker 领取到的一条待通知执行记录。"""

    id: int
    job_id: str
    job_name: str = ""
    tenant_id: str
    source_id: str = ""
    notification_due_at: Optional[datetime] = None
    notification_timezone: str = ""
    notification_attempts: int = 0
    creator_user_id: str = ""
    task_chat_id: str = ""
    task_session_id: str = ""
    meta: str = ""
    job_meta: str = Field(default="", alias="job_meta")


class CronNotificationService:
    """负责待通知执行记录的原子领取和状态回写。"""

    async def claim_due_notifications(
        self,
        *,
        lock_owner: str,
        now_utc: datetime,
        limit: int,
        stale_lock_seconds: int = 600,
        source_ids: list[str] | None = None,
    ) -> list[ClaimedCronNotification]:
        ids = await self._claim_due_notification_ids(
            lock_owner=lock_owner,
            now_utc=now_utc,
            limit=limit,
            stale_lock_seconds=stale_lock_seconds,
            source_ids=source_ids,
        )
        if not ids:
            return []
        return await self._fetch_claimed_notifications(lock_owner, ids)

    async def _claim_due_notification_ids(
        self,
        *,
        lock_owner: str,
        now_utc: datetime,
        limit: int,
        stale_lock_seconds: int,
        source_ids: list[str] | None,
    ) -> list[int]:
        db = get_db_connection()
        normalized_now = _to_beijing_naive(now_utc)
        stale_before = normalized_now - timedelta(seconds=stale_lock_seconds)
        source_filter_join = ""
        source_filter_clause = ""
        source_filter_params: tuple[str, ...] = ()
        normalized_source_ids = _normalize_source_ids(source_ids)
        if normalized_source_ids:
            placeholders = ", ".join(["%s"] * len(normalized_source_ids))
            source_filter_join = (
                "LEFT JOIN swe_cron_jobs j ON e.job_id = j.id"
            )
            source_filter_clause = (
                f"AND (j.source_id IN ({placeholders}) "
                "OR j.source_id IS NULL "
                "OR j.source_id = '')"
            )
            source_filter_params = tuple(normalized_source_ids)

        async with db.acquire() as conn:
            await conn.begin()
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"""
                        SELECT e.id
                        FROM swe_cron_executions e
                        {source_filter_join}
                        WHERE e.status = 'success'
                          AND e.async_status = 'success'
                          AND e.need_notification = 1
                          AND e.notification_status = 'pending'
                          AND e.notification_due_at <= %s
                          AND (
                              e.notification_lock_owner IS NULL
                              OR e.notification_lock_owner = ''
                              OR e.notification_locked_at IS NULL
                              OR e.notification_locked_at < %s
                          )
                          {source_filter_clause}
                        ORDER BY e.notification_due_at, e.id
                        LIMIT %s
                        FOR UPDATE SKIP LOCKED
                        """,
                        (
                            normalized_now,
                            stale_before,
                            *source_filter_params,
                            limit,
                        ),
                    )
                    rows = await cur.fetchall()
                    ids = [int(row[0]) for row in rows]
                    if ids:
                        placeholders = ", ".join(["%s"] * len(ids))
                        await cur.execute(
                            f"""
                            UPDATE swe_cron_executions
                            SET notification_lock_owner = %s,
                                notification_locked_at = %s
                            WHERE id IN ({placeholders})
                            """,
                            (lock_owner, normalized_now, *ids),
                        )
                await conn.commit()
                return ids
            except Exception:
                await conn.rollback()
                raise

    async def _fetch_claimed_notifications(
        self,
        lock_owner: str,
        ids: list[int],
    ) -> list[ClaimedCronNotification]:
        db = get_db_connection()
        placeholders = ", ".join(["%s"] * len(ids))
        rows = await db.fetch_all(
            f"""
            SELECT
                e.id,
                e.job_id,
                e.job_name,
                e.tenant_id,
                COALESCE(j.source_id, '') AS source_id,
                e.notification_due_at,
                e.notification_timezone,
                e.notification_attempts,
                e.meta,
                j.creator_user_id,
                j.task_chat_id,
                j.task_session_id,
                j.meta AS job_meta
            FROM swe_cron_executions e
            LEFT JOIN swe_cron_jobs j ON e.job_id = j.id
            WHERE e.id IN ({placeholders})
              AND e.notification_lock_owner = %s
              AND e.status = 'success'
              AND e.async_status = 'success'
              AND e.need_notification = 1
              AND e.notification_status = 'pending'
            ORDER BY e.notification_due_at, e.id
            """,
            (*ids, lock_owner),
        )
        return [ClaimedCronNotification.model_validate(row) for row in rows]

    async def mark_sent(
        self,
        *,
        execution_id: int,
        sent_at: datetime,
    ) -> None:
        db = get_db_connection()
        await db.execute(
            """
            UPDATE swe_cron_executions
            SET notification_status = 'sent',
                notification_sent_at = %s,
                notification_error = '',
                notification_lock_owner = '',
                notification_locked_at = NULL
            WHERE id = %s
            """,
            (_to_beijing_naive(sent_at), execution_id),
        )

    async def mark_failed(
        self,
        *,
        execution_id: int,
        error: str,
        max_attempts: int,
    ) -> None:
        db = get_db_connection()
        await db.execute(
            """
            UPDATE swe_cron_executions
            SET notification_status =
                    CASE WHEN notification_attempts + 1 >= %s
                    THEN 'failed' ELSE 'pending' END,
                notification_attempts = notification_attempts + 1,
                notification_error = %s,
                notification_lock_owner = '',
                notification_locked_at = NULL
            WHERE id = %s
            """,
            (max_attempts, error[:2048], execution_id),
        )


def _to_beijing_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)


def _normalize_source_ids(source_ids: list[str] | None) -> list[str]:
    normalized = []
    for source_id in source_ids or []:
        value = str(source_id or "").strip()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


_notification_service: Optional[CronNotificationService] = None


def get_cron_notification_service() -> CronNotificationService:
    """获取通知状态服务单例。"""
    global _notification_service
    if _notification_service is None:
        _notification_service = CronNotificationService()
    return _notification_service
