# -*- coding: utf-8 -*-
"""Tests for error list bbk filter SQL."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from monitor.app.services.tracing.query_service import TracingQueryService


@pytest.mark.asyncio
async def test_get_error_list_qualifies_bbk_filter_on_join_query():
    """报错列表主查询在联表场景下应显式限定 s.bbk_id。"""
    db = MagicMock()
    db.fetch_all = AsyncMock(return_value=[])
    db.fetch_one = AsyncMock(return_value={"total": 0})
    service = TracingQueryService(db)

    await service.get_error_list(
        source_id="source-a",
        start_date=datetime(2026, 7, 1),
        end_date=datetime(2026, 7, 9),
        bbk_ids="201,202",
        page=1,
        page_size=10,
    )

    query, _params = db.fetch_all.await_args.args

    assert "s.bbk_id IN (%s, %s)" in query
    assert " AND bbk_id IN (%s, %s)" not in query
