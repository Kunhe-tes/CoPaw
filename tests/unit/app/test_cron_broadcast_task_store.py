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

    async def execute_many(self, query, params_list):
        self.executed.append((query, params_list))
        return len(params_list)

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


def test_async_task_mirror_marks_all_failed_as_failed():
    """统一任务镜像应将全部目标失败标记为 failed。"""
    db = _Db()
    store = CronBroadcastTaskStore(db)

    asyncio.run(
        store._mirror_async_task_finished(  # noqa: SLF001
            task_id="task-1",
            done_count=2,
            failed_count=2,
            results=[],
            failure_summary="all failed",
        ),
    )

    finish_calls = [
        params
        for query, params in db.executed
        if "UPDATE swe_async_tasks" in query
    ]
    assert finish_calls[-1][0] == "failed"


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


def test_db_store_uses_db_without_connection_status_check():
    """有数据库对象时广播任务不预校验连接状态。"""
    db = _Db()
    db.is_connected = False
    store = CronBroadcastTaskStore(db)

    task, reused = _start_task(store)

    sql = "\n".join(query for query, _params in db.executed)
    assert reused is False
    assert task.tenant_count == 2
    assert "INSERT IGNORE INTO swe_cron_broadcast_tasks" in sql
    assert "INSERT INTO swe_async_tasks" in sql


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
                "target_key": '["tenant-a","tenant-b"]',
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


def test_db_store_start_task_does_not_preinsert_target_items():
    db = _Db()
    store = CronBroadcastTaskStore(db)

    task, reused = asyncio.run(
        store.start_task(
            agent_id="default",
            source_id="source-a",
            tenant_id="tenant-a",
            job_id="job-source",
            target_tenant_ids=["tenant-a", "tenant-b", "tenant-c"],
        ),
    )

    sql = "\n".join(query for query, _params in db.executed)
    assert reused is False
    assert task.tenant_count == 3
    assert "INSERT IGNORE INTO swe_cron_broadcast_tasks" in sql
    assert "INSERT INTO swe_cron_broadcast_task_items" not in sql


def test_db_store_mirrors_actor_fields_to_async_task():
    """定时任务分发镜像到统一任务表时应保留操作人。"""
    db = _Db()
    store = CronBroadcastTaskStore(db)

    asyncio.run(
        store.start_task(
            agent_id="default",
            source_id="source-a",
            tenant_id="tenant-a",
            job_id="job-source",
            target_tenant_ids=["tenant-a", "tenant-b"],
            actor_user_id="operator-1",
            actor_user_name="张三",
        ),
    )

    async_task_calls = [
        params
        for query, params in db.executed
        if "INSERT INTO swe_async_tasks" in query
    ]
    assert async_task_calls
    assert async_task_calls[-1][5] == "向 2 个用户分发定时任务"
    assert async_task_calls[-1][7] == "operator-1"
    assert async_task_calls[-1][8] == "张三"


def test_db_store_mirrors_job_name_to_async_task_summary():
    """定时任务分发镜像到统一任务表时摘要应包含任务名称。"""
    db = _Db()
    store = CronBroadcastTaskStore(db)

    asyncio.run(
        store.start_task(
            agent_id="default",
            source_id="source-a",
            tenant_id="tenant-a",
            job_id="job-source",
            job_name="ark",
            target_tenant_ids=["tenant-a", "tenant-b"],
        ),
    )

    async_task_calls = [
        params
        for query, params in db.executed
        if "INSERT INTO swe_async_tasks" in query
    ]
    assert async_task_calls[-1][5] == "分发定时任务「ark」，目标 2 个用户"


def test_db_store_target_item_status_is_upserted_lazily():
    db = _Db()
    store = CronBroadcastTaskStore(db)

    task, _ = _start_task(store)
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

    sql = "\n".join(query for query, _params in db.executed)
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert "VALUES (%s, %s, 'running', NULL)" in sql
    assert "VALUES (%s, %s, %s, %s)" in sql
