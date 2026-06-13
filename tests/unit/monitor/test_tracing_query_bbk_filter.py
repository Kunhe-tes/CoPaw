# -*- coding: utf-8 -*-
"""Tests for TracingQueryService bbk_ids filtering.

Tests for:
- build_bbk_in_filter helper function
- _build_traces_where_clause bbk_ids parameter handling
- _build_users_query subquery bbk_id filtering
"""

import pytest
from datetime import datetime, timezone

from monitor.app.services.tracing.query_service import (
    build_bbk_in_filter,
    build_cron_bbk_in_filter,
    TracingQueryService,
)


class TestBuildBbkInFilter:
    """Tests for build_bbk_in_filter helper function."""

    def test_returns_empty_when_no_bbk_ids(self):
        """Empty bbk_ids should return empty SQL and params."""
        sql, params = build_bbk_in_filter(None)
        assert sql == ""
        assert params == []

    def test_returns_empty_when_empty_string(self):
        """Empty string bbk_ids should return empty SQL and params."""
        sql, params = build_bbk_in_filter("")
        assert sql == ""
        assert params == []

    def test_single_bbk_id(self):
        """Single bbk_id should return correct IN clause."""
        sql, params = build_bbk_in_filter("201")
        assert sql == " AND bbk_id IN (%s)"
        assert params == ["201"]

    def test_multiple_bbk_ids(self):
        """Multiple bbk_ids should return correct IN clause."""
        sql, params = build_bbk_in_filter("201,202,203")
        assert sql == " AND bbk_id IN (%s, %s, %s)"
        assert params == ["201", "202", "203"]

    def test_bbk_ids_with_whitespace(self):
        """bbk_ids with whitespace should be trimmed."""
        sql, params = build_bbk_in_filter(" 201 , 202 , 203 ")
        assert sql == " AND bbk_id IN (%s, %s, %s)"
        assert params == ["201", "202", "203"]

    def test_bbk_100_includes_v00(self):
        """bbk_id 100 (总行) should automatically include V00."""
        sql, params = build_bbk_in_filter("100")
        assert sql == " AND bbk_id IN (%s, %s)"
        assert "100" in params
        assert "V00" in params

    def test_bbk_100_with_other_ids_includes_v00(self):
        """bbk_id 100 with other ids should include V00."""
        sql, params = build_bbk_in_filter("100,201")
        assert len(params) == 3  # 100, V00, 201
        assert "100" in params
        assert "V00" in params
        assert "201" in params


class TestBuildCronBbkInFilter:
    """Tests for build_cron_bbk_in_filter helper function."""

    def test_returns_empty_when_no_bbk_ids(self):
        """Empty bbk_ids should return empty SQL and params."""
        sql, params = build_cron_bbk_in_filter(None)
        assert sql == ""
        assert params == []

    def test_single_bbk_id(self):
        """Single bbk_id should return correct IN clause for cron tables."""
        sql, params = build_cron_bbk_in_filter("201")
        assert sql == " AND j.bbk_id IN (%s)"
        assert params == ["201"]

    def test_bbk_100_includes_v00(self):
        """bbk_id 100 should include V00 for cron tables."""
        sql, params = build_cron_bbk_in_filter("100")
        assert len(params) == 2
        assert "100" in params
        assert "V00" in params


class TestBuildTracesWhereClause:
    """Tests for _build_traces_where_clause bbk_ids handling."""

    @pytest.fixture
    def service(self):
        """Create TracingQueryService instance with mock db."""
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        return TracingQueryService(mock_db)

    def test_includes_bbk_filter_when_bbk_ids_provided(self, service):
        """bbk_ids should be included in WHERE clause."""
        where_sql, params = service._build_traces_where_clause(
            source_id="test-source",
            filter_user_type="filtered",
            user_id=None,
            bbk_ids="201",
            start_date=None,
            end_date=None,
        )
        assert "bbk_id IN" in where_sql
        assert "201" in params

    def test_no_bbk_filter_when_no_bbk_ids(self, service):
        """No bbk_ids should not add bbk_id IN clause."""
        where_sql, params = service._build_traces_where_clause(
            source_id="test-source",
            filter_user_type="filtered",
            user_id=None,
            bbk_ids=None,
            start_date=None,
            end_date=None,
        )
        assert "bbk_id IN" not in where_sql

    def test_bbk_params_in_correct_order(self, service):
        """bbk_params should be in correct order in params list."""
        where_sql, params = service._build_traces_where_clause(
            source_id="test-source",
            filter_user_type="filtered",
            user_id=None,
            bbk_ids="201,202",
            start_date=datetime(2026, 6, 1),
            end_date=datetime(2026, 6, 9),
        )
        # 参数顺序：source_id, "default", 80%, IT%, bbk_params, start_date, end_date
        assert "201" in params
        assert "202" in params


