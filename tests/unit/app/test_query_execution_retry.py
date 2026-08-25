# -*- coding: utf-8 -*-
"""Contract tests for query retry execution helpers."""

from __future__ import annotations

from types import SimpleNamespace

from swe.app.runner.query_execution.retry import load_retry_settings


def test_load_retry_settings_uses_explicit_agent_configuration() -> None:
    agent_config = SimpleNamespace(
        running=SimpleNamespace(
            query_retry=SimpleNamespace(
                enabled=True,
                max_retries=2,
                backoff_base=3.0,
                backoff_cap=12.0,
            ),
        ),
    )

    assert load_retry_settings(
        agent_id="test-agent",
        tenant_id="tenant-1",
        agent_config=agent_config,
    ) == (3, 2, 3.0, 12.0)
