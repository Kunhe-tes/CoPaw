# -*- coding: utf-8 -*-
"""工具审批审计存储。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_REQUEST_TABLE = "swe_tool_approval_requests"
_EVENT_TABLE = "swe_tool_approval_events"


class ApprovalAuditStore:
    """记录审批请求当前状态与过程事件。"""

    def __init__(self, db: Any | None = None):
        self.db = db

    @property
    def is_available(self) -> bool:
        """返回当前数据库连接是否可用。"""
        return self.db is not None and bool(
            getattr(self.db, "is_connected", False),
        )

    async def initialize(self) -> None:
        """幂等初始化审批审计表。"""
        if not self.is_available:
            return
        await self.db.execute(_CREATE_REQUEST_TABLE)
        await self.db.execute(_CREATE_EVENT_TABLE)

    async def upsert_request(
        self,
        pending: Any,
        *,
        source_channel: str | None = None,
        source_user_id: str | None = None,
        source_message_id: str | None = None,
        consumed_at: float | None = None,
    ) -> None:
        """写入或更新审批主记录。"""
        if not self.is_available:
            return
        params = _request_params(
            pending,
            source_channel=source_channel,
            source_user_id=source_user_id,
            source_message_id=source_message_id,
            consumed_at=consumed_at,
        )
        await self._execute("upsert approval request", _UPSERT_REQUEST, params)

    async def add_event(
        self,
        pending: Any,
        event_type: str,
        *,
        status: str | None = None,
        actor_channel: str | None = None,
        actor_user_id: str | None = None,
        source_message_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """追加审批过程事件。"""
        if not self.is_available:
            return
        await self._execute(
            "insert approval event",
            _INSERT_EVENT,
            (
                getattr(pending, "request_id", ""),
                event_type,
                status or getattr(pending, "status", None),
                actor_channel,
                actor_user_id,
                source_message_id,
                _json_dumps(details or {}),
            ),
        )

    async def _execute(
        self,
        operation: str,
        query: str,
        params: tuple[Any, ...] | None = None,
    ) -> None:
        try:
            await self.db.execute(query, params)
        except Exception:
            logger.warning(
                "Approval audit store failed: %s",
                operation,
                exc_info=True,
            )


def _request_params(
    pending: Any,
    *,
    source_channel: str | None,
    source_user_id: str | None,
    source_message_id: str | None,
    consumed_at: float | None,
) -> tuple[Any, ...]:
    extra = getattr(pending, "extra", None)
    if not isinstance(extra, dict):
        extra = {}
    tool_call = extra.get("tool_call")
    if not isinstance(tool_call, dict):
        tool_call = {}

    return (
        getattr(pending, "request_id", ""),
        getattr(pending, "scope_id", ""),
        extra.get("agent_id"),
        extra.get("tenant_id"),
        extra.get("source_id"),
        getattr(pending, "session_id", ""),
        getattr(pending, "user_id", ""),
        getattr(pending, "channel", ""),
        getattr(pending, "tool_name", ""),
        extra.get("approval_kind") or "tool_guard",
        tool_call.get("id"),
        _json_dumps(tool_call.get("input") or {}),
        getattr(pending, "result_summary", ""),
        int(getattr(pending, "findings_count", 0) or 0),
        getattr(pending, "status", "pending"),
        source_channel,
        source_user_id,
        source_message_id,
        _json_dumps(extra),
        1 if bool(getattr(pending, "consumed", False)) else 0,
        _from_timestamp(getattr(pending, "created_at", None)),
        _from_timestamp(getattr(pending, "resolved_at", None)),
        _from_timestamp(consumed_at),
    )


def _from_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).replace(
            tzinfo=None,
        )
    except (TypeError, ValueError, OSError):
        return None


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value), ensure_ascii=False)


_CREATE_REQUEST_TABLE = f"""
    CREATE TABLE IF NOT EXISTS {_REQUEST_TABLE} (
        request_id VARCHAR(64) NOT NULL,
        scope_id VARCHAR(255) NOT NULL,
        agent_id VARCHAR(128) NULL,
        tenant_id VARCHAR(128) NULL,
        source_id VARCHAR(128) NULL,
        session_id VARCHAR(255) NOT NULL,
        user_id VARCHAR(255) NULL,
        channel VARCHAR(64) NULL,
        tool_name VARCHAR(255) NOT NULL,
        approval_kind VARCHAR(64) NOT NULL DEFAULT 'tool_guard',
        tool_call_id VARCHAR(255) NULL,
        tool_input_json MEDIUMTEXT NULL,
        result_summary MEDIUMTEXT NULL,
        findings_count INT NOT NULL DEFAULT 0,
        status VARCHAR(32) NOT NULL,
        source_channel VARCHAR(64) NULL,
        source_user_id VARCHAR(255) NULL,
        source_message_id VARCHAR(255) NULL,
        extra_json MEDIUMTEXT NULL,
        consumed TINYINT(1) NOT NULL DEFAULT 0,
        created_at TIMESTAMP NULL,
        resolved_at TIMESTAMP NULL,
        consumed_at TIMESTAMP NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (request_id),
        INDEX idx_tool_approval_requests_scope_status (
            scope_id, status, created_at
        ),
        INDEX idx_tool_approval_requests_session (
            session_id, created_at
        ),
        INDEX idx_tool_approval_requests_agent (
            agent_id, tenant_id, source_id, created_at
        )
    )
