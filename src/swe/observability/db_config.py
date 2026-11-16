# -*- coding: utf-8 -*-
"""Independent MySQL configuration for Agent Observability."""

from __future__ import annotations

import os

from ..database.config import DatabaseConfig


def get_observability_database_config() -> DatabaseConfig | None:
    """Build a dedicated DB config without reading SWE_DB_* values."""
    host = os.environ.get("SWE_AGENTOBS_DB_HOST", "").strip()
    if not host:
        return None
    return DatabaseConfig(
        host=host,
        port=int(os.environ.get("SWE_AGENTOBS_DB_PORT", "3306")),
        user=os.environ.get("SWE_AGENTOBS_DB_USER", ""),
        password=os.environ.get("SWE_AGENTOBS_DB_PASSWORD", ""),
        database=os.environ.get("SWE_AGENTOBS_DB_NAME", "swe_agentobs"),
        min_connections=int(os.environ.get("SWE_AGENTOBS_DB_MIN_CONN", "1")),
        max_connections=int(os.environ.get("SWE_AGENTOBS_DB_MAX_CONN", "5")),
        charset=os.environ.get("SWE_AGENTOBS_DB_CHARSET", "utf8mb4"),
        use_unicode=True,
        ssl_disabled=os.environ.get("SWE_AGENTOBS_DB_SSL_DISABLED", "true").lower()
        in {"1", "true", "yes", "on"},
        time_zone="+00:00",
        acquire_timeout=float(os.environ.get("SWE_AGENTOBS_DB_ACQUIRE_TIMEOUT", "5")),
        connect_timeout=float(os.environ.get("SWE_AGENTOBS_DB_CONNECT_TIMEOUT", "5")),
        read_timeout=float(os.environ.get("SWE_AGENTOBS_DB_READ_TIMEOUT", "5")),
        write_timeout=float(os.environ.get("SWE_AGENTOBS_DB_WRITE_TIMEOUT", "5")),
        cleanup_timeout=1,
    )
