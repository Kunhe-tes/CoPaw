# -*- coding: utf-8 -*-
"""Tests for cron subtask result indexing."""

from datetime import datetime

import pytest

from monitor.app.services.subtask.query_service import QueryService


class FakeDb:
    def __init__(self):
        self.fetch_all_calls = []
        self.fetch_one_calls = []
        self.execute_calls = []
        self.fetch_all_results = [
            [
                {
                    "execution_id": 42,
                    "job_id": "job-1",
                    "trace_id": "trace-1",
                    "actual_time": datetime(2026, 8, 16, 10, 0, 0),
                    "created_at": datetime(2026, 8, 16, 10, 0, 1),
                    "tenant_id": "tenant-1",
                    "bbk_id": "771",
                    "source_id": "source-1",
                    "skill_ids": "skill-a, skill-b, skill-a",
                },
            ],
            [
                {
                    "subtask_id": 7,
                    "trace_id": "trace-1",
                    "task_id": "task-1",
                    "filename": "result.html",
                    "task_type": "plan",
                    "custuid": "cust-1",
                    "cust_nm": "Customer",
                    "bbk_org_id": "772",
                    "template_id": 11,
                    "result_id": "doc-1",
                    "status": "SUC",
                    "created_at": datetime(2026, 8, 16, 10, 0, 2),
                },
            ],
        ]
        self.fetch_one_results = [{"count": 1}, {"count": 0}]

    async def fetch_all(self, sql, params=None):
        self.fetch_all_calls.append((sql, params))
        return self.fetch_all_results.pop(0)

    async def fetch_one(self, sql, params=None):
        self.fetch_one_calls.append((sql, params))
        return self.fetch_one_results.pop(0)

    async def execute(self, sql, params=None):
        self.execute_calls.append((sql, params))
        return 1


@pytest.mark.asyncio
async def test_batch_update_indexes_success_execution_results():
    db = FakeDb()
    success_count, error_count, indexed_count = await QueryService(
        db=db,
    ).batch_update_execution_async_status()

    assert success_count == 1
    assert error_count == 0
    assert indexed_count == 2

    success_update_sql = db.execute_calls[0][0]
    assert "async_status = 'success'" in success_update_sql
    assert "AND e.status = 'success'" in success_update_sql

    insert_calls = [
        call
        for call in db.execute_calls
        if "INSERT INTO swe_cron_result_index" in call[0]
    ]
    assert len(insert_calls) == 2

    first_insert_params = insert_calls[0][1]
    assert first_insert_params[0] == "source-1"
    assert first_insert_params[1] == "tenant-1"
    assert first_insert_params[2] == "771"
    assert first_insert_params[3] == "772"
    assert first_insert_params[4] == "cust-1"
    assert first_insert_params[6] == "skill-a"
    assert first_insert_params[13] == 11
    assert first_insert_params[14] == "doc-1"

    second_insert_params = insert_calls[1][1]
    assert second_insert_params[6] == "skill-b"
