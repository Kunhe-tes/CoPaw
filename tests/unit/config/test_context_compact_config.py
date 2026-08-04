# -*- coding: utf-8 -*-
"""Tests for staged proactive context-compaction configuration."""

import pytest
from pydantic import ValidationError

from swe.config.config import ContextCompactConfig


def test_context_compact_defaults_define_confirmed_stages() -> None:
    config = ContextCompactConfig()

    assert (
        config.lightweight_governance_ratio,
        config.precompaction_step_ratio,
        config.memory_compact_ratio,
        config.emergency_compact_ratio,
    ) == (0.65, 0.05, 0.80, 0.90)


def test_context_compact_rejects_non_monotonic_stage_ratios() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ContextCompactConfig(
            lightweight_governance_ratio=0.70,
            memory_compact_ratio=0.65,
            emergency_compact_ratio=0.90,
        )

    assert "lightweight, active, and emergency" in str(exc_info.value)


@pytest.mark.parametrize(
    (
        "legacy_active_ratio",
        "active_ratio",
        "lightweight_ratio",
        "step_ratio",
        "emergency_ratio",
    ),
    [
        (0.30, 0.31, 0.30, 0.01, 0.90),
        (0.50, 0.50, 0.45, 0.05, 0.90),
        (0.65, 0.65, 0.60, 0.05, 0.90),
        (0.90, 0.89, 0.65, 0.05, 0.94),
    ],
)
def test_legacy_active_threshold_is_migrated_to_a_valid_stage_sequence(
    legacy_active_ratio: float,
    active_ratio: float,
    lightweight_ratio: float,
    step_ratio: float,
    emergency_ratio: float,
) -> None:
    config = ContextCompactConfig.model_validate(
        {"memory_compact_ratio": legacy_active_ratio},
    )

    assert (
        config.memory_compact_ratio,
        config.lightweight_governance_ratio,
        config.precompaction_step_ratio,
        config.emergency_compact_ratio,
    ) == (active_ratio, lightweight_ratio, step_ratio, emergency_ratio)
