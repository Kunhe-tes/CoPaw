# -*- coding: utf-8 -*-
"""Retry-policy resolution owned by query execution."""

from __future__ import annotations

from typing import Any

from swe.app.runner import query_attempt
from swe.app.source_system_config import resolve_query_retry_config
from swe.config.config import load_agent_config


def load_retry_settings(
    *,
    agent_id: str,
    tenant_id: str | None,
    agent_config: Any | None = None,
) -> tuple[int, int, float, float]:
    """Resolve retry settings with the historic single-attempt fallback."""
    config = agent_config
    try:
        if config is None:
            config = load_agent_config(agent_id, tenant_id=tenant_id)
    except Exception:
        pass
    enabled, max_retries, backoff_base, backoff_cap = (
        query_attempt.extract_retry_config(_resolve_source_override(config))
    )
    return (
        max_retries + 1 if enabled else 1,
        max_retries,
        backoff_base,
        backoff_cap,
    )


def _resolve_source_override(agent_config: Any | None) -> Any | None:
    """Apply the current source's explicit retry override when available."""
    if agent_config is None:
        return None
    try:
        running = getattr(agent_config, "running", None)
        if running is None or getattr(running, "query_retry", None) is None:
            return agent_config
        resolved = resolve_query_retry_config(running.query_retry)
        if hasattr(agent_config, "model_copy"):
            return agent_config.model_copy(
                update={
                    "running": running.model_copy(
                        update={"query_retry": resolved},
                    ),
                },
            )
        setattr(running, "query_retry", resolved)
    except Exception:
        return agent_config
    return agent_config
