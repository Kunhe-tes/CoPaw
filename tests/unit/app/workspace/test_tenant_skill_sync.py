# -*- coding: utf-8 -*-
"""src/swe 侧 HTTP 客户端 sync_skills_to_db 单元测试."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _configure_market(monkeypatch, url: str, token: str = ""):
    """覆盖模块级 market 配置常量（EnvVarLoader 在导入期已求值）。"""
    from src.swe.app.workspace import tenant_skill_sync

    monkeypatch.setattr(tenant_skill_sync, "MARKET_INTERNAL_URL", url)
    monkeypatch.setattr(tenant_skill_sync, "MARKET_INTERNAL_TOKEN", token)
    return tenant_skill_sync


def _fake_async_client(fake_client):
    """构造 httpx.AsyncClient 的异步上下文管理器替身。"""
    fake = MagicMock()
    fake.return_value.__aenter__ = AsyncMock(return_value=fake_client)
    fake.return_value.__aexit__ = AsyncMock(return_value=None)
    return fake


@pytest.mark.asyncio
async def test_sync_skills_to_db_calls_market_endpoint(monkeypatch):
    """应调用 market 内部端点，URL 含 tenant_id。"""
    module = _configure_market(monkeypatch, "http://market.test:8080")

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"tenant_id": "alice", "synced": 5}
    fake_response.text = ""

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=fake_response)

    with patch(
        "src.swe.app.workspace.tenant_skill_sync.httpx.AsyncClient",
        _fake_async_client(fake_client),
    ):
        await module.sync_skills_to_db("alice")

    fake_client.post.assert_called_once()
    url = fake_client.post.call_args.args[0]
    assert url == (
        "http://market.test:8080/market/internal/tenants/alice/sync-skills"
    )


@pytest.mark.asyncio
async def test_sync_skills_to_db_sends_token_header(monkeypatch):
    """配置了 MARKET_INTERNAL_TOKEN 时，应附带 X-Internal-Token header。"""
    module = _configure_market(
        monkeypatch,
        "http://market:8080",
        token="secret123",
    )

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"synced": 1}
    fake_response.text = ""

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=fake_response)

    with patch(
        "src.swe.app.workspace.tenant_skill_sync.httpx.AsyncClient",
        _fake_async_client(fake_client),
    ):
        await module.sync_skills_to_db("alice")

    headers = fake_client.post.call_args.kwargs["headers"]
    assert headers.get("X-Internal-Token") == "secret123"


@pytest.mark.asyncio
async def test_sync_skills_to_db_swallows_connection_error(monkeypatch):
    """market 不可达时必须不抛异常，仅吞掉异常。"""
    module = _configure_market(monkeypatch, "http://market-down:8080")

    fake_client = MagicMock()
    fake_client.post = AsyncMock(side_effect=ConnectionError("market down"))

    with patch(
        "src.swe.app.workspace.tenant_skill_sync.httpx.AsyncClient",
        _fake_async_client(fake_client),
    ):
        # 不应抛异常
        await module.sync_skills_to_db("alice")


@pytest.mark.asyncio
async def test_sync_skills_to_db_swallows_timeout(monkeypatch):
    """超时必须不抛异常。"""
    import httpx

    module = _configure_market(monkeypatch, "http://market:8080")

    fake_client = MagicMock()
    fake_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch(
        "src.swe.app.workspace.tenant_skill_sync.httpx.AsyncClient",
        _fake_async_client(fake_client),
    ):
        await module.sync_skills_to_db("alice")


@pytest.mark.asyncio
async def test_sync_skills_to_db_logs_warning_on_500(monkeypatch, caplog):
    """market 返回 500 时记 warning，不抛异常。"""
    import logging

    module = _configure_market(monkeypatch, "http://market:8080")

    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_response.json.return_value = {}
    fake_response.text = "internal error"

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=fake_response)

    with patch(
        "src.swe.app.workspace.tenant_skill_sync.httpx.AsyncClient",
        _fake_async_client(fake_client),
    ):
        with caplog.at_level(logging.WARNING):
            await module.sync_skills_to_db("alice")

    warning_records = [r for r in caplog.records if "swe_skills" in r.message]
    assert len(warning_records) >= 1
