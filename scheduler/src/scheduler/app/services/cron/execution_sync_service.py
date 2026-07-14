# -*- coding: utf-8 -*-
"""Persist Scheduler-managed SWE execution feedback."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from scheduler.app.database import get_db_connection
from scheduler.app.models.cron import ExecutionSyncRequest

logger = logging.getLogger(__name__)

_BEIJING_TZ = ZoneInfo("Asia/Shanghai")
INPUT_SNAPSHOT_MAX_LENGTH = 16000
ERROR_MESSAGE_MAX_LENGTH = 2048
OUTPUT_PREVIEW_MAX_LENGTH = 512
META_MAX_LENGTH = 2048


def _truncate_string(text: str | None, max_length: int) -> str:
    if text is None:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _get_beijing_now() -> datetime:
    return datetime.now(_BEIJING_TZ).replace(tzinfo=None)


def _to_beijing_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(_BEIJING_TZ).replace(tzinfo=None)


def _positive_int(value: object, default: Optional[int] = None) -> Optional[int]:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _extract_dispatch_identity_columns(
    raw_meta: str | None,
) -> tuple[Optional[int], str, Optional[int]]:
    if not raw_meta:
        return None, "", None
    try:
        meta = json.loads(raw_meta)
    except json.JSONDecodeError:
        return None, "", None
    if not isinstance(meta, dict):
        return None, "", None
    dispatch_meta = meta.get("cron_dispatch")
    if not isinstance(dispatch_meta, dict):
        return None, "", None
    intent_id = _positive_int(dispatch_meta.get("intent_id"))
    batch_id = str(dispatch_meta.get("batch_id") or "").strip()
    dispatch_attempt = _positive_int(
        dispatch_meta.get("dispatch_attempt"),
        1,
    )
    return intent_id, batch_id, dispatch_attempt


class ExecutionSyncService:
    """Minimal execution persistence used by Scheduler feedback APIs."""

    async def record_execution(
        self,
        request: ExecutionSyncRequest,
    ) -> Optional[int]:
        db = get_db_connection()
        now = _get_beijing_now()
        input_snapshot = _truncate_string(
            request.input_snapshot,
            INPUT_SNAPSHOT_MAX_LENGTH,
        )
        error_message = _truncate_string(
            request.error_message,
            ERROR_MESSAGE_MAX_LENGTH,
        )
        output_preview = _truncate_string(
            request.output_preview,
            OUTPUT_PREVIEW_MAX_LENGTH,
        )
        (
            dispatch_intent_id,
            dispatch_batch_id,
            dispatch_attempt,
        ) = _extract_dispatch_identity_columns(request.meta)
        meta = _truncate_string(request.meta, META_MAX_LENGTH)

        async with db.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO swe_cron_executions (
                        job_id, job_name, tenant_id,
                        scheduled_time, actual_time, end_time, duration_ms,
                        status, error_message,
                        instance_id, executor_leader, is_manual,
                        trace_id, session_id,
                        input_snapshot, output_preview, meta,
                        dispatch_intent_id, dispatch_batch_id,
                        dispatch_attempt,
                        notification_status, notification_due_at,
                        notification_timezone, is_read, read_at, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s
                    )
                    """,
                    (
                        request.job_id,
                        request.job_name,
                        request.tenant_id,
                        request.scheduled_time,
                        request.actual_time,
                        request.end_time,
                        request.duration_ms,
                        request.status,
                        error_message,
                        request.instance_id,
                        request.executor_leader,
                        request.is_manual,
                        request.trace_id,
                        request.session_id,
                        input_snapshot,
                        output_preview,
                        meta,
                        dispatch_intent_id,
                        dispatch_batch_id,
                        dispatch_attempt,
                        request.notification_status,
                        _to_beijing_naive(request.notification_due_at),
                        request.notification_timezone,
                        request.is_read,
                        _to_beijing_naive(request.read_at),
                        now,
                    ),
                )
                execution_id = getattr(cur, "lastrowid", None)

        logger.info(
            "Scheduler recorded execution: job_id=%s execution_id=%s status=%s",
            request.job_id,
            execution_id,
            request.status,
        )
        return int(execution_id) if execution_id is not None else None

    async def find_execution_by_dispatch_identity(
        self,
        *,
        intent_id: int,
        batch_id: str,
        dispatch_attempt: int,
    ) -> Optional[int]:
        if intent_id <= 0 or not batch_id or dispatch_attempt <= 0:
            return None
        db = get_db_connection()
        row = await db.fetch_one(
            """
            SELECT id
            FROM swe_cron_executions
            WHERE dispatch_intent_id = %s
              AND dispatch_batch_id = %s
              AND dispatch_attempt = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (intent_id, batch_id, dispatch_attempt),
        )
        if not row:
            return None
        try:
            return int(row.get("id"))
        except (TypeError, ValueError):
            return None


_execution_sync_service: ExecutionSyncService | None = None


def get_execution_sync_service() -> ExecutionSyncService:
    global _execution_sync_service

    if _execution_sync_service is None:
        _execution_sync_service = ExecutionSyncService()
    return _execution_sync_service
