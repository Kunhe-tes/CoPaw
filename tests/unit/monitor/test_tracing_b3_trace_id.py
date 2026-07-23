# -*- coding: utf-8 -*-
"""Tests for B3 correlation IDs in Monitor trace detail mapping."""

from datetime import datetime, timedelta, timezone

from monitor.app.services.tracing.query_service import TracingQueryService


def _complete_trace_row() -> dict[str, object]:
    """Build a realistic database row returned by the trace detail query."""
    start_time = datetime(2026, 7, 16, 8, 0, tzinfo=timezone.utc)
    return {
        "trace_id": "internal-trace",
        "b3_trace_id": "shared-b3",
        "source_id": "copaw",
        "user_id": "user-123",
        "user_name": "Trace User",
        "bbk_id": "201",
        "session_id": "session-456",
        "session_name": "B3 trace mapping",
        "channel": "cron",
        "start_time": start_time,
        "end_time": start_time + timedelta(seconds=2),
        "duration_ms": 2000,
        "model_name": "qwen-max",
        "total_input_tokens": 120,
        "total_output_tokens": 45,
        "tools_used": '["search"]',
        "skills_used": '["monitoring"]',
        "status": "completed",
        "error": None,
        "user_message": "Check the scheduled task.",
    }


def _query_service_without_database() -> TracingQueryService:
    """Create the service without a DB because the mapper has no state."""
    return TracingQueryService.__new__(TracingQueryService)


def test_row_to_trace_maps_internal_and_b3_trace_ids() -> None:
    trace = _query_service_without_database()._row_to_trace(
        _complete_trace_row(),
    )

    assert trace.trace_id == "internal-trace"
    assert trace.b3_trace_id == "shared-b3"


def test_row_to_trace_defaults_missing_b3_trace_id_to_none() -> None:
    legacy_row = _complete_trace_row()
    legacy_row.pop("b3_trace_id")

    trace = _query_service_without_database()._row_to_trace(legacy_row)

    assert trace.trace_id == "internal-trace"
    assert trace.b3_trace_id is None
