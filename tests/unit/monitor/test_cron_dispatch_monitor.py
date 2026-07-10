from datetime import datetime

import pytest

from monitor.app.services.cron import query_service as query_service_module
from monitor.app.services.cron.query_service import QueryService


class FakeDb:
    def __init__(self, *, one_results=None, all_results=None):
        self.one_results = list(one_results or [])
        self.all_results = list(all_results or [])
        self.fetch_one_calls = []
        self.fetch_all_calls = []

    async def fetch_one(self, sql, params=None):
        self.fetch_one_calls.append((sql, params))
        return self.one_results.pop(0) if self.one_results else None

    async def fetch_all(self, sql, params=None):
        self.fetch_all_calls.append((sql, params))
        return self.all_results.pop(0) if self.all_results else []


@pytest.mark.asyncio
async def test_get_dispatch_batches_filters_by_current_source(monkeypatch):
    fake_db = FakeDb(
        one_results=[
            {
                "total_batches": 2,
                "running_batches": 1,
                "completed_batches": 1,
                "failed_batches": 0,
                "total_intents": 12,
                "completed_intents": 8,
                "failed_intents": 1,
            },
        ],
        all_results=[
            [
                {
                    "batch_id": "cron:batch-a",
                    "parent_job_id": "parent-a",
                    "parent_external_job_id": "external-a",
                    "tenant_id": "tenant-a",
                    "source_id": "RMASSIST",
                    "provider_id": "provider-a",
                    "model_id": "model-a",
                    "agent_id": "agent-a",
                    "scheduled_fire_at": datetime(2026, 7, 8, 9, 0, 0),
                    "callback_received_at": datetime(2026, 7, 8, 5, 0, 0),
                    "status": "running",
                    "lock_owner": "worker-a",
                    "locked_at": datetime(2026, 7, 8, 5, 0, 20),
                    "total_count": 12,
                    "completed_count": 8,
                    "failed_count": 1,
                    "error_message": "",
                    "completed_at": None,
                    "created_at": datetime(2026, 7, 8, 5, 0, 0),
                    "updated_at": datetime(2026, 7, 8, 5, 1, 0),
                },
            ],
        ],
    )
    monkeypatch.setattr(
        query_service_module,
        "get_db_connection",
        lambda: fake_db,
    )

    result = await QueryService().get_dispatch_batches(
        source_id="RMASSIST",
        start_time=datetime(2026, 7, 8, 0, 0, 0),
        end_time=datetime(2026, 7, 8, 23, 59, 59),
        status="running",
        page=1,
        page_size=20,
    )

    assert result.source_id == "RMASSIST"
    assert result.stats.pending_intents == 3
    assert result.items[0].batch_id == "cron:batch-a"
    assert fake_db.fetch_one_calls[0][1] == (
        "RMASSIST",
        datetime(2026, 7, 8, 0, 0, 0),
        datetime(2026, 7, 8, 23, 59, 59),
        "running",
    )