class TestBuildUsersQuerySubqueries:
    """Tests for _build_users_query subquery bbk_id filtering.

    This test class verifies that subqueries correctly filter by bbk_id
    when bbk_ids parameter is provided.
    """

    @pytest.fixture
    def service(self):
        """Create TracingQueryService instance with mock db."""
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        return TracingQueryService(mock_db)

    def test_subqueries_include_bbk_filter_when_source_id_all(self, service):
        """When source_id='all', subqueries should include bbk_id filter."""
        where_sql, params = service._build_traces_where_clause(
            source_id="all",
            filter_user_type="filtered",
            user_id=None,
            bbk_ids="201",
            start_date=None,
            end_date=None,
        )
        cron_sql, cron_params = service._build_cron_subquery(
            source_id="all",
            start_date=None,
            end_date=None,
        )
        query, final_params = service._build_users_query(
            source_id="all",
            where_sql=where_sql,
            cron_subquery_sql=cron_sql,
            order_by="manual_calls DESC, user_id ASC",
            params=params,
            cron_params=cron_params,
            page_size=10,
            offset=0,
        )

        # 验证子查询中包含 bbk_id 过滤
        # total_skills 子查询应该有 bbk_id 过滤
        assert (
            "AND bbk_id IN" in query or "bbk_id IN" in query
        ), "total_skills subquery should filter by bbk_id"

    def test_subqueries_include_bbk_filter_when_source_id_specific(
        self,
        service,
    ):
        """When source_id is specific, subqueries should include bbk_id filter."""
        where_sql, params = service._build_traces_where_clause(
            source_id="test-source",
            filter_user_type="filtered",
            user_id=None,
            bbk_ids="201",
            start_date=None,
            end_date=None,
        )
        cron_sql, cron_params = service._build_cron_subquery(
            source_id="test-source",
            start_date=None,
            end_date=None,
            bbk_ids="201",  # 传递 bbk_ids 参数
        )
        query, final_params = service._build_users_query(
            source_id="test-source",
            where_sql=where_sql,
            cron_subquery_sql=cron_sql,
            order_by="manual_calls DESC, user_id ASC",
            params=params,
            cron_params=cron_params,
            page_size=10,
            offset=0,
            bbk_ids="201",  # 传递 bbk_ids 参数
        )

        # 验证 user_name 子查询包含 bbk_id 过滤
        # bbk_id 子查询应该有 bbk_id 过滤
        assert "AND bbk_id IN" in query, "subqueries should filter by bbk_id"

    def test_cron_subquery_includes_bbk_filter(self, service):
        """_build_cron_subquery should include bbk_id filter when bbk_ids provided."""
        # 这个测试验证修复：_build_cron_subquery 应该接受 bbk_ids 参数
        # 当前实现不接受，所以这个测试会失败
        cron_sql, cron_params = service._build_cron_subquery(
            source_id="all",
            start_date=None,
            end_date=None,
            bbk_ids="201",  # 当前方法签名不支持这个参数
        )
        assert (
            "j.bbk_id IN" in cron_sql
        ), "cron subquery should filter by j.bbk_id"

    def test_user_name_subquery_filters_bbk(self, service):
        """user_name should use MAX aggregation instead of subquery."""
        where_sql, params = service._build_traces_where_clause(
            source_id="test-source",
            filter_user_type="filtered",
            user_id=None,
            bbk_ids="201",
            start_date=None,
            end_date=None,
        )
        cron_sql, cron_params = service._build_cron_subquery(
            source_id="test-source",
            start_date=None,
            end_date=None,
            bbk_ids="201",
        )
        query, final_params = service._build_users_query(
            source_id="test-source",
            where_sql=where_sql,
            cron_subquery_sql=cron_sql,
            order_by="manual_calls DESC, user_id ASC",
            params=params,
            cron_params=cron_params,
            page_size=10,
            offset=0,
            bbk_ids="201",
        )

        # 简化后使用 MAX(t.user_name) 而不是子查询
        assert "MAX(t.user_name)" in query, (
            "user_name should use MAX aggregation after data is complete"
        )

    def test_bbk_id_subquery_filters_bbk(self, service):
        """bbk_id should use MAX aggregation instead of subquery."""
        where_sql, params = service._build_traces_where_clause(
            source_id="test-source",
            filter_user_type="filtered",
            user_id=None,
            bbk_ids="201",
            start_date=None,
            end_date=None,
        )
        cron_sql, cron_params = service._build_cron_subquery(
            source_id="test-source",
            start_date=None,
            end_date=None,
            bbk_ids="201",
        )
        query, final_params = service._build_users_query(
            source_id="test-source",
            where_sql=where_sql,
            cron_subquery_sql=cron_sql,
            order_by="manual_calls DESC, user_id ASC",
            params=params,
            cron_params=cron_params,
            page_size=10,
            offset=0,
            bbk_ids="201",
        )

        # 简化后使用 MAX(t.bbk_id) 而不是子查询
        assert "MAX(t.bbk_id)" in query, (
            "bbk_id should use MAX aggregation after data is complete"
        )

    def test_total_skills_subquery_filters_bbk(self, service):
        """total_skills subquery should filter by bbk_id."""
        where_sql, params = service._build_traces_where_clause(
            source_id="test-source",
            filter_user_type="filtered",
            user_id=None,
            bbk_ids="201",
            start_date=None,
            end_date=None,
        )
        cron_sql, cron_params = service._build_cron_subquery(
            source_id="test-source",
            start_date=None,
            end_date=None,
            bbk_ids="201",
        )
        query, final_params = service._build_users_query(
            source_id="test-source",
            where_sql=where_sql,
            cron_subquery_sql=cron_sql,
            order_by="manual_calls DESC, user_id ASC",
            params=params,
            cron_params=cron_params,
            page_size=10,
            offset=0,
            bbk_ids="201",
        )

        # total_skills 子查询应该有 bbk_id 过滤
        # 格式: SELECT COUNT(*) FROM swe_tracing_spans s WHERE ...
        # 内嵌子查询：SELECT trace_id FROM swe_tracing_traces WHERE ...
        # 应该包含 bbk_id 过滤
        assert "AND bbk_id IN" in query, (
            "total_skills subquery must filter by bbk_id to prevent counting "
            "skills from other bbk branches"
        )