"""

_CREATE_EVENT_TABLE = f"""
    CREATE TABLE IF NOT EXISTS {_EVENT_TABLE} (
        event_id BIGINT NOT NULL AUTO_INCREMENT,
        request_id VARCHAR(64) NOT NULL,
        event_type VARCHAR(64) NOT NULL,
        status VARCHAR(32) NULL,
        actor_channel VARCHAR(64) NULL,
        actor_user_id VARCHAR(255) NULL,
        source_message_id VARCHAR(255) NULL,
        details_json MEDIUMTEXT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (event_id),
        INDEX idx_tool_approval_events_request (
            request_id, created_at
        ),
        INDEX idx_tool_approval_events_type (
            event_type, created_at
        )
    )
"""

_UPSERT_REQUEST = f"""
    INSERT INTO {_REQUEST_TABLE} (
        request_id, scope_id, agent_id, tenant_id, source_id,
        session_id, user_id, channel, tool_name, approval_kind,
        tool_call_id, tool_input_json, result_summary, findings_count,
        status, source_channel, source_user_id, source_message_id,
        extra_json, consumed, created_at, resolved_at, consumed_at
    )
    VALUES (
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s, %s
    )
    ON DUPLICATE KEY UPDATE
        scope_id = VALUES(scope_id),
        agent_id = VALUES(agent_id),
        tenant_id = VALUES(tenant_id),
        source_id = VALUES(source_id),
        session_id = VALUES(session_id),
        user_id = VALUES(user_id),
        channel = VALUES(channel),
        tool_name = VALUES(tool_name),
        approval_kind = VALUES(approval_kind),
        tool_call_id = VALUES(tool_call_id),
        tool_input_json = VALUES(tool_input_json),
        result_summary = VALUES(result_summary),
        findings_count = VALUES(findings_count),
        status = VALUES(status),
        source_channel = COALESCE(VALUES(source_channel), source_channel),
        source_user_id = COALESCE(VALUES(source_user_id), source_user_id),
        source_message_id = COALESCE(
            VALUES(source_message_id),
            source_message_id
        ),
        extra_json = VALUES(extra_json),
        consumed = VALUES(consumed),
        resolved_at = COALESCE(VALUES(resolved_at), resolved_at),
        consumed_at = COALESCE(VALUES(consumed_at), consumed_at),
        updated_at = CURRENT_TIMESTAMP
"""

_INSERT_EVENT = f"""
    INSERT INTO {_EVENT_TABLE} (
        request_id, event_type, status, actor_channel, actor_user_id,
        source_message_id, details_json
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
"""
