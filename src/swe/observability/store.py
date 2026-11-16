# -*- coding: utf-8 -*-
"""Independent observability SQL store and schema readiness inspection."""

from __future__ import annotations

from datetime import timezone
from typing import Any

from ..database import DatabaseConnection

REQUIRED_TABLES = frozenset(
    {
        "swe_agentobs_inbox",
        "swe_agentobs_events",
        "swe_agentobs_runs",
        "swe_agentobs_attempts",
        "swe_agentobs_spans",
    },
)
REQUIRED_COLUMNS = {
    "swe_agentobs_inbox": frozenset(
        {
            "ingest_id",
            "payload_text",
            "processing_state",
            "processed_at",
            "reason_code",
            "event_id",
        },
    ),
    "swe_agentobs_events": frozenset(
        {
            "event_id",
            "schema_version",
            "event_name",
            "entity_kind",
            "entity_id",
            "phase_key",
            "local_seq",
            "run_id",
            "attempt_id",
            "span_id",
            "occurred_at",
            "first_ingest_id",
            "producer_id",
            "metadata_text",
        },
    ),
    "swe_agentobs_runs": frozenset(
        {
            "run_id",
            "service_unit_key",
            "source_key",
            "tenant_key",
            "agent_key",
            "chat_key",
            "root_question_key",
            "started_at",
            "ended_at",
            "status",
            "quality",
            "terminal_fact_source",
            "duration_us",
            "llm_calls",
            "tool_calls",
            "input_tokens",
            "output_tokens",
            "span_count",
            "error_span_count",
            "projected_at",
        },
    ),
    "swe_agentobs_attempts": frozenset(
        {
            "attempt_id",
            "run_id",
            "attempt_index",
            "predecessor_attempt_id",
            "started_at",
            "ended_at",
            "status",
            "duration_us",
        },
    ),
    "swe_agentobs_spans": frozenset(
        {
            "span_id",
            "run_id",
            "attempt_id",
            "parent_span_id",
            "span_type",
            "operation",
            "kind",
            "name",
            "step_index",
            "started_at",
            "ended_at",
            "status",
            "technical_status",
            "has_error",
            "error_type",
            "duration_us",
            "input_tokens",
            "output_tokens",
        },
    ),
}
REQUIRED_INDEXES = {
    "swe_agentobs_inbox": {
        "ix_agentobs_inbox_pending": (False, ("processing_state", "ingest_id")),
    },
    "swe_agentobs_events": {
        "uq_agentobs_event_slot": (
            True,
            ("entity_kind", "entity_id", "phase_key", "local_seq"),
        ),
        "ix_agentobs_events_run": (False, ("run_id", "occurred_at", "event_id")),
    },
    "swe_agentobs_runs": {
        "ix_agentobs_runs_source_time": (
            False,
            ("service_unit_key", "source_key", "started_at", "run_id"),
        ),
        "ix_agentobs_runs_scope_time": (
            False,
            (
                "service_unit_key",
                "source_key",
                "tenant_key",
                "agent_key",
                "started_at",
                "run_id",
            ),
        ),
    },
    "swe_agentobs_attempts": {
        "uq_agentobs_attempt_order": (True, ("run_id", "attempt_index")),
    },
    "swe_agentobs_spans": {
        "ix_agentobs_spans_run_time": (False, ("run_id", "started_at", "span_id")),
        "ix_agentobs_spans_parent": (
            False,
            ("run_id", "parent_span_id", "started_at", "span_id"),
        ),
    },
}


class ObservabilityStore:
    def __init__(self, connection: DatabaseConnection) -> None:
        self.connection = connection

    async def readiness(self) -> dict[str, Any]:
        async with self.connection.acquire() as session:
            rows = await session.fetch_all(
                "SELECT TABLE_NAME,COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME LIKE 'swe_agentobs_%'",
                (self.connection.config.database,),
            )
            index_rows = await session.fetch_all(
                "SELECT TABLE_NAME,INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME "
                "FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME LIKE 'swe_agentobs_%'",
                (self.connection.config.database,),
            )
        found: dict[str, set[str]] = {}
        for row in rows:
            found.setdefault(str(row["TABLE_NAME"]), set()).add(str(row["COLUMN_NAME"]))
        missing_columns = {
            table: sorted(columns - found.get(table, set()))
            for table, columns in REQUIRED_COLUMNS.items()
            if columns - found.get(table, set())
        }
        missing_tables = sorted(REQUIRED_TABLES - found.keys())
        indexes: dict[str, dict[str, dict[str, Any]]] = {}
        for row in index_rows:
            table = str(row["TABLE_NAME"])
            name = str(row["INDEX_NAME"])
            index = indexes.setdefault(table, {}).setdefault(
                name, {"non_unique": bool(int(row["NON_UNIQUE"])), "columns": []},
            )
            index["columns"].append((int(row["SEQ_IN_INDEX"]), str(row["COLUMN_NAME"])))
        invalid_indexes: dict[str, list[str]] = {}
        for table, definitions in REQUIRED_INDEXES.items():
            for name, (unique, columns) in definitions.items():
                actual = indexes.get(table, {}).get(name)
                actual_columns = (
                    tuple(column for _, column in sorted(actual["columns"]))
                    if actual
                    else None
                )
                if (
                    actual is None
                    or actual["non_unique"] == unique
                    or actual_columns != columns
                ):
                    invalid_indexes.setdefault(table, []).append(name)
        return {
            "ready": not missing_tables and not missing_columns and not invalid_indexes,
            "missing_tables": missing_tables,
            "missing_columns": missing_columns,
            "invalid_indexes": invalid_indexes,
        }

    async def list_runs(
        self,
        *,
        service_unit_id: str,
        source_ids: list[str],
        limit: int,
        before: tuple[Any, str] | None = None,
        start_at=None,
        end_at=None,
    ) -> list[dict[str, Any]]:
        if not source_ids:
            return []
        placeholders = ",".join(["%s"] * len(source_ids))
        query = (
            "SELECT run_id, service_unit_key, source_key, tenant_key, agent_key, "
            "chat_key, root_question_key, started_at, ended_at, status, quality, "
            "duration_us, llm_calls, tool_calls, input_tokens, output_tokens, "
            "span_count, error_span_count, projected_at FROM swe_agentobs_runs "
            f"WHERE service_unit_key = %s AND source_key IN ({placeholders})"
        )
        params: list[Any] = [
            service_unit_id.encode(),
            *[s.encode() for s in source_ids],
        ]
        if start_at is not None:
            query += " AND started_at >= %s"
            params.append(start_at.astimezone(timezone.utc).replace(tzinfo=None))
        if end_at is not None:
            query += " AND started_at < %s"
            params.append(end_at.astimezone(timezone.utc).replace(tzinfo=None))
        if before:
            query += " AND (started_at < %s OR (started_at = %s AND run_id < %s))"
            params.extend([before[0], before[0], before[1]])
        query += " ORDER BY started_at DESC, run_id DESC LIMIT %s"
        params.append(limit)
        async with self.connection.acquire() as session:
            return await session.fetch_all(query, tuple(params))
