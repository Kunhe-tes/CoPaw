# -*- coding: utf-8 -*-
"""Staged checkpoint-compaction budget decision coverage."""

import pytest

from swe.agents.hooks.memory_compaction import decide_context_budget
from swe.agents.hooks.memory_compaction import MemoryCompactionHook
from swe.config.config import ContextCompactConfig


def test_budget_stages_follow_confirmed_65_5_80_90_contract() -> None:
    config = ContextCompactConfig()

    assert decide_context_budget(64, 100, config).stage == "normal"
    assert decide_context_budget(65, 100, config).stage == "governance"
    assert decide_context_budget(69, 100, config).precompaction_watermark == 0
    assert decide_context_budget(70, 100, config).precompaction_watermark == 1
    assert decide_context_budget(80, 100, config).stage == "active"
    assert decide_context_budget(90, 100, config).stage == "emergency"


def test_budget_decision_rejects_invalid_window() -> None:
    config = ContextCompactConfig()

    try:
        decide_context_budget(1, 0, config)
    except ValueError as exc:
        assert "max_input_length" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("zero input window must be rejected")


@pytest.mark.asyncio
async def test_governance_schedules_only_new_watermarks() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    manager = SimpleNamespace(schedule_precompaction=AsyncMock())
    hook = MemoryCompactionHook(manager)
    agent = SimpleNamespace(
        _request_context={"chat_id": "chat-1"},
        model=object(),
        formatter=object(),
    )
    running = SimpleNamespace(
        max_input_length=100,
        context_compact=ContextCompactConfig(),
    )

    assert await hook._apply_checkpoint_budget_stage(agent, running, [], 65)
    assert await hook._apply_checkpoint_budget_stage(agent, running, [], 69)
    assert await hook._apply_checkpoint_budget_stage(agent, running, [], 70)

    assert manager.schedule_precompaction.await_count == 2
    assert (
        manager.schedule_precompaction.await_args_list[0].kwargs["watermark"]
        == 0
    )
    assert (
        manager.schedule_precompaction.await_args_list[1].kwargs["watermark"]
        == 1
    )


@pytest.mark.asyncio
async def test_active_stage_installs_ready_candidate_before_reme() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    manager = SimpleNamespace(
        install_ready_precompaction=AsyncMock(return_value=True),
    )
    hook = MemoryCompactionHook(manager)
    agent = SimpleNamespace(_request_context={"chat_id": "chat-1"})
    running = SimpleNamespace(
        max_input_length=100,
        context_compact=ContextCompactConfig(),
    )

    assert await hook._apply_checkpoint_budget_stage(agent, running, [], 80)
    manager.install_ready_precompaction.assert_awaited_once_with(
        chat_id="chat-1",
    )
