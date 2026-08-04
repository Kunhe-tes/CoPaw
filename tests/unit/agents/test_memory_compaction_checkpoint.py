# -*- coding: utf-8 -*-
"""Staged checkpoint-compaction budget decision coverage."""

from swe.agents.hooks.memory_compaction import decide_context_budget
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
