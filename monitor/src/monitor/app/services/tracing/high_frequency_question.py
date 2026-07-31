# -*- coding: utf-8 -*-
"""Service for high-frequency question analysis APIs."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from fastapi import HTTPException

from ...database import DatabaseConnection, get_db_connection
from ...models.high_frequency_question import (
    HighFrequencyQuestionMessageListResponse,
    HighFrequencyQuestionMessageQueryRequest,
    HighFrequencyQuestionMessageResponse,
    HighFrequencyQuestionResultSaveRequest,
    HighFrequencyQuestionResultSaveResponse,
    MAX_MESSAGE_ROWS,
)

logger = logging.getLogger(__name__)

MEANINGLESS_USER_MESSAGES = (
    "好",
    "好的",
    "收到",
    "继续",
    "谢谢",
    "谢谢你",
    "感谢",
    "嗯",
    "嗯嗯",
    "ok",
    "你好",
    "OK",
)


class HighFrequencyQuestionService:
    """High-frequency question analysis service."""

    def __init__(self, db: Optional[DatabaseConnection] = None) -> None:
        self._db = db or get_db_connection()

    @classmethod
    def get_instance(cls) -> "HighFrequencyQuestionService":
        return cls(get_db_connection())

    async def query_messages(
        self,
        request: HighFrequencyQuestionMessageQueryRequest,
    ) -> HighFrequencyQuestionMessageListResponse:
        """Query cleaned source user messages from tracing traces."""
        started = time.perf_counter()
        where_sql, params = self._build_message_where_clause(request)
        limit = MAX_MESSAGE_ROWS + 1

        query = f"""
            SELECT
                trace_id,
                user_id,
                session_id,
                bbk_id,
                user_message,
                start_time
            FROM swe_tracing_traces
            WHERE {where_sql}
            ORDER BY start_time ASC, trace_id ASC
            LIMIT %s
        """
        rows = await self._db.fetch_all(query, (*params, limit))

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "High-frequency question messages queried: "
            "source_id=%s start_time=%s end_time=%s bbk_id=%s count=%d elapsed_ms=%d",
            request.source_id,
            request.start_time,
            request.end_time,
            request.bbk_id,
            min(len(rows), MAX_MESSAGE_ROWS),
            elapsed_ms,
        )

        if len(rows) > MAX_MESSAGE_ROWS:
            raise HTTPException(
                status_code=400,
                detail=(
                    "message query exceeds 10000 rows; narrow the time range "
                    "or bbk_id"
                ),
            )

        return HighFrequencyQuestionMessageListResponse(
            total=len(rows),
            data=[self._row_to_message(row) for row in rows],
        )

    async def save_results(
        self,
        request: HighFrequencyQuestionResultSaveRequest,
    ) -> HighFrequencyQuestionResultSaveResponse:
        """Save a full high-frequency question result batch transactionally."""
        started = time.perf_counter()
        params_list = self._build_insert_params(request)

        async with self._db.acquire() as conn:
            await conn.begin()
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        DELETE FROM swe_high_frequency_question_result
                        WHERE batch_id = %s
                        """,
                        (request.batch_id,),
                    )
                    if params_list:
                        await cur.executemany(
                            """
                            INSERT INTO swe_high_frequency_question_result (
                                batch_id,
                                stat_start_time,
                                stat_end_time,
                                scope_type,
                                bbk_id,
                                rank_no,
                                topic_name,
                                message_count,
                                user_count,
                                valid_message_count,
                                sample_questions
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                            )
                            """,
                            params_list,
                        )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "High-frequency question results saved: "
            "batch_id=%s saved_count=%d elapsed_ms=%d",
            request.batch_id,
            len(params_list),
            elapsed_ms,
        )
        return HighFrequencyQuestionResultSaveResponse(
            batch_id=request.batch_id,
            saved_count=len(params_list),
        )

    def _build_message_where_clause(
        self,
        request: HighFrequencyQuestionMessageQueryRequest,
    ) -> tuple[str, tuple[Any, ...]]:
        clauses = [
            "source_id = %s",
            "start_time >= %s",
            "start_time < %s",
            "status = 'completed'",
            "session_id NOT LIKE %s",
            "user_message IS NOT NULL",
            "TRIM(user_message) != ''",
        ]
        params: list[Any] = [
            request.source_id,
            request.start_time,
            request.end_time,
            "cron-task%",
        ]

        placeholders = ", ".join(["%s"] * len(MEANINGLESS_USER_MESSAGES))
        clauses.append(f"TRIM(user_message) NOT IN ({placeholders})")
        params.extend(MEANINGLESS_USER_MESSAGES)

        if request.bbk_id:
            clauses.append("bbk_id = %s")
            params.append(request.bbk_id)

        return " AND ".join(clauses), tuple(params)

    def _row_to_message(
        self,
        row: dict[str, Any],
    ) -> HighFrequencyQuestionMessageResponse:
        return HighFrequencyQuestionMessageResponse(
            message_id=str(row["trace_id"]),
            user_id=row.get("user_id"),
            session_id=row.get("session_id"),
            bbk_id=row.get("bbk_id"),
            content=str(row.get("user_message") or ""),
            message_time=row["start_time"],
        )

    def _build_insert_params(
        self,
        request: HighFrequencyQuestionResultSaveRequest,
    ) -> list[tuple[Any, ...]]:
        params_list: list[tuple[Any, ...]] = []
        for result in request.results:
            params_list.append(
                (
                    request.batch_id,
                    request.stat_start_time,
                    request.stat_end_time,
                    result.scope_type,
                    result.bbk_id,
                    result.rank_no,
                    result.topic_name,
                    result.message_count,
                    result.user_count,
                    result.valid_message_count,
                    json.dumps(result.sample_questions, ensure_ascii=False),
                ),
            )
        return params_list
