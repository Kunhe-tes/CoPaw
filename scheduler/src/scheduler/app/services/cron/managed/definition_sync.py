# -*- coding: utf-8 -*-
"""将父任务基本配置的变更登记为仅更新既有子任务的一轮分发。"""

import copy
import json

from .definition import canonical
from .distribution import (
    BroadcastStore,
    ITEMS,
    TASKS,
    _children,
    _reserved_item,
)
from .identity import CallerIdentity
from .operations import IDENTITY_FIELDS
from .scatter import shift_cron_expression
from .storage import insert


def changed_fields(previous, spec):
    fields = (
        "name",
        "task_type",
        "text",
        "model_slot",
        "skill_ids",
        "recheck",
    )
    changes = {
        name: spec.get(name)
        for name in fields
        if previous.get(name) != spec.get(name)
    }
    if "task_type" in changes:
        for name in ("text", "request", "model_slot", "skill_ids", "recheck"):
            changes[name] = spec.get(name)
    elif previous.get("request") is not None and spec.get("request") is None:
        changes["request"] = None
    for name, ignored in (
        ("request", {"user_id", "session_id"}),
        ("dispatch", {"target"}),
        ("runtime", set()),
        ("schedule", {"type"}),
    ):
        if name in changes:
            continue
        before = previous.get(name) or {}
        if name == "schedule":
            before = {"run_on_non_workday": False, **before}
        delta = {
            key: value
            for key, value in (spec.get(name) or {}).items()
            if key not in ignored and value != before.get(key)
        }
        if delta:
            changes[name] = delta
    delay = spec.get("meta", {}).get("notification_delay_minutes", 0)
    if delay != previous.get("meta", {}).get("notification_delay_minutes", 0):
        changes["meta"] = {"notification_delay_minutes": delay}
    return changes


async def enqueue_child_sync(tx, operation, version, state, spec):
    key = tuple(operation[name] for name in IDENTITY_FIELDS)
    children = await _children(tx, key, [])
    if not children:
        return None
    task_id = operation["operation_id"]
    payload = json.loads(operation["payload_json"])
    caller = CallerIdentity(
        *key[:3],
        operation["actor_id"],
        payload["actor_is_manager"],
    )
    task = BroadcastStore._new_task(
        caller,
        {
            **dict(zip(IDENTITY_FIELDS, key)),
            "definition_version": version,
            "state_dispatch_state": state["dispatch_state"],
            "spec_json": canonical(spec),
        },
        {
            "request_id": operation["request_id"],
            "targets": [],
            "enable_offset": False,
            "offset_window_hours": 0,
        },
        task_id,
        operation["request_hash"],
    )
    task["payload_json"] = canonical(
        {
            **json.loads(task["payload_json"]),
            "retime_only": False,
            "definition_changes": payload["child_definition_changes"],
        },
    )
    task["tenant_count"] = len(children)
    await insert(tx, TASKS, task)
    for index, child in enumerate(children, 1):
        await insert(
            tx,
            ITEMS,
            _reserved_item(
                task,
                child,
                child,
                index,
                child["offset_minutes"] or 0,
                False,
            ),
        )
    return task_id


async def batch_platform_spec(db, key, spec):
    row = await db.fetch_one(
        "SELECT MAX(offset_minutes) AS advance FROM swe_cron_jobs_v2 "
        "WHERE parent_tenant_id=%s AND parent_source_id=%s AND parent_agent_id=%s "
        "AND parent_job_id=%s AND management_owner='scheduler' AND deleted_at IS NULL",
        key,
    )
    advance = int(row["advance"] or 0)
    if not advance:
        return spec
    schedule = spec["schedule"]
    shifted = shift_cron_expression(
        schedule["cron"],
        schedule["timezone"],
        offset_minutes=advance,
    )
    if shifted.error:
        raise ValueError("batch_timer_cron_not_shiftable")
    platform_spec = copy.deepcopy(spec)
    platform_spec["schedule"]["cron"] = shifted.cron
    platform_spec["meta"]["_scheduler_calendar_advance_minutes"] = advance
    return platform_spec
