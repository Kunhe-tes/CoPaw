# -*- coding: utf-8 -*-
"""验证结果提交暂时失败后只补写结果，不重复执行 Agent 或 Workflow。"""

import asyncio
import copy
import json
import os
from contextvars import Context

import pytest

from tests.unit.app.test_managed_cron_execution import Engine, key
from tests.unit.scheduler.test_managed_cron_executions import (
    enqueue,
    execution_setup,
)


class Session:
    def __init__(self):
        self.states = {}

    async def mutate_session_state(
        self,
        session_id,
        mutator,
        user_id="",
        **_kwargs,
    ):
        scope = session_id, user_id
        self.states[scope] = mutator(copy.deepcopy(self.states.get(scope, {})))

    async def get_session_state_dict(self, session_id, user_id="", **_kwargs):
        return copy.deepcopy(self.states.get((session_id, user_id), {}))

    get_persisted_session_state_dict = get_session_state_dict


@pytest.mark.asyncio
async def test_recovery_uses_saved_result_without_reentering_engine(
    execution_setup,
    monkeypatch,
):
    from swe.app.crons.managed_execution import ManagedExecutionService
    from swe.app.crons.managed_receipts import SessionResultReceipts
    from swe.app.crons.managed_results import ExecutionWriter

    db = execution_setup[0]
    row, _ = await enqueue(execution_setup)
    writer, engine, session = ExecutionWriter(db), Engine(), Session()
    original = writer.complete

    async def unavailable(*_args):
        raise RuntimeError("private-db-password")

    monkeypatch.setattr(writer, "complete", unavailable)
    service = ManagedExecutionService(
        writer,
        engine,
        receipts=SessionResultReceipts(session),
    )
    with pytest.raises(RuntimeError):
        await service.execute(row["execution_id"], key(row))
    assert len(engine.calls) == 1
    recovered = ManagedExecutionService(
        ExecutionWriter(db),
        engine,
        receipts=SessionResultReceipts(session),
    )
    assert await recovered.recover(row["execution_id"], key(row))
    assert len(engine.calls) == 1
    assert (
        db.conn.execute(
            "SELECT status FROM swe_cron_execution_runs",
        ).fetchone()[0]
        == "success"
    )
    assert (
        db.conn.execute("SELECT COUNT(*) FROM swe_cron_executions").fetchone()[
            0
        ]
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.name == "nt",
    reason="原有 SafeJSONSession 文件锁依赖 Linux fcntl",
)
async def test_running_recovery_returns_while_task_holds_session_lock(
    execution_setup,
    tmp_path,
):
    from swe.app.crons.managed_execution import ManagedExecutionService
    from swe.app.crons.managed_receipts import SessionResultReceipts
    from swe.app.crons.managed_results import ExecutionWriter
    from swe.app.runner.session import SafeJSONSession

    db = execution_setup[0]
    row, _ = await enqueue(execution_setup)
    writer = ExecutionWriter(db)
    execution_id, identity = row["execution_id"], key(row)
    await writer.accept(execution_id, identity)
    run = await writer.start(execution_id, identity, "worker")
    binding = json.loads(run["spec_json"])["meta"]
    session = SafeJSONSession(save_dir=str(tmp_path))
    service = ManagedExecutionService(
        writer,
        Engine(),
        receipts=SessionResultReceipts(session),
    )

    async with session.execution(
        binding["task_session_id"],
        binding["creator_user_id"],
    ):
        assert not await asyncio.wait_for(
            asyncio.create_task(
                service.recover(execution_id, identity),
                context=Context(),
            ),
            timeout=2,
        )
    assert (await writer.get(execution_id, identity))["status"] == "running"


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.name == "nt",
    reason="原有 SafeJSONSession 文件锁依赖 Linux fcntl",
)
async def test_pending_result_receipt_survives_a_fresh_session_instance(
    execution_setup,
    tmp_path,
):
    from swe.app.crons.managed_receipts import SessionResultReceipts
    from swe.app.crons.managed_results import ExecutionOutcome, ExecutionWriter
    from swe.app.runner.session import SafeJSONSession

    db = execution_setup[0]
    row, _ = await enqueue(execution_setup)
    writer = ExecutionWriter(db)
    await writer.accept(row["execution_id"], key(row))
    run = await writer.start(row["execution_id"], key(row), "worker")
    await SessionResultReceipts(SafeJSONSession(save_dir=str(tmp_path))).save(
        run,
        ExecutionOutcome("success", preview="durable result"),
    )
    loaded = await SessionResultReceipts(
        SafeJSONSession(save_dir=str(tmp_path)),
    ).load(run)
    assert loaded.preview == "durable result"
    assert loaded.status == "success"
