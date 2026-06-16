# -*- coding: utf-8 -*-
"""租户 Provider API 端点的单元测试。"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

import swe.app.routers.providers as providers_router
from swe.app.routers.providers import _distribute_providers_to_tenant
from swe.config.context import (
    encode_scope_id,
    resolve_runtime_tenant_id,
    resolve_storage_tenant_id,
)
from swe.app.routers.providers import tenant_providers_router
from swe.providers.models import ModelSlotConfig
from swe.providers.provider import ProviderInfo


@pytest.fixture
def sample_provider_info():
    """创建用于 deprecated /providers 响应的 ProviderManager 数据。"""
    return ProviderInfo(
        id="test-openai",
        name="Test OpenAI",
        base_url="https://api.example.test/v1",
        models=[],
    )


@pytest.fixture
def client():
    """创建只挂载 deprecated tenant providers router 的测试客户端。"""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(tenant_providers_router)
    return TestClient(app)


class TestGetTenantProviders:
    """验证 deprecated GET /providers 端点的 ProviderManager 视图。"""

    def test_get_tenant_providers_success(self, client, sample_provider_info):
        """成功请求时应返回当前租户的 provider-backed 配置。"""
        active_model = ModelSlotConfig(
            provider_id="test-openai",
            model="gpt-4",
        )
        mock_manager = MagicMock()
        mock_manager.get_active_model.return_value = active_model
        mock_manager.list_provider_info = AsyncMock(
            return_value=[sample_provider_info],
        )

        with (
            patch(
                "swe.app.routers.providers.get_current_effective_tenant_id",
                return_value="test-tenant",
            ),
            patch("swe.app.routers.providers.ProviderManager") as manager_cls,
        ):
            manager_cls.get_instance.return_value = mock_manager

            response = client.get("/providers")

        assert response.status_code == 200
        data = response.json()

        assert data["tenant_id"] == "test-tenant"
        assert len(data["providers"]) == 1
        assert data["providers"][0]["id"] == "test-openai"
        assert data["active_model"]["provider_id"] == "test-openai"
        assert data["active_model"]["model"] == "gpt-4"
        assert data["deprecated"] is True
        assert "/models" in data["migration_note"]
        manager_cls.ensure_tenant_provider_storage.assert_called_once_with(
            "test-tenant",
        )
        manager_cls.get_instance.assert_called_once_with("test-tenant")
        mock_manager.list_provider_info.assert_awaited_once_with()

    def test_get_tenant_providers_missing_tenant_id(self, client):
        """上下文缺少租户时应返回明确的 400 错误。"""
        with patch(
            "swe.app.routers.providers.get_current_effective_tenant_id",
            return_value=None,
        ):
            response = client.get("/providers")

            assert response.status_code == 400
            assert "Tenant ID not set" in response.json()["detail"]

    def test_get_tenant_providers_allows_empty_provider_state(self, client):
        """初始化后的空 provider 状态仍应按当前契约返回 200。"""
        mock_manager = MagicMock()
        mock_manager.get_active_model.return_value = None
        mock_manager.list_provider_info = AsyncMock(return_value=[])

        with (
            patch(
                "swe.app.routers.providers.get_current_effective_tenant_id",
                return_value="empty-tenant",
            ),
            patch("swe.app.routers.providers.ProviderManager") as manager_cls,
        ):
            manager_cls.get_instance.return_value = mock_manager

            response = client.get("/providers")

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == "empty-tenant"
        assert data["providers"] == []
        assert data["active_model"] is None
        assert data["deprecated"] is True

    def test_get_tenant_providers_different_tenant(
        self,
        client,
        sample_provider_info,
    ):
        """不同租户应通过各自的 ProviderManager 实例读取配置。"""
        tenant1_manager = MagicMock()
        tenant1_manager.get_active_model.return_value = ModelSlotConfig(
            provider_id="test-openai",
            model="gpt-4",
        )
        tenant1_manager.list_provider_info = AsyncMock(
            return_value=[sample_provider_info],
        )

        tenant2_provider = ProviderInfo(
            id="tenant2-anthropic",
            name="Tenant 2 Anthropic",
            base_url="https://api.anthropic.example.test",
            models=[],
        )
        tenant2_manager = MagicMock()
        tenant2_manager.get_active_model.return_value = ModelSlotConfig(
            provider_id="tenant2-anthropic",
            model="claude-3",
        )
        tenant2_manager.list_provider_info = AsyncMock(
            return_value=[tenant2_provider],
        )

        with (
            patch(
                "swe.app.routers.providers.get_current_effective_tenant_id",
            ) as tenant_id,
            patch(
                "swe.app.routers.providers.ProviderManager",
            ) as manager_cls,
        ):
            manager_cls.get_instance.side_effect = [
                tenant1_manager,
                tenant2_manager,
            ]

            tenant_id.return_value = "tenant1"
            try:
                response1 = client.get("/providers")
                data1 = response1.json()

                assert data1["tenant_id"] == "tenant1"
                assert data1["providers"][0]["id"] == "test-openai"
                assert data1["active_model"]["model"] == "gpt-4"

                tenant_id.return_value = "tenant2"
                response2 = client.get("/providers")
                data2 = response2.json()

                assert data2["tenant_id"] == "tenant2"
                assert data2["providers"][0]["id"] == "tenant2-anthropic"
                assert data2["active_model"]["model"] == "claude-3"

                assert data1 != data2
            finally:
                manager_cls.get_instance.side_effect = None

        manager_cls.ensure_tenant_provider_storage.assert_any_call("tenant1")
        manager_cls.ensure_tenant_provider_storage.assert_any_call("tenant2")
        assert manager_cls.get_instance.call_count == 2


def test_distribute_providers_writes_target_source_scope(
    monkeypatch,
    tmp_path,
) -> None:
    """全量分发应写入目标 tenant + 当前 source 的 secret 命名空间。"""

    class FakeTenantInitializer:
        def __init__(self, base_working_dir, tenant_id, source_id=None):
            self.effective_tenant_id = resolve_runtime_tenant_id(
                tenant_id,
                source_id,
            )

        def has_seeded_bootstrap(self):
            return True

        def ensure_seeded_bootstrap(self):
            raise AssertionError("不应在已初始化租户上触发 bootstrap")

    secret_dir = tmp_path / ".swe.secret"
    source_providers_dir = tmp_path / "source" / "providers"
    source_providers_dir.mkdir(parents=True)
    (source_providers_dir / "active_model.json").write_text(
        '{"provider_id":"openai","model":"gpt-5"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        providers_router,
        "get_tenant_storage_providers_dir",
        lambda tenant_id: secret_dir / tenant_id / "providers",
    )
    monkeypatch.setattr(
        providers_router,
        "TenantInitializer",
        FakeTenantInitializer,
    )

    result = _distribute_providers_to_tenant(
        source_providers_dir=source_providers_dir,
        target_tenant_id="tenant-b",
        source_working_dir=tmp_path / ".swe" / "source-scope",
        source_id="source-a",
    )

    target_scope_id = encode_scope_id("tenant-b", "source-a")
    assert result.success is True
    assert (
        secret_dir / target_scope_id / "providers" / "active_model.json"
    ).exists()
    assert not (secret_dir / "tenant-b" / "providers").exists()


def test_distribute_providers_writes_default_target_to_source_template(
    monkeypatch,
    tmp_path,
) -> None:
    """分发到 default 时应写入 default_{source} 的 secret 命名空间。"""

    class FakeTenantInitializer:
        def __init__(self, base_working_dir, tenant_id, source_id=None):
            del base_working_dir
            self.effective_tenant_id = resolve_storage_tenant_id(
                tenant_id,
                source_id,
            )

        def has_seeded_bootstrap(self):
            return True

        def ensure_seeded_bootstrap(self):
            raise AssertionError("不应在已初始化租户上触发 bootstrap")

    secret_dir = tmp_path / ".swe.secret"
    source_providers_dir = tmp_path / "source" / "providers"
    source_providers_dir.mkdir(parents=True)
    (source_providers_dir / "active_model.json").write_text(
        '{"provider_id":"openai","model":"gpt-5"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        providers_router,
        "get_tenant_storage_providers_dir",
        lambda tenant_id: secret_dir / tenant_id / "providers",
    )
    monkeypatch.setattr(
        providers_router,
        "TenantInitializer",
        FakeTenantInitializer,
    )

    result = _distribute_providers_to_tenant(
        source_providers_dir=source_providers_dir,
        target_tenant_id="default",
        source_working_dir=tmp_path / ".swe" / "default_source-a",
        source_id="source-a",
    )

    assert result.success is True
    assert (
        secret_dir / "default_source-a" / "providers" / "active_model.json"
    ).exists()
