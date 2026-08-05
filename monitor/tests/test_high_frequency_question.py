# -*- coding: utf-8 -*-
"""Tests for high-frequency question APIs."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from pydantic import ValidationError

from monitor.app.models.high_frequency_question import (
    HighFrequencyQuestionMessageQueryRequest,
    HighFrequencyQuestionResultSaveRequest,
)
from monitor.app.routers.high_frequency_question import _resolve_source_id
from monitor.app.services.tracing import high_frequency_question as hfq_service_module
from monitor.app.services.tracing.high_frequency_question import (
    HighFrequencyQuestionService,
)


def test_message_query_requires_valid_time_range():
    with pytest.raises(ValidationError):
        HighFrequencyQuestionMessageQueryRequest(
            source_id="RMASSIST",
            start_time="2026-07-30 00:00:00",
            end_time="2026-07-23 00:00:00",
        )


def test_result_save_rejects_invalid_scope_bbk_pair():
    with pytest.raises(ValidationError):
        HighFrequencyQuestionResultSaveRequest(
            source_id="RMASSIST",
            batch_id="HFQ_20260730_030000",
            stat_start_time="2026-07-23 00:00:00",
            stat_end_time="2026-07-30 00:00:00",
            results=[
                {
                    "scope_type": "ALL",
                    "bbk_id": "110",
                    "rank_no": 1,
                    "topic_name": "查询客户保险持仓",
                    "message_count": 10,
                    "valid_message_count": 20,
                    "sample_questions": [],
                },
            ],
        )


def test_result_save_rejects_duplicate_rank_key():
    with pytest.raises(ValidationError):
        HighFrequencyQuestionResultSaveRequest(
            source_id="RMASSIST",
            batch_id="HFQ_20260730_030000",
            stat_start_time="2026-07-23 00:00:00",
            stat_end_time="2026-07-30 00:00:00",
            results=[
                _result_item(),
                _result_item(),
            ],
        )


def test_resolve_source_id_prefers_header_then_body_then_default():
    assert _resolve_source_id(" RMASSIST ", "default") == "RMASSIST"
    assert _resolve_source_id(None, " body-source ") == "body-source"
    assert _resolve_source_id(None, None) == "default"


@pytest.mark.asyncio
async def test_query_messages_uses_expected_filters():
    db = _FakeDb(
        rows=[
            {
                "trace_id": "trace-001",
                "user_id": "136807",
                "session_id": "session-001",
                "bbk_id": "110",
                "user_message": "查保险",
                "start_time": datetime(2026, 7, 29, 10, 20, 0),
            },
        ],
    )
    service = HighFrequencyQuestionService(db)
    request = HighFrequencyQuestionMessageQueryRequest(
        source_id="RMASSIST",
        start_time="2026-07-23 00:00:00",
        end_time="2026-07-30 00:00:00",
        bbk_id="110",
    )

    response = await service.query_messages(request)

    assert response.total == 1
    assert response.data[0].message_id == "trace-001"
    assert response.data[0].content == "查保险"
    sql = db.fetch_all_calls[0][0]
    params = db.fetch_all_calls[0][1]
    assert "source_id = %s" in sql
    assert "status = 'completed'" in sql
    assert "session_id NOT LIKE %s" in sql
    assert "TRIM(user_message) NOT IN" in sql
    assert "bbk_id = %s" in sql
    assert params[0] == "RMASSIST"
    assert "cron-task%" in params
    assert params[-2] == "110"
    assert params[-1] == 10001


@pytest.mark.asyncio
async def test_save_results_deletes_and_batch_inserts_in_transaction():
    db = _FakeDb()
    service = HighFrequencyQuestionService(db)
    request = HighFrequencyQuestionResultSaveRequest(
        source_id="RMASSIST",
        batch_id="HFQ_20260730_030000",
        stat_start_time="2026-07-23 00:00:00",
        stat_end_time="2026-07-30 00:00:00",
        results=[_result_item()],
    )

    response = await service.save_results(request)

    assert response.saved_count == 1
    assert db.conn.began is True
    assert db.conn.committed is True
    assert db.conn.rolled_back is False
    assert "DELETE FROM swe_high_frequency_question_result" in db.cursor.executes[0][0]
    assert db.cursor.executes[0][1] == ("RMASSIST", "HFQ_20260730_030000")
    assert "INSERT INTO swe_high_frequency_question_result" in db.cursor.many[0][0]
    assert "source_id" in db.cursor.many[0][0]
    assert "user_count" not in db.cursor.many[0][0]
    assert db.cursor.many[0][1][0][0] == "RMASSIST"
    assert db.cursor.many[0][1][0][1] == "HFQ_20260730_030000"


@pytest.mark.asyncio
async def test_wait_for_result_rows_polls_until_rows_exist(monkeypatch):
    db = _FakeDb(fetch_one_results=[{"count": 0}, {"count": 3}])
    service = HighFrequencyQuestionService(db)
    monkeypatch.setattr(hfq_service_module, "HFQ_RESULT_WAIT_SECONDS", 1.0)
    monkeypatch.setattr(
        hfq_service_module,
        "HFQ_RESULT_POLL_INTERVAL_SECONDS",
        1.0,
    )
    monkeypatch.setattr(hfq_service_module.asyncio, "sleep", _noop_sleep)

    result_count = await service._wait_for_result_rows(
        source_id="RMASSIST",
        batch_id="task-001",
    )

    assert result_count == 3
    assert len(db.fetch_one_calls) == 2


def _result_item() -> dict:
    return {
        "scope_type": "ORG",
        "bbk_id": "110",
        "rank_no": 1,
        "topic_name": "查询客户保险持仓",
        "message_count": 10,
        "valid_message_count": 20,
        "sample_questions": ["查保险"],
    }


class _FakeDb:
    def __init__(
        self,
        rows: list[dict] | None = None,
        fetch_one_results: list[dict | None] | None = None,
    ) -> None:
        self.rows = rows or []
        self.fetch_one_results = fetch_one_results or []
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.cursor = _FakeCursor()
        self.conn = _FakeConnection(self.cursor)

    async def fetch_all(self, query: str, params: tuple) -> list[dict]:
        self.fetch_all_calls.append((query, params))
        return self.rows

    async def fetch_one(self, query: str, params: tuple) -> dict | None:
        self.fetch_one_calls.append((query, params))
        if self.fetch_one_results:
            return self.fetch_one_results.pop(0)
        return None

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


async def _noop_sleep(_delay: float) -> None:
    return None


class _FakeConnection:
    def __init__(self, cursor: "_FakeCursor") -> None:
        self.cursor_obj = cursor
        self.began = False
        self.committed = False
        self.rolled_back = False

    async def begin(self) -> None:
        self.began = True

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    def cursor(self) -> "_FakeCursor":
        return self.cursor_obj


class _FakeCursor:
    def __init__(self) -> None:
        self.executes: list[tuple[str, tuple]] = []
        self.many: list[tuple[str, list[tuple]]] = []

    async def __aenter__(self) -> "_FakeCursor":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, query: str, params: tuple) -> None:
        self.executes.append((query, params))

    async def executemany(self, query: str, params: list[tuple]) -> None:
        self.many.append((query, params))