@pytest.mark.asyncio
async def test_get_dispatch_batch_detail_parses_events(monkeypatch):
    fake_db = FakeDb(
        one_results=[
            {
                "batch_id": "cron:batch-a",
                "parent_job_id": "parent-a",
                "parent_external_job_id": "",
                "tenant_id": "tenant-a",
                "source_id": "RMASSIST",
                "provider_id": "provider-a",
                "model_id": "model-a",
                "agent_id": "agent-a",
                "scheduled_fire_at": datetime(2026, 7, 8, 9, 0, 0),
                "callback_received_at": datetime(2026, 7, 8, 5, 0, 0),
                "status": "running",
                "lock_owner": "worker-a",
                "locked_at": None,
                "total_count": 1,
                "completed_count": 0,
                "failed_count": 0,
                "error_message": "",
                "completed_at": None,
                "created_at": datetime(2026, 7, 8, 5, 0, 0),
                "updated_at": datetime(2026, 7, 8, 5, 1, 0),
            },
            {"count": 1},
        ],
        all_results=[
            [
                {
                    "id": 1001,
                    "batch_id": "cron:batch-a",
                    "intent_role": "child",
                    "status": "pending",
                    "source_id": "RMASSIST",
                    "provider_id": "provider-a",
                    "model_id": "model-a",
                    "tenant_id": "tenant-a",
                    "agent_id": "agent-a",
                    "job_id": "job-a",
                    "parent_job_id": "parent-a",
                    "scheduled_fire_at": datetime(2026, 7, 8, 9, 0, 0),
                    "due_at": datetime(2026, 7, 8, 5, 5, 0),
                    "dispatch_order": 1,
                    "viewer_heat_score": "1.25",
                    "attempt_count": 0,
                    "max_attempts": 3,
                    "lock_owner": "",
                    "locked_at": None,
                    "acked_at": None,
                    "completed_at": None,
                    "error_message": "",
                    "created_at": datetime(2026, 7, 8, 5, 0, 0),
                    "updated_at": datetime(2026, 7, 8, 5, 0, 0),
                },
            ],
            [
                {
                    "id": 1,
                    "batch_id": "cron:batch-a",
                    "intent_id": 1001,
                    "event_type": "retry_scheduled",
                    "worker_id": "worker-a",
                    "job_id": "job-a",
                    "tenant_id": "tenant-a",
                    "source_id": "RMASSIST",
                    "details": '{"error": "timeout"}',
                    "created_at": datetime(2026, 7, 8, 5, 6, 0),
                },
            ],
        ],
    )
    monkeypatch.setattr(
        query_service_module,
        "get_db_connection",
        lambda: fake_db,
    )

    result = await QueryService().get_dispatch_batch_detail(
        source_id="RMASSIST",
        batch_id="cron:batch-a",
    )

    assert result is not None
    assert result.intent_total == 1
    assert result.intents[0].viewer_heat_score == 1.25
    assert result.events[0].details == {"error": "timeout"}


@pytest.mark.asyncio
async def test_get_dispatch_workers_parses_policy_and_capacity(monkeypatch):
    fake_db = FakeDb(
        all_results=[
            [
                {
                    "source_id": "RMASSIST",
                    "provider_id": "provider-a",
                    "model_id": "model-a",
                    "default_strategy_id": "strategy-a",
                    "strategy_schedule": (
                        '[{"start_time":"16:00","end_time":"21:00",'
                        '"strategy_id":"peak_1"}]'
                    ),
                    "enabled": 1,
                    "created_at": datetime(2026, 7, 8, 4, 0, 0),
                    "updated_at": datetime(2026, 7, 8, 4, 0, 0),
                    "strategy_id": "strategy-a",
                    "min_workers": 5,
                    "baseline_workers": 5,
                    "max_workers": 999,
                    "adjust_interval_seconds": 20,
                    "feedback_window_seconds": 20,
                    "stale_execution_seconds": 7800,
                    "error_rate_rules": '{"success_100": "double"}',
                    "strategy_enabled": 1,
                    "description": "test strategy",
                },
            ],
            [
                {
                    "id": 10,
                    "worker_id": "worker-a",
                    "source_id": "RMASSIST",
                    "provider_id": "provider-a",
                    "model_id": "model-a",
                    "strategy_id": "strategy-a",
                    "previous_workers": 5,
                    "baseline_workers": 5,
                    "min_workers": 5,
                    "max_workers": 999,
                    "effective_workers": 10,
                    "pending_count": 3,
                    "claimed_count": 2,
                    "running_count": 1,
                    "success_count": 8,
                    "failure_count": 0,
                    "error_rate": "0.0",
                    "matched_rule": '{"reason": "success_100_double"}',
                    "avg_latency_ms": 1200,
                    "decision_reason": "success_100_double",
                    "created_at": datetime(2026, 7, 8, 5, 0, 0),
                },
            ],
            [],
        ],
    )
    monkeypatch.setattr(
        query_service_module,
        "get_db_connection",
        lambda: fake_db,
    )

    result = await QueryService().get_dispatch_workers(source_id="RMASSIST")

    assert result.policies[0].strategy_schedule == [
        {
            "start_time": "16:00",
            "end_time": "21:00",
            "strategy_id": "peak_1",
        }
    ]
    assert result.policies[0].strategy["error_rate_rules"] == {
        "success_100": "double",
    }
    assert result.current_capacity[0].matched_rule == {
        "reason": "success_100_double",
    }
