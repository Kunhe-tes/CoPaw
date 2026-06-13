# -*- coding: utf-8 -*-
"""身份补齐 helper 测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from swe.app.identity_resolver import resolve_user_identity


@pytest.mark.asyncio
async def test_resolve_user_identity_keeps_existing_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已有身份信息时不应触发额外查询。"""
    fetch_mock = AsyncMock(return_value=("远端姓名", "9999"))
    monkeypatch.setattr(
        "swe.app.identity_resolver._fetch_user_info_for_tenant",
        fetch_mock,
    )

    resolved = await resolve_user_identity(
        tenant_id="tenant-a",
        source_id="source-a",
        user_name="本地姓名",
        bbk_id="3301",
    )

    assert resolved.user_name == "本地姓名"
    assert resolved.bbk_id == "3301"
    fetch_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_user_identity_uses_store_before_remote_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """本地表已有身份信息时不应调用远端接口。"""

    class FakeStore:
        async def get_tenant_source_info(self, tenant_id: str, source_id: str):
            assert tenant_id == "tenant-a"
            assert source_id == "source-a"
            return {"tenant_name": "库内姓名", "bbk_id": "3301"}

    store = FakeStore()

    def fake_get_store() -> FakeStore:
        return store

    fetch_mock = AsyncMock(return_value=("远端姓名", "9999"))
    monkeypatch.setattr(
        "swe.app.identity_resolver.get_tenant_init_source_store",
        fake_get_store,
    )
    monkeypatch.setattr(
        "swe.app.identity_resolver._fetch_user_info_for_tenant",
        fetch_mock,
    )

    resolved = await resolve_user_identity(
        tenant_id="tenant-a",
        source_id="source-a",
        user_name=None,
        bbk_id=None,
    )

    assert resolved.user_name == "库内姓名"
    assert resolved.bbk_id == "3301"
    fetch_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_user_identity_updates_store_after_remote_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """远端补齐成功后应回写 store，方便后续链路复用。"""

    class FakeStore:
        get_tenant_source_info = AsyncMock(return_value=None)
        update_tenant_info = AsyncMock(return_value=True)

    store = FakeStore()
    monkeypatch.setattr(
        "swe.app.identity_resolver.get_tenant_init_source_store",
        lambda: store,
    )
    monkeypatch.setattr(
        "swe.app.identity_resolver._fetch_user_info_for_tenant",
        AsyncMock(return_value=("远端姓名", "3301")),
    )

    resolved = await resolve_user_identity(
        tenant_id="tenant-a",
        source_id="source-a",
        user_name=None,
        bbk_id=None,
    )

    assert resolved.user_name == "远端姓名"
    assert resolved.bbk_id == "3301"
    store.update_tenant_info.assert_awaited_once_with(
        tenant_id="tenant-a",
        source_id="source-a",
        tenant_name="远端姓名",
        bbk_id="3301",
    )


@pytest.mark.asyncio
async def test_resolve_user_identity_skips_remote_lookup_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """主链路禁用远端查询时不应等待外部接口。"""
    fetch_mock = AsyncMock(return_value=("远端姓名", "3301"))
    monkeypatch.setattr(
        "swe.app.identity_resolver._fetch_user_info_for_tenant",
        fetch_mock,
    )

    resolved = await resolve_user_identity(
        tenant_id="tenant-a",
        source_id="source-a",
        user_name=None,
        bbk_id=None,
        allow_remote_lookup=False,
    )

    assert resolved.user_name is None
    assert resolved.bbk_id is None
    fetch_mock.assert_not_awaited()
