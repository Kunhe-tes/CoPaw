# -*- coding: utf-8 -*-
"""Tests for cron subtask result indexing."""

import asyncio
from datetime import datetime

from monitor.app.services.subtask import query_service as query_service_module
from monitor.app.services.subtask.query_service import QueryService


class FakeDb:
    def __init__(self):
        self.fetch_all_calls = []
        self.execute_calls = []
        self.execute_many_calls = []
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

    async def fetch_all(self, sql, params=None):
        self.fetch_all_calls.append((sql, params))
        return self.fetch_all_results.pop(0)

    async def execute(self, sql, params=None):
        self.execute_calls.append((sql, params))
        if "async_status = 'success'" in sql:
            return 1
        if "async_status = 'error'" in sql:
            return 0
        return 1

    async def execute_many(self, sql, params_list):
        self.execute_many_calls.append((sql, params_list))
        return len(params_list)


def _result_index_batch_insert_calls(db):
    return [
        call
        for call in db.execute_many_calls
        if "INSERT INTO swe_cron_result_index" in call[0]
    ]


def test_batch_update_indexes_success_execution_results():
    db = FakeDb()
    success_count, error_count, indexed_count, indexed_users = asyncio.run(
        QueryService(db=db).batch_update_execution_async_status(),
    )

    assert success_count == 1
    assert error_count == 0
    assert indexed_count == 2
    assert indexed_users == [
        {"custUid": "cust-1", "bbkId": "772"},
        {"custUid": "cust-1", "bbkId": "772"},
    ]

    success_update_sql = db.execute_calls[0][0]
    assert "async_status = 'success'" in success_update_sql
    assert "AND e.status = 'success'" in success_update_sql

    insert_calls = _result_index_batch_insert_calls(db)
    assert len(insert_calls) == 1
    assert len(insert_calls[0][1]) == 2

    first_insert_params = insert_calls[0][1][0]
    assert first_insert_params[0] == "source-1"
    assert first_insert_params[1] == "tenant-1"
    assert first_insert_params[2] == "771"
    assert first_insert_params[3] == "772"
    assert first_insert_params[4] == "cust-1"
    assert first_insert_params[5] == "C******r"
    assert first_insert_params[6] == "skill-a"
    assert first_insert_params[13] == 11
    assert first_insert_params[14] == "doc-1"

    second_insert_params = insert_calls[0][1][1]
    assert second_insert_params[6] == "skill-b"

    subtask_sql = db.fetch_all_calls[1][0]
    assert "template_id IS NOT NULL" in subtask_sql
    assert "template_id > 0" in subtask_sql
    assert "result_id IS NOT NULL" in subtask_sql
    assert "result_id <> ''" in subtask_sql


class FakeCustomerNameResponse:
    status_code = 200

    def json(self):
        return {
            "data": [
                {
                    "row": "0000001015FICNP",
                    "values": {"f": {"EAC_NM": "Customer Name"}},
                },
            ],
        }


class FakeCustomerNameClient:
    def __init__(self):
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def post(self, url, headers=None, json=None):
        self.post_calls.append((url, headers, json))
        return FakeCustomerNameResponse()


def test_batch_update_queries_and_masks_missing_customer_name(monkeypatch):
    db = FakeDb()
    db.fetch_all_results[1][0]["custuid"] = "PNCIF5101000000"
    db.fetch_all_results[1][0]["cust_nm"] = ""

    client = FakeCustomerNameClient()
    monkeypatch.setattr(
        query_service_module,
        "CUSTOMER_NAME_QUERY_URL",
        "https://example.test/customer-name",
    )
    monkeypatch.setattr(
        query_service_module.httpx,
        "AsyncClient",
        lambda timeout: client,
    )

    success_count, error_count, indexed_count, indexed_users = asyncio.run(
        QueryService(db=db).batch_update_execution_async_status(),
    )

    assert success_count == 1
    assert error_count == 0
    assert indexed_count == 2
    assert indexed_users == [
        {"custUid": "PNCIF5101000000", "bbkId": "772"},
        {"custUid": "PNCIF5101000000", "bbkId": "772"},
    ]

    assert client.post_calls == [
        (
            "https://example.test/customer-name",
            {"Content-Type": "application/json"},
            {"rows": ["0000001015FICNP"]},
        ),
    ]

    insert_calls = _result_index_batch_insert_calls(db)
    assert insert_calls[0][1][0][5] == "C*********e"
