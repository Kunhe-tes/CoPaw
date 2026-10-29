# -*- coding: utf-8 -*-
"""只对当日失败补跑标记生效的执行前保护及同链历史替换。"""

import json
from uuid import UUID

MARKER = "daily_failure_retry"
KEYS = ("tenant_id", "source_id", "agent_id", "job_id")
WHERE = " AND ".join(f"`{name}`=%s" for name in KEYS)


def _object(value):
    try:
        parsed = json.loads(value or "{}")
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def daily_metadata(run):
    value = _object(run["dispatch_meta_json"]).get(MARKER)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("cron_daily_retry_history_marker_invalid")
    for name in ("call_id", "root_execution_id", "previous_execution_id"):
        try:
            UUID(value[name])
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ValueError(
                "cron_daily_retry_history_marker_invalid",
            ) from exc
    if type(value.get("retry_count")) is not int or value["retry_count"] < 1:
        raise ValueError("cron_daily_retry_history_count_invalid")
    return {
        name: value[name]
        for name in (
            "call_id",
            "root_execution_id",
            "previous_execution_id",
            "retry_count",
        )
    }


async def newer_success_exists(db, run):
    if daily_metadata(run) is None:
        return False
    key = tuple(run[name] for name in KEYS)
    row = await db.fetch_one(
        "SELECT execution_id FROM swe_cron_execution_runs "
        f"WHERE {WHERE} AND queue_order>%s AND kind IN ('ordinary','batch') "
        "AND JSON_UNQUOTE(JSON_EXTRACT(dispatch_meta_json,'$.protocol'))='scheduler_managed_v1' "
        "AND status='success' AND settled_status='success' LIMIT 1",
        (*key, run["queue_order"]),
    )
    return row is not None


def _check_history(run, previous, history, marker):
    if previous is None or history is None:
        raise ValueError("cron_daily_retry_history_missing")
    meta = _object(history.get("meta"))
    expected = {
        "management_owner": "scheduler",
        "managed_execution_id": previous["execution_id"],
        "source_id": run["source_id"],
        "agent_id": run["agent_id"],
    }
    if (
        history["job_id"] != run["job_id"]
        or history["tenant_id"] != run["tenant_id"]
        or not all(meta.get(name) == value for name, value in expected.items())
    ):
        raise ValueError("cron_daily_retry_history_identity_invalid")
    prior = daily_metadata(previous)
    if prior:
        if (
            marker["root_execution_id"] != prior["root_execution_id"]
            or marker["retry_count"] != prior["retry_count"] + 1
        ):
            raise ValueError("cron_daily_retry_history_chain_invalid")
    elif marker["retry_count"] != 1:
        raise ValueError("cron_daily_retry_history_chain_invalid")


async def _check_batch(db, run, previous, marker):
    meta = _object(run["dispatch_meta_json"])
    prior_meta = _object(previous["dispatch_meta_json"])
    if not meta.get("batch_id"):
        if previous["kind"] != "ordinary" or marker["root_execution_id"] != (
            daily_metadata(previous) or {}
        ).get("root_execution_id", previous["execution_id"]):
            raise ValueError("cron_daily_retry_history_chain_invalid")
        return
    if prior_meta.get("batch_id") not in (None, meta["batch_id"]):
        raise ValueError("cron_daily_retry_history_batch_invalid")
    member = await db.fetch_one(
        "SELECT * FROM swe_cron_managed_batch_members "
        f"WHERE batch_id=%s AND member_id=%s AND {WHERE} FOR UPDATE",
        (
            meta["batch_id"],
            meta.get("batch_member_id"),
            *(run[name] for name in KEYS),
        ),
    )
    if (
        member is None
        or member["initial_execution_id"] != marker["root_execution_id"]
        or member["current_execution_id"] != run["execution_id"]
    ):
        raise ValueError("cron_daily_retry_history_batch_invalid")


async def finalize_daily_history(db, run):
    """调用方已在新历史事务中持有定义/执行锁，失败则整体回滚。"""
    marker = daily_metadata(run)
    if marker is None:
        return False
    meta = _object(run["dispatch_meta_json"])
    if meta.get("previous_execution_id") != marker["previous_execution_id"]:
        raise ValueError("cron_daily_retry_history_chain_invalid")
    previous = await db.fetch_one(
        f"SELECT * FROM swe_cron_execution_runs WHERE execution_id=%s AND {WHERE} FOR UPDATE",
        (marker["previous_execution_id"], *(run[name] for name in KEYS)),
    )
    history = None
    if previous is not None:
        history = await db.fetch_one(
            "SELECT * FROM swe_cron_executions WHERE id=%s FOR UPDATE",
            (previous["history_execution_id"],),
        )
    _check_history(run, previous, history, marker)
    await _check_batch(db, run, previous, marker)
    await db.execute(
        "UPDATE swe_cron_executions SET is_final=0 WHERE id=%s AND job_id=%s AND tenant_id=%s",
        (previous["history_execution_id"], run["job_id"], run["tenant_id"]),
    )
    return True
