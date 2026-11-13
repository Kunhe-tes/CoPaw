# -*- coding: utf-8 -*-
"""验证分发后台使用真实源授权创建子任务，不伪造管理员或接收人身份。"""

import json

import pytest

from tests.unit.scheduler.test_managed_cron_distribution import (
    distribution_setup,
    payload,
    source,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("sync_children", [False, True])
async def test_save_parent_syncs_dates_and_optionally_updates_children(
    distribution_setup,
    sync_children,
):
    from scheduler.app.services.cron.managed.distribution import BroadcastStore
    from scheduler.app.services.cron.managed.distribution_worker import (
        BroadcastProcessor,
    )
    from scheduler.app.services.cron.managed.identity import CallerIdentity

    db, caller, management = distribution_setup
    job_id = (await source(distribution_setup))["job_id"]
    store = BroadcastStore(db)
    processor = BroadcastProcessor(
        db,
        management.resources,
        management.platform,
    )
    first = await store.submit(caller, job_id, payload())
    await processor.process(first["task_id"])

    def child():
        return dict(
            db.conn.execute(
                "SELECT * FROM swe_cron_jobs_v2 WHERE tenant_id='carol'",
            ).fetchone(),
        )

    before = child()
    receiver = CallerIdentity("carol", "bank", "default", "carol")
    own_spec = json.loads(before["spec_json"])
    own_spec["name"] = "子任务自定义名称"
    own_spec["runtime"]["timeout_seconds"] = 321
    await management.update(
        receiver,
        before["job_id"],
        {
            "request_id": "own-name",
            "expected_definition_version": before["definition_version"],
            "spec": own_spec,
        },
    )
    root_spec = json.loads(
        db.conn.execute(
            "SELECT spec_json FROM swe_cron_jobs_v2 WHERE job_id=?",
            (job_id,),
        ).fetchone()[0],
    )
    period = {"start_date": "2099-01-01", "end_date": "2099-12-31"}
    root_spec.update(text="修改后的正文", run_date_range=period)
    root_spec["meta"]["notification_delay_minutes"] = 20
    root_spec["runtime"]["max_concurrency"] = 2
    body = {
        "request_id": "save-root",
        "expected_definition_version": 1,
        "expected_management_version": db.conn.execute(
            "SELECT management_version FROM swe_cron_job_states WHERE job_id=?",
            (job_id,),
        ).fetchone()[0],
        "sync_children": sync_children,
        "spec": root_spec,
    }
    operation = await management.update(caller, job_id, body)
    assert operation["status"] == "completed"
    assert await management.update(caller, job_id, body) == operation
    assert json.loads(child()["spec_json"])["run_date_range"] == period
    if sync_children:
        await processor.process(operation["broadcast_task_id"])
        result = await store.get(
            caller,
            job_id,
            operation["broadcast_task_id"],
        )
        assert result["success_count"] == 2
    else:
        assert "broadcast_task_id" not in operation
    after = child()
    assert after["job_id"] == before["job_id"]
    assert after["cron_expr"] == before["cron_expr"]
    assert after["offset_minutes"] == before["offset_minutes"]
    assert after["name"] == "子任务自定义名称"
    after_spec = json.loads(after["spec_json"])
    assert after_spec["text"] == (
        "修改后的正文" if sync_children else "report"
    )
    assert after_spec["meta"].get("notification_delay_minutes", 0) == (
        20 if sync_children else 0
    )
    assert after_spec["runtime"]["timeout_seconds"] == 321
    assert after_spec["meta"]["broadcast_original_cron"] == "0 9 * * *"
    assert after_spec["runtime"]["max_concurrency"] == (
        2 if sync_children else 1
    )
    await _assert_schedule_updates(
        distribution_setup,
        processor,
        job_id,
        root_spec,
        sync_children,
        child,
    )


async def _assert_schedule_updates(
    distribution_setup,
    processor,
    job_id,
    root_spec,
    sync_children,
    child,
):
    _, caller, management = distribution_setup
    before = child()
    root_spec["run_date_range"] = None
    root_spec["schedule"]["cron"] = "0 10 * * *"
    root_spec["name"] = "同步排程时修改的名称"
    cleared = await management.update(
        caller,
        job_id,
        {
            "request_id": "clear-root-dates",
            "expected_definition_version": 2,
            "sync_children": sync_children,
            "spec": root_spec,
        },
    )
    assert cleared["status"] == "completed"
    assert json.loads(child()["spec_json"])["run_date_range"] is None
    await processor.process(cleared["broadcast_task_id"])
    assert child()["cron_expr"] == "0 8 * * *"
    assert child()["offset_minutes"] == before["offset_minutes"]
    assert child()["name"] == (
        root_spec["name"] if sync_children else "子任务自定义名称"
    )

    root_spec["schedule"]["timezone"] = "UTC"
    changed_zone = await management.update(
        caller,
        job_id,
        {
            "request_id": "change-timezone",
            "expected_definition_version": 3,
            "sync_children": sync_children,
            "spec": root_spec,
        },
    )
    assert changed_zone["status"] == "completed"
    await processor.process(changed_zone["broadcast_task_id"])
    assert child()["timezone"] == "UTC"
    assert child()["cron_expr"] == "0 8 * * *"
    assert child()["offset_minutes"] == before["offset_minutes"]
    assert (
        json.loads(child()["spec_json"])["meta"]["broadcast_original_timezone"]
        == "UTC"
    )


@pytest.mark.asyncio
async def test_worker_creates_batch_children_without_individual_batch_timers(
    distribution_setup,
    monkeypatch,
):
    from scheduler.app.services.cron.managed.distribution import BroadcastStore
    from scheduler.app.services.cron.managed.distribution_worker import (
        BroadcastProcessor,
    )

    db, caller, management = distribution_setup
    created = await source(distribution_setup)
    task = await BroadcastStore(db).submit(
        caller,
        created["job_id"],
        payload(),
    )
    calls = []
    prepare = management.resources.prepare

    async def checked(operation, actor):
        calls.append((actor.actor_id, actor.tenant_id, actor.is_manager))
        return await prepare(operation, actor)

    monkeypatch.setattr(management.resources, "prepare", checked)
    await BroadcastProcessor(
        db,
        management.resources,
        management.platform,
    ).process(task["task_id"])
    result = await BroadcastStore(db).get(
        caller,
        created["job_id"],
        task["task_id"],
    )
    assert result["status"] == "succeeded"
    assert result["success_count"] == 2
    assert calls == [("alice", "bob", False), ("alice", "carol", False)]
    children = db.conn.execute(
        "SELECT * FROM swe_cron_jobs_v2 WHERE parent_job_id=?",
        (created["job_id"],),
    ).fetchall()
    assert len(children) == 2
    assert all(row["creator_user_id"] == row["tenant_id"] for row in children)
    assert all(row["job_origin"] == "broadcast" for row in children)
    assert all(
        json.loads(row["spec_json"])["meta"]["creator_user_id"]
        == row["tenant_id"]
        for row in children
    )
    assert management.platform.calls.count("register") == 1
    assert "enable" not in management.platform.calls
    assert all(
        row[0] == "alice"
        for row in db.conn.execute(
            "SELECT actor_id FROM swe_cron_registration_journal",
        ).fetchall()
    )


@pytest.mark.asyncio
async def test_terminated_round_is_not_reprocessed_and_new_round_reuses_child_identity(
    distribution_setup,
):
    from scheduler.app.services.cron.managed.distribution import BroadcastStore
    from scheduler.app.services.cron.managed.distribution_worker import (
        BroadcastProcessor,
    )

    db, caller, management = distribution_setup
    created = await source(distribution_setup)
    store = BroadcastStore(db)
    processor = BroadcastProcessor(
        db,
        management.resources,
        management.platform,
    )
    first = await store.submit(caller, created["job_id"], payload())
    await processor.process(first["task_id"])
    before = list(management.resources.prepared)
    await processor.process(first["task_id"])
    assert management.resources.prepared == before
    second = await store.submit(
        caller,
        created["job_id"],
        payload("new-round"),
    )
    await processor.process(second["task_id"])
    original = await store.get(caller, created["job_id"], first["task_id"])
    repeated = await store.get(caller, created["job_id"], second["task_id"])
    assert [row["job_id"] for row in original["results"]] == [
        row["job_id"] for row in repeated["results"]
    ]
    assert all(row["operation"] == "updated" for row in repeated["results"])


@pytest.mark.asyncio
async def test_zero_target_retime_keeps_recipient_content_pause_and_resources(
    distribution_setup,
):
    from scheduler.app.services.cron.managed.controls import ControlService
    from scheduler.app.services.cron.managed.distribution import BroadcastStore
    from scheduler.app.services.cron.managed.distribution_worker import (
        BroadcastProcessor,
    )
    from scheduler.app.services.cron.managed.identity import CallerIdentity

    db, caller, management = distribution_setup
    created = await source(distribution_setup)
    store = BroadcastStore(db)
    processor = BroadcastProcessor(
        db,
        management.resources,
        management.platform,
    )
    first = await store.submit(caller, created["job_id"], payload())
    await processor.process(first["task_id"])
    child = dict(
        db.conn.execute(
            "SELECT * FROM swe_cron_jobs_v2 WHERE tenant_id='bob'",
        ).fetchone(),
    )
    receiver = CallerIdentity("bob", "bank", "default", "bob")
    spec = json.loads(child["spec_json"])
    spec.update(name="接收人自己的名称", text="接收人自己的正文")
    await management.update(
        receiver,
        child["job_id"],
        {
            "request_id": "recipient-edit",
            "expected_definition_version": 1,
            "spec": spec,
        },
    )
    state = dict(
        db.conn.execute(
            "SELECT * FROM swe_cron_job_states WHERE tenant_id='bob'",
        ).fetchone(),
    )
    await ControlService(db, management.platform).set_enabled(
        receiver,
        child["job_id"],
        {
            "request_id": "recipient-pause",
            "enabled": False,
            "expected_management_version": state["management_version"],
        },
    )
    prepared_count = len(management.resources.prepared)
    retime = await store.submit(
        caller,
        created["job_id"],
        {**payload("retime", targets=[]), "offset_window_hours": 1},
    )
    await processor.process(retime["task_id"])
    result = await store.get(caller, created["job_id"], retime["task_id"])
    assert result["status"] == "succeeded"
    updated = dict(
        db.conn.execute(
            "SELECT * FROM swe_cron_jobs_v2 WHERE job_id=?",
            (child["job_id"],),
        ).fetchone(),
    )
    actual = json.loads(updated["spec_json"])
    assert actual["name"] == "接收人自己的名称"
    assert actual["text"] == "接收人自己的正文"
    assert not updated["enabled"]
    assert len(management.resources.prepared) == prepared_count


@pytest.mark.asyncio
async def test_failed_target_uses_new_round_and_reuses_reserved_child(
    distribution_setup,
    monkeypatch,
):
    from scheduler.app.services.cron.managed.distribution import BroadcastStore
    from scheduler.app.services.cron.managed.distribution_worker import (
        BroadcastProcessor,
    )
    from scheduler.app.services.cron.managed.operations import (
        ManagementConflict,
    )

    db, caller, management = distribution_setup
    created = await source(distribution_setup)
    store = BroadcastStore(db)
    processor = BroadcastProcessor(
        db,
        management.resources,
        management.platform,
    )
    prepare = management.resources.prepare
    failing = True

    async def sometimes_fails(operation, actor):
        if actor.tenant_id == "bob" and failing:
            raise ValueError("private-provider-credential")
        return await prepare(operation, actor)

    monkeypatch.setattr(management.resources, "prepare", sometimes_fails)
    first = await store.submit(caller, created["job_id"], payload())
    await processor.process(first["task_id"])
    failed = await store.get(caller, created["job_id"], first["task_id"])
    assert failed["status"] == "partial_failed"
    bob = next(row for row in failed["results"] if row["tenant_id"] == "bob")
    operation = db.conn.execute(
        "SELECT operation_id FROM swe_cron_registration_journal WHERE job_id=?",
        (bob["job_id"],),
    ).fetchone()
    from scheduler.app.services.cron.managed.identity import CallerIdentity

    with pytest.raises(ManagementConflict, match="new_round"):
        await management.retry(
            CallerIdentity("bob", "bank", "default", "alice"),
            bob["job_id"],
            operation["operation_id"],
        )
    failing = False
    next_round = await store.submit(
        caller,
        created["job_id"],
        payload("retry-new-round", targets=[{"tenant_id": "bob"}]),
    )
    await processor.process(next_round["task_id"])
    fixed = await store.get(caller, created["job_id"], next_round["task_id"])
    assert fixed["status"] == "succeeded"
    assert fixed["results"][0]["job_id"] == bob["job_id"]
    assert (
        db.conn.execute(
            "SELECT enabled FROM swe_cron_jobs_v2 WHERE job_id=?",
            (bob["job_id"],),
        ).fetchone()[0]
        == 1
    )


@pytest.mark.asyncio
async def test_deleted_child_is_recreated_only_by_explicit_new_round(
    distribution_setup,
):
    from scheduler.app.services.cron.managed.distribution import BroadcastStore
    from scheduler.app.services.cron.managed.distribution_worker import (
        BroadcastProcessor,
    )
    from scheduler.app.services.cron.managed.identity import CallerIdentity

    db, caller, management = distribution_setup
    created = await source(distribution_setup)
    store = BroadcastStore(db)
    processor = BroadcastProcessor(
        db,
        management.resources,
        management.platform,
    )
    first = await store.submit(
        caller,
        created["job_id"],
        payload(targets=[{"tenant_id": "bob"}]),
    )
    await processor.process(first["task_id"])
    before = await store.get(caller, created["job_id"], first["task_id"])
    old_id = before["results"][0]["job_id"]
    await management.delete(
        CallerIdentity("bob", "bank", "default", "alice"),
        old_id,
        {"request_id": "delete-old-child", "expected_definition_version": 1},
    )
    await processor.process(first["task_id"])
    assert (
        db.conn.execute(
            "SELECT COUNT(*) FROM swe_cron_jobs_v2 WHERE parent_job_id=? AND deleted_at IS NULL",
            (created["job_id"],),
        ).fetchone()[0]
        == 0
    )
    next_round = await store.submit(
        caller,
        created["job_id"],
        payload("replace-deleted", targets=[{"tenant_id": "bob"}]),
    )
    await processor.process(next_round["task_id"])
    after = await store.get(caller, created["job_id"], next_round["task_id"])
    assert after["status"] == "succeeded"
    assert after["results"][0]["job_id"] != old_id
    assert db.conn.execute(
        "SELECT deleted_at FROM swe_cron_jobs_v2 WHERE job_id=?",
        (old_id,),
    ).fetchone()[0]
