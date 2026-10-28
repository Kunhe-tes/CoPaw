# -*- coding: utf-8 -*-
"""market 侧 MyMCP 路由测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from market.app.my_mcp_helpers import MyMCPRequestContext
from market.app.routers.my_mcp import router
from market.runtime.config_store import MCPClientConfig, MCPConfig


class FakeMarketplace:
    """提供给路由的最小 marketplace 假对象。"""

    def __init__(self) -> None:
        self.swe_root = "D:/fake/.swe"
        self.db = SimpleNamespace(is_connected=False)
        self.publish_mcp = AsyncMock()


@pytest.fixture
def request_context() -> MyMCPRequestContext:
    """构造固定的请求上下文。"""
    return MyMCPRequestContext(
        user_id="user-a",
        tenant_id="user-a",
        source_id="SRC_A",
        effective_tenant_id="user-a",
        agent_id="default",
    )


@pytest.fixture
def test_app() -> FastAPI:
    """创建挂载 MyMCP 路由的 FastAPI 应用。"""
    app = FastAPI()
    app.state.marketplace = FakeMarketplace()
    app.include_router(router)
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """普通用户客户端。"""
    return TestClient(test_app)


@pytest.fixture
def manager_client(test_app: FastAPI) -> TestClient:
    """带管理员请求头的客户端。"""
    return TestClient(test_app, headers={"X-Manager": "true"})


def _agent_config(
    clients: dict[str, MCPClientConfig] | None = None,
) -> SimpleNamespace:
    """构造带 MCP 配置的最小 agent config。"""
    return SimpleNamespace(
        mcp=MCPConfig(clients=clients or {}),
    )


class TestListMyMCP:
    """GET /market/my-mcp 列表测试。"""

    def test_list_empty(self, client: TestClient, request_context):
        """空配置应返回空列表。"""
        agent_config = SimpleNamespace(mcp=None)
        with patch(
            "market.app.routers.my_mcp.load_agent_config_for_request",
            return_value=(request_context, agent_config),
        ):
            response = client.get("/market/my-mcp")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_sorted_by_updated_at(
        self,
        client: TestClient,
        request_context,
    ):
        """列表应按更新时间降序排序。"""
        agent_config = _agent_config(
            {
                "older": MCPClientConfig(
                    name="Older Client",
                    command="npx",
                    created_at="2026-04-01T10:00:00Z",
                    updated_at="2026-04-01T10:00:00Z",
                ),
                "newest": MCPClientConfig(
                    name="Newest Client",
                    command="npx",
                    created_at="2026-04-03T10:00:00Z",
                    updated_at="2026-04-03T10:00:00Z",
                ),
            },
        )
        with patch(
            "market.app.routers.my_mcp.load_agent_config_for_request",
            return_value=(request_context, agent_config),
        ):
            response = client.get("/market/my-mcp")
        assert response.status_code == 200
        data = response.json()
        assert [item["client_key"] for item in data] == ["newest", "older"]


class TestGetMyMCPDetail:
    """GET /market/my-mcp/{client_key} 详情测试。"""

    def test_get_detail_masks_sensitive_values(
        self,
        client: TestClient,
        request_context,
    ):
        """详情响应应对 env 和 headers 做脱敏。"""
        agent_config = _agent_config(
            {
                "weather": MCPClientConfig(
                    name="Weather Tool",
                    description="天气查询",
                    command="npx",
                    args=["-y", "weather-mcp"],
                    env={"API_KEY": "test-key-12345678"},
                    headers={"X-Custom": "header-value"},
                    source="",
                    created_at="2026-04-29T10:00:00Z",
                    updated_at="2026-04-30T10:00:00Z",
                ),
            },
        )
        with patch(
            "market.app.routers.my_mcp.load_agent_config_for_request",
            return_value=(request_context, agent_config),
        ):
            response = client.get("/market/my-mcp/weather")
        assert response.status_code == 200
        data = response.json()
        assert data["client_key"] == "weather"
        assert data["env"]["API_KEY"] == "te***********5678"
        assert data["headers"]["X-Custom"] == "he******alue"


class TestCreateUpdateDeleteMyMCP:
    """MyMCP 基础增删改测试。"""

    def test_create_duplicate_key_returns_400(
        self,
        client: TestClient,
        request_context,
    ):
        """重复 client_key 应返回 400。"""
        agent_config = _agent_config(
            {"existing": MCPClientConfig(name="Existing", command="npx")},
        )
        with patch(
            "market.app.routers.my_mcp.load_agent_config_for_request",
            return_value=(request_context, agent_config),
        ):
            response = client.post(
                "/market/my-mcp",
                json={
                    "client_key": "existing",
                    "name": "Existing",
                    "transport": "stdio",
                    "command": "npx",
                },
            )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_update_distributed_mcp_blocks_sensitive_fields(
        self,
        client: TestClient,
        request_context,
    ):
        """市场分发项禁止修改敏感字段。"""
        agent_config = _agent_config(
            {
                "distributed": MCPClientConfig(
                    name="Distributed Tool",
                    command="npx",
                    args=["-y", "distributed-mcp"],
                    source="marketplace:item-uuid-123",
                    market_client_key="distributed-tool",
                    distributed_by="admin-user",
                ),
            },
        )
        with patch(
            "market.app.routers.my_mcp.load_agent_config_for_request",
            return_value=(request_context, agent_config),
        ):
            response = client.put(
                "/market/my-mcp/distributed",
                json={"command": "new-command"},
            )
        assert response.status_code == 403
        assert "Cannot modify" in response.json()["detail"]

    def test_toggle_updates_enabled_state(
        self,
        client: TestClient,
        request_context,
    ):
        """启停应切换 enabled 状态。"""
        agent_config = _agent_config(
            {
                "weather": MCPClientConfig(
                    name="Weather",
                    command="npx",
                    enabled=False,
                    created_at="2026-04-29T10:00:00Z",
                    updated_at="2026-04-29T10:00:00Z",
                ),
            },
        )
        with (
            patch(
                "market.app.routers.my_mcp.load_agent_config_for_request",
                return_value=(request_context, agent_config),
            ),
            patch(
                "market.app.routers.my_mcp.save_agent_config_for_request",
            ) as mock_save,
        ):
            response = client.patch("/market/my-mcp/weather/toggle")
        assert response.status_code == 200
        assert response.json()["enabled"] is True
        mock_save.assert_called_once()

    def test_delete_success(
        self,
        client: TestClient,
        request_context,
    ):
        """删除 MCP 应返回成功消息。"""
        agent_config = _agent_config(
            {"weather": MCPClientConfig(name="Weather", command="npx")},
        )
        with (
            patch(
                "market.app.routers.my_mcp.load_agent_config_for_request",
                return_value=(request_context, agent_config),
            ),
            patch(
                "market.app.routers.my_mcp.save_agent_config_for_request",
            ) as mock_save,
        ):
            response = client.delete("/market/my-mcp/weather")
        assert response.status_code == 200
        assert response.json()["message"] == "MCP client 'weather' deleted"
        mock_save.assert_called_once()


class TestPublishMyMCP:
    """MyMCP 发布到市场测试。"""

    def test_publish_requires_manager(
        self,
        client: TestClient,
        request_context,
    ):
        """非管理员不允许发布。"""
        agent_config = _agent_config(
            {"weather": MCPClientConfig(name="Weather", command="npx")},
        )
        with patch(
            "market.app.routers.my_mcp.load_agent_config_for_request",
            return_value=(request_context, agent_config),
        ):
            response = client.post(
                "/market/my-mcp/weather/publish",
                json={"bbk_ids": ["100"]},
            )
        assert response.status_code == 403

    def test_publish_single_success(
        self,
        manager_client: TestClient,
        test_app: FastAPI,
        request_context,
    ):
        """单个上架应返回 item_id。"""
        agent_config = _agent_config(
            {"weather": MCPClientConfig(name="Weather", command="npx")},
        )
        test_app.state.marketplace.publish_mcp.return_value = (
            SimpleNamespace(item_id="mcp-weather-123"), False,
        )
        with patch(
            "market.app.routers.my_mcp.load_agent_config_for_request",
            return_value=(request_context, agent_config),
        ):
            response = manager_client.post(
                "/market/my-mcp/weather/publish",
                json={"bbk_ids": ["100"]},
                headers={"X-User-Name": "%E5%BC%A0%E4%B8%89"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["client_key"] == "weather"
        assert data["item_id"] == "mcp-weather-123"
        assert data["success"] is True


class TestMyMCPConnection:
    """MyMCP 测试连接测试。"""

    def test_test_connection_success(
        self,
        client: TestClient,
        request_context,
    ):
        """测试连接成功时应透传工具列表。"""
        agent_config = _agent_config(
            {
                "weather": MCPClientConfig(
                    name="Weather",
                    command="npx",
                    args=["-y", "weather-mcp"],
                ),
            },
        )
        with (
            patch(
                "market.app.routers.my_mcp.load_agent_config_for_request",
                return_value=(request_context, agent_config),
            ),
            patch(
                "market.app.routers.my_mcp._test_mcp_connection",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "tools": [{"name": "get_weather"}],
                        "error": "",
                    },
                ),
            ),
        ):
            response = client.post("/market/my-mcp/weather/test")
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["tools"][0]["name"] == "get_weather"


class TestMyMCPWorkflow:
    """完整 CRUD 流程回归测试。"""

    def test_full_crud_workflow(self, client: TestClient, request_context):
        """验证创建、详情、更新、启停、删除的基本链路。"""
        agent_config = _agent_config({})

        with (
            patch(
                "market.app.routers.my_mcp.load_agent_config_for_request",
                return_value=(request_context, agent_config),
            ),
            patch("market.app.routers.my_mcp.save_agent_config_for_request"),
        ):
            create_response = client.post(
                "/market/my-mcp",
                json={
                    "client_key": "test-tool",
                    "name": "Test Tool",
                    "description": "A test MCP client",
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "test-mcp-server"],
                    "env": {"API_KEY": "secret-key-12345"},
                },
            )
        assert create_response.status_code == 201
        assert create_response.json()["client_key"] == "test-tool"

        with patch(
            "market.app.routers.my_mcp.load_agent_config_for_request",
            return_value=(request_context, agent_config),
        ):
            list_response = client.get("/market/my-mcp")
            detail_response = client.get("/market/my-mcp/test-tool")
        assert list_response.status_code == 200
        assert len(list_response.json()) == 1
        assert detail_response.status_code == 200
        assert detail_response.json()["name"] == "Test Tool"

        with (
            patch(
                "market.app.routers.my_mcp.load_agent_config_for_request",
                return_value=(request_context, agent_config),
            ),
            patch("market.app.routers.my_mcp.save_agent_config_for_request"),
        ):
            update_response = client.put(
                "/market/my-mcp/test-tool",
                json={
                    "name": "Updated Tool",
                    "description": "Updated description",
                },
            )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Updated Tool"

        with (
            patch(
                "market.app.routers.my_mcp.load_agent_config_for_request",
                return_value=(request_context, agent_config),
            ),
            patch("market.app.routers.my_mcp.save_agent_config_for_request"),
        ):
            toggle_response = client.patch("/market/my-mcp/test-tool/toggle")
        assert toggle_response.status_code == 200
        assert toggle_response.json()["enabled"] is False

        with (
            patch(
                "market.app.routers.my_mcp.load_agent_config_for_request",
                return_value=(request_context, agent_config),
            ),
            patch("market.app.routers.my_mcp.save_agent_config_for_request"),
        ):
            delete_response = client.delete("/market/my-mcp/test-tool")
        assert delete_response.status_code == 200

        with patch(
            "market.app.routers.my_mcp.load_agent_config_for_request",
            return_value=(request_context, agent_config),
        ):
            list_response2 = client.get("/market/my-mcp")
            detail_response2 = client.get("/market/my-mcp/test-tool")
        assert list_response2.status_code == 200
        assert list_response2.json() == []
        assert detail_response2.status_code == 404
