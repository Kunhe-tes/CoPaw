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
