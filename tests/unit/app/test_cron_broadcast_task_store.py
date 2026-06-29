# -*- coding: utf-8 -*-
"""定时任务广播分发进度存储测试。"""

import asyncio

from swe.app.crons.broadcast_task_store import CronBroadcastTaskStore


class _Db:
    def __init__(self, execute_results=None, fetch_one_results=None):
        self.is_connected = True
        self.executed = []
        self.execute_results = list(execute_results or [])
        self.fetch_one_results = list(fetch_one_results or [])

    async def execute(self, query, params=None):
        self.executed.append((query, params))
        if self.execute_results:
            return self.execute_results.pop(0)
        return 1

    async def fetch_one(self, query, params=None):
        self.executed.append((query, params))
        if self.fetch_one_results:
            return self.fetch_one_results.pop(0)
        return None

    async def fetch_all(self, query, params=None):
        self.executed.append((query, params))
        return []


def _start_task(store: CronBroadcastTaskStore):
    return asyncio.run(
        store.start_task(
            agent_id="default",
            source_id="source-a",
            tenant_id="tenant-a",
            job_id="job-source",
            target_tenant_ids=["tenant-a", "tenant-b"],
        ),
    )


def test_memory_store_tracks_target_progress():
    store = CronBroadcastTaskStore()

    task, reused = _start_task(store)
    asyncio.run(store.mark_target_running(task.task_id, "tenant-a"))
    asyncio.run(
        store.record_target_result(
            task.task_id,
            {
                "tenant_id": "tenant-a",
                "success": True,
                "job_id": "child-a",
                "cron": "0 9 * * *",
                "timezone": "UTC",
                "offset_minutes": 0,
                "notification_timezone": "UTC",
                "error": "",
                "warning": "",
            },
        ),
    )
    snapshot = asyncio.run(store.get_task(task.task_id))

    assert reused is False
    assert snapshot is not None
    assert snapshot.status == "running"
    assert snapshot.tenant_count == 2
    assert snapshot.completed_count == 1
    assert snapshot.failed_count == 0
    assert snapshot.results[0]["job_id"] == "child-a"


def test_memory_store_reuses_running_task_for_same_source_job():
    store = CronBroadcastTaskStore()

    first, first_reused = _start_task(store)
    second, second_reused = asyncio.run(
        store.start_task(
            agent_id="default",
            source_id="source-a",
            tenant_id="tenant-a",
            job_id="job-source",
            target_tenant_ids=["tenant-c"],
        ),
    )

    assert first_reused is False
    assert second_reused is True
    assert second.task_id == first.task_id


def test_memory_store_finishes_failed_when_any_target_failed():
    store = CronBroadcastTaskStore()

    task, _ = _start_task(store)
    asyncio.run(
        store.record_target_result(
            task.task_id,
            {
                "tenant_id": "tenant-a",
                "success": True,
                "job_id": "child-a",
                "cron": "",
                "timezone": "UTC",
                "offset_minutes": 0,
                "notification_timezone": "UTC",
                "error": "",
                "warning": "",
            },
        ),
    )
    asyncio.run(
        store.record_target_result(
            task.task_id,
            {
                "tenant_id": "tenant-b",
                "success": False,
                "job_id": "",
                "cron": "",
                "timezone": "UTC",
                "offset_minutes": 0,
                "notification_timezone": "UTC",
                "error": "boom",
                "warning": "",
            },
        ),
    )
    asyncio.run(store.finish_task(task.task_id))
    snapshot = asyncio.run(store.get_task(task.task_id))

    assert snapshot is not None
    assert snapshot.status == "failed"
    assert snapshot.completed_count == 2
    assert snapshot.failed_count == 1


def test_initialize_creates_task_and_item_tables():
    db = _Db()
    store = CronBroadcastTaskStore(db)

    asyncio.run(store.initialize())

    sql = "\n".join(query for query, _params in db.executed)
    assert "CREATE TABLE IF NOT EXISTS swe_cron_broadcast_tasks" in sql
    assert "CREATE TABLE IF NOT EXISTS swe_cron_broadcast_task_items" in sql
    assert "target_key VARCHAR(1024) NOT NULL" in sql
    assert "claim_key VARCHAR(64) NULL" in sql
    assert "UNIQUE KEY uniq_broadcast_task_claim" in sql
    assert "PRIMARY KEY (task_id, tenant_id)" in sql


def test_db_store_reuses_running_task_when_claim_insert_is_ignored():
    db = _Db(
        execute_results=[0],
        fetch_one_results=[
            None,
            {"task_id": "task-existing"},
            {
                "task_id": "task-existing",
                "agent_id": "default",
                "source_id": "source-a",
                "tenant_id": "tenant-a",
                "job_id": "job-source",
                "target_key": "[\"tenant-a\",\"tenant-b\"]",
                "status": "running",
                "tenant_count": 2,
                "completed_count": 0,
                "failed_count": 0,
                "failure_summary": None,
                "updated_at": None,
            },
        ],
    )
    store = CronBroadcastTaskStore(db)

    task, reused = _start_task(store)

    sql = "\n".join(query for query, _params in db.executed)
    assert reused is True
    assert task.task_id == "task-existing"
    assert "INSERT IGNORE INTO swe_cron_broadcast_tasks" in sql
    assert "INSERT INTO swe_cron_broadcast_task_items" not in sql
