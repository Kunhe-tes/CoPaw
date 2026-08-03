# -*- coding: utf-8 -*-
"""src/swe 侧 HTTP 客户端 sync_skills_to_db 单元测试."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_sync_skills_to_db_calls_market_endpoint(monkeypatch):
    """应调用 market 内部端点，URL 含 tenant_id。"""
    monkeypatch.setenv("SWE_MARKET_INTERNAL_URL", "http://market.test:8080")
    monkeypatch.delenv("SWE_MARKET_INTERNAL_TOKEN", raising=False)

    from src.swe.app.workspace.tenant_skill_sync import sync_skills_to_db

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"tenant_id": "alice", "synced": 5}
    fake_response.text = ""

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=fake_response)

    fake_async_client = MagicMock()
    fake_async_client.return_value.__aenter__ = AsyncMock(return_value=fake_client)
    fake_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "src.swe.app.workspace.tenant_skill_sync.httpx.AsyncClient",
        fake_async_client,
    ):
        await sync_skills_to_db("alice")

    fake_client.post.assert_called_once()
    call_args = fake_client.post.call_args
    url = call_args.args[0]
    assert url == "http://market.test:8080/market/internal/tenants/alice/sync-skills"


@pytest.mark.asyncio
async def test_sync_skills_to_db_sends_token_header(monkeypatch):
    """配置了 SWE_MARKET_INTERNAL_TOKEN 时，应附带 X-Internal-Token header。"""
    monkeypatch.setenv("SWE_MARKET_INTERNAL_URL", "http://market:8080")
    monkeypatch.setenv("SWE_MARKET_INTERNAL_TOKEN", "secret123")

    from src.swe.app.workspace.tenant_skill_sync import sync_skills_to_db

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"synced": 1}
    fake_response.text = ""

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=fake_response)

    fake_async_client = MagicMock()
    fake_async_client.return_value.__aenter__ = AsyncMock(return_value=fake_client)
    fake_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "src.swe.app.workspace.tenant_skill_sync.httpx.AsyncClient",
        fake_async_client,
    ):
        await sync_skills_to_db("alice")

    headers = fake_client.post.call_args.kwargs["headers"]
    assert headers.get("X-Internal-Token") == "secret123"


@pytest.mark.asyncio
async def test_sync_skills_to_db_swallows_connection_error(monkeypatch):
    """market 不可达时必须不抛异常，仅吞掉异常。"""
    monkeypatch.setenv("SWE_MARKET_INTERNAL_URL", "http://market-down:8080")
    monkeypatch.delenv("SWE_MARKET_INTERNAL_TOKEN", raising=False)

    from src.swe.app.workspace.tenant_skill_sync import sync_skills_to_db

    fake_client = MagicMock()
    fake_client.post = AsyncMock(side_effect=ConnectionError("market down"))

    fake_async_client = MagicMock()
    fake_async_client.return_value.__aenter__ = AsyncMock(return_value=fake_client)
    fake_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "src.swe.app.workspace.tenant_skill_sync.httpx.AsyncClient",
        fake_async_client,
    ):
        # 不应抛异常
        await sync_skills_to_db("alice")


@pytest.mark.asyncio
async def test_sync_skills_to_db_swallows_timeout(monkeypatch):
    """超时必须不抛异常。"""
    monkeypatch.setenv("SWE_MARKET_INTERNAL_URL", "http://market:8080")
    monkeypatch.delenv("SWE_MARKET_INTERNAL_TOKEN", raising=False)

    import httpx

    from src.swe.app.workspace.tenant_skill_sync import sync_skills_to_db

    fake_client = MagicMock()
    fake_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    fake_async_client = MagicMock()
    fake_async_client.return_value.__aenter__ = AsyncMock(return_value=fake_client)
    fake_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "src.swe.app.workspace.tenant_skill_sync.httpx.AsyncClient",
        fake_async_client,
    ):
        await sync_skills_to_db("alice")


@pytest.mark.asyncio
async def test_sync_skills_to_db_logs_warning_on_500(monkeypatch, caplog):
    """market 返回 500 时记 warning，不抛异常。"""
    monkeypatch.setenv("SWE_MARKET_INTERNAL_URL", "http://market:8080")
    monkeypatch.delenv("SWE_MARKET_INTERNAL_TOKEN", raising=False)

    import logging

    from src.swe.app.workspace.tenant_skill_sync import sync_skills_to_db

    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_response.json.return_value = {}
    fake_response.text = "internal error"

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=fake_response)

    fake_async_client = MagicMock()
    fake_async_client.return_value.__aenter__ = AsyncMock(return_value=fake_client)
    fake_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "src.swe.app.workspace.tenant_skill_sync.httpx.AsyncClient",
        fake_async_client,
    ):
        with caplog.at_level(logging.WARNING):
            await sync_skills_to_db("alice")

    warning_records = [r for r in caplog.records if "swe_skills" in r.message]
    assert len(warning_records) >= 1