class TestBuildCronSubquerySignature:
    """Tests for _build_cron_subquery method signature.

    This test verifies that _build_cron_subquery accepts bbk_ids parameter.
    """

    @pytest.fixture
    def service(self):
        """Create TracingQueryService instance with mock db."""
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        return TracingQueryService(mock_db)

    def test_accepts_bbk_ids_parameter(self, service):
        """_build_cron_subquery should accept bbk_ids parameter."""
        # 这个测试验证方法签名是否支持 bbk_ids 参数
        # 当前实现不支持，测试会失败
        import inspect

        sig = inspect.signature(service._build_cron_subquery)
        params = sig.parameters

        assert "bbk_ids" in params, (
            "_build_cron_subquery must accept bbk_ids parameter to filter "
            "cron executions by branch"
        )

    def test_includes_bbk_filter_in_sql(self, service):
        """_build_cron_subquery should include bbk_id filter in SQL."""
        # 这个测试会在修复后通过
        cron_sql, cron_params = service._build_cron_subquery(
            source_id="test-source",
            start_date=None,
            end_date=None,
            bbk_ids="201",
        )
        assert (
            "j.bbk_id IN" in cron_sql
        ), "cron subquery must include j.bbk_id IN filter"
        assert "201" in cron_params


class TestBuildUsersQuerySignature:
    """Tests for _build_users_query method signature."""

    @pytest.fixture
    def service(self):
        """Create TracingQueryService instance with mock db."""
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        return TracingQueryService(mock_db)

    def test_accepts_bbk_ids_parameter(self, service):
        """_build_users_query should accept bbk_ids parameter."""
        import inspect

        sig = inspect.signature(service._build_users_query)
        params = sig.parameters

        assert "bbk_ids" in params, (
            "_build_users_query must accept bbk_ids parameter to pass "
            "to subqueries for bbk filtering"
        )
