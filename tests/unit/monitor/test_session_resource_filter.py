# -*- coding: utf-8 -*-
"""Tests for resource-aware tracing session filtering."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from monitor.app.routers.tracing import _validate_session_resource_filter
from monitor.app.services.tracing.query_service import TracingQueryService


class TestSessionResourceFilterValidation:
    def test_omitted_filter_preserves_existing_behavior(self):
        assert _validate_session_resource_filter(None, None, None) == (
            None,
            None,
            None,
        )

    def test_accepts_model_and_skill_filters(self):
        assert _validate_session_resource_filter("model", " gpt-5 ", None) == (
            "model",
            "gpt-5",
            None,
        )
        assert _validate_session_resource_filter(
            "skill",
            " search ",
            None,
        ) == (
            "skill",
            "search",
            None,
        )

    def test_accepts_composite_mcp_tool_filter(self):
        assert _validate_session_resource_filter(
            "mcp_tool",
            " query_customer ",
            " crm ",
        ) == ("mcp_tool", "query_customer", "crm")

    @pytest.mark.parametrize(
        ("resource_type", "resource_name", "mcp_server"),
        [
            (None, "gpt-5", None),
            ("model", None, None),
            ("model", "gpt-5", "crm"),
            ("skill", "search", "crm"),
            ("mcp_tool", "query_customer", None),
        ],
    )
    def test_rejects_incomplete_or_mismatched_filters(
        self,
        resource_type,
        resource_name,
        mcp_server,
    ):
        with pytest.raises(HTTPException) as exc_info:
            _validate_session_resource_filter(
                resource_type,
                resource_name,
                mcp_server,
            )
        assert exc_info.value.status_code == 400


class TestSessionResourceQuery:
    @pytest.fixture
    def service(self):
        db = AsyncMock()
        db.fetch_one.return_value = {"total": 0}
        db.fetch_all.return_value = []
        return TracingQueryService(db)

    @pytest.mark.asyncio
    async def test_no_resource_filter_does_not_add_resource_predicate(
        self,
        service,
    ):
        await service.get_sessions(source_id="tenant-a", user_id="user-1")

        count_sql, count_params = service._db.fetch_one.call_args.args
        data_sql, data_params = service._db.fetch_all.call_args.args

        assert "swe_tracing_traces resource" not in count_sql
        assert "swe_tracing_spans resource" not in count_sql
        assert "swe_tracing_traces resource" not in data_sql
        assert "swe_tracing_spans resource" not in data_sql
        assert count_params == ("tenant-a", "user-1")
        assert "tenant-a" in data_params

    @pytest.mark.asyncio
    async def test_filters_sessions_by_exact_model_with_date_scope(
        self,
        service,
    ):
        start = datetime(2026, 5, 1)
        end = datetime(2026, 6, 1)

        await service.get_sessions(
            source_id="tenant-a",
            start_date=start,
            end_date=end,
            resource_type="model",
            resource_name="gpt-5",
        )

        count_sql, count_params = service._db.fetch_one.call_args.args
        assert "resource.source_id = t.source_id" in count_sql
        assert "resource.session_id = t.session_id" in count_sql
        assert "resource.model_name = %s" in count_sql
        assert "resource.start_time >= %s" in count_sql
        assert "resource.start_time <= %s" in count_sql
        assert count_params == (
            "tenant-a",
            start,
            end,
            "gpt-5",
            start,
            end,
        )

    @pytest.mark.asyncio
    async def test_filters_sessions_by_exact_skill_and_error(self, service):
        await service.get_sessions(
            source_id="tenant-a",
            resource_type="skill",
            resource_name="risk-check",
            has_error=True,
        )

        count_sql, count_params = service._db.fetch_one.call_args.args
        assert "swe_tracing_spans resource" in count_sql
        assert "resource.event_type = 'skill_invocation'" in count_sql
        assert "resource.skill_name = %s" in count_sql
        assert "error_trace.source_id = t.source_id" in count_sql
        assert "error_trace.status = 'error'" in count_sql
        assert count_params == ("tenant-a", "risk-check")

    @pytest.mark.asyncio
    async def test_filters_mcp_tool_by_server_and_tool_name(self, service):
        await service.get_sessions(
            source_id="tenant-a",
            resource_type="mcp_tool",
            resource_name="query_customer",
            mcp_server="crm",
        )

        count_sql, count_params = service._db.fetch_one.call_args.args
        assert "resource.event_type = 'tool_call_end'" in count_sql
        assert "resource.tool_name = %s" in count_sql
        assert "resource.mcp_server = %s" in count_sql
        assert count_params == ("tenant-a", "query_customer", "crm")

    @pytest.mark.asyncio
    async def test_all_sources_filter_keeps_source_isolation(self, service):
        await service.get_sessions(
            source_id="all",
            resource_type="skill",
            resource_name="search",
        )

        count_sql, count_params = service._db.fetch_one.call_args.args
        assert "t.source_id NOT IN" in count_sql
        assert "resource.source_id = t.source_id" in count_sql
        assert count_params[-1] == "search"
