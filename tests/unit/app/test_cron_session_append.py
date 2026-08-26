# -*- coding: utf-8 -*-
"""Cron session delta and execution-key regression coverage."""

from __future__ import annotations

from typing import Any

from swe.app.crons.executor import _build_cron_execution_key
from swe.app.runner.runner import _build_cron_append_state


def _entry(role: str, text: str, timestamp: str) -> dict[str, Any]:
    return {
        "role": role,
        "content": [{"type": "text", "text": text}],
        "timestamp": timestamp,
    }


def _agent_state(entries: list[Any]) -> dict[str, Any]:
    return {
        "memory": {"content": entries},
    }


def test_cron_appends_only_request_delta_and_keeps_existing_agent_fields() -> (
    None
):
    existing: dict[str, Any] = {
        "agent": {
            "model": {"name": "manual-model"},
            "memory": {"content": [_entry("user", "u1", "t1")]},
        },
        "task_runs": [],
    }
    current: dict[str, Any] = _agent_state(
        [_entry("user", "u2", "t2"), _entry("assistant", "a2", "t2")],
    )

    merged, old, new, stripped, committed = _build_cron_append_state(
        existing,
        current,
        None,
        execution_key="job-1:fire-1:session-1",
    )

    assert committed is True
    assert old == existing["agent"]["memory"]["content"]
    assert new == current["memory"]["content"]
    assert stripped == 0
    assert merged["agent"]["model"] == {"name": "manual-model"}
    assert merged["agent"]["memory"]["content"] == old + new
    assert merged["task_runs"][0]["execution_key"] == (
        "job-1:fire-1:session-1"
    )


def test_same_execution_key_is_idempotent() -> None:
    execution_key = "job-1:fire-1:session-1"
    existing: dict[str, Any] = {
        "agent": {"memory": {"content": [_entry("user", "u1", "t1")]}},
        "task_runs": [
            {
                "run_id": "task-run-old",
                "execution_key": execution_key,
                "memory_start": 0,
                "memory_end": 1,
            },
        ],
    }
    current: dict[str, Any] = _agent_state([_entry("assistant", "a1", "t1")])

    merged, old, new, stripped, committed = _build_cron_append_state(
        existing,
        current,
        None,
        execution_key=execution_key,
    )

    assert committed is False
    assert merged is existing
    assert old == existing["agent"]["memory"]["content"]
    assert new == current["memory"]["content"]
    assert stripped == 0


def test_cron_strips_internal_follow_up_before_append() -> None:
    internal = _entry("assistant", "internal", "t2")
    internal["metadata"] = {"swe_internal_follow_up": True}
    visible = _entry("assistant", "visible", "t2")
    existing: dict[str, Any] = {
        "agent": {"memory": {"content": [_entry("user", "u1", "t1")]}},
        "task_runs": [],
    }
    current: dict[str, Any] = _agent_state([[internal, []], [visible, []]])

    merged, old, new, stripped, committed = _build_cron_append_state(
        existing,
        current,
        None,
        execution_key="job-1:fire-2:session-1",
    )

    assert committed is True
    assert stripped == 1
    assert old == existing["agent"]["memory"]["content"]
    assert new == [[visible, []]]
    assert merged["agent"]["memory"]["content"] == old + [[visible, []]]
    assert merged["task_runs"][0]["memory_start"] == 1
    assert merged["task_runs"][0]["memory_end"] == 2


def test_execution_key_uses_scheduler_identity_not_worker_time() -> None:
    assert (
        _build_cron_execution_key(
            job_id="job-1",
            target_session_id="session-1",
            dispatch_meta={
                "scheduled_fire_at": "2026-08-26T09:00:00Z",
            },
        )
        == "job-1:2026-08-26T09:00:00Z:session-1"
    )
    assert (
        _build_cron_execution_key(
            job_id="job-1",
            target_session_id="session-1",
            dispatch_meta={
                "batch_id": "batch-1",
                "intent_id": 7,
            },
        )
        == "job-1:batch-1:7:session-1"
    )
    assert (
        _build_cron_execution_key(
            job_id="job-1",
            target_session_id="session-1",
            dispatch_meta={"cron_is_manual": True},
        )
        == ""
    )
