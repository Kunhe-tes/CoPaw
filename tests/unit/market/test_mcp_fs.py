# -*- coding: utf-8 -*-
"""MCP 文件系统操作测试。"""

import pytest
from pathlib import Path
from market.marketplace.fs import (
    get_mcp_dir,
    get_mcp_config_path,
    _mask_env_value,
    get_user_skills_dir,
)


def test_get_mcp_dir():
    """获取 MCP 目录路径。"""
    marketplace_root = Path("/tmp/.swe.marketplace")
    source_id = "source-123"
    item_id = "item-uuid"

    mcp_dir = get_mcp_dir(marketplace_root, source_id, item_id)
    expected = marketplace_root / source_id / "mcp" / item_id
    assert mcp_dir == expected


def test_get_mcp_config_path():
    """获取 MCP 配置文件路径。"""
    marketplace_root = Path("/tmp/.swe.marketplace")
    source_id = "source-123"
    item_id = "item-uuid"

    config_path = get_mcp_config_path(marketplace_root, source_id, item_id)
    expected = marketplace_root / source_id / "mcp" / item_id / "mcp.json"
    assert config_path == expected


def test_get_user_skills_dir_uses_default_source_template():
    """default 用户技能目录应直达 default_{source}。"""
    swe_root = Path("/tmp/.swe")

    skills_dir = get_user_skills_dir(
        swe_root,
        "default",
        "default",
        "CMSJY",
    )

    assert skills_dir == (
        swe_root / "default_CMSJY" / "workspaces" / "default" / "skills"
    )


def test_mask_env_value_short():
    """短值完全遮盖。"""
    assert _mask_env_value("short") == "*****"
    assert _mask_env_value("12345678") == "********"


def test_mask_env_value_long():
    """长值显示前2+后4，中间遮盖。"""
    # "secret-key-12345" (17 chars) -> se**********2345
    assert _mask_env_value("secret-key-12345") == "se**********2345"
    # "sk-proj-1234567890" (17 chars, has dash at pos 2) -> sk-***********7890
    assert _mask_env_value("sk-proj-1234567890") == "sk-***********7890"


def test_mask_env_value_empty():
    """空值返回空。"""
    assert _mask_env_value("") == ""
    assert _mask_env_value(None) is None


class TestMCPConfigIO:
    """MCP 配置读写测试（需要临时目录）。"""

    def test_save_and_load_mcp_config(self, tmp_path):
        """保存和加载 MCP 配置。"""
        from market.marketplace.fs import save_mcp_config, load_mcp_config

        marketplace_root = tmp_path / ".swe.marketplace"
        source_id = "test-source"
        item_id = "test-item"

        config = {
            "client_key": "weather",
            "config": {
                "name": "Weather Tool",
                "command": "npx",
                "args": ["-y", "weather-mcp"],
            },
        }

        save_mcp_config(marketplace_root, source_id, item_id, config)

        loaded = load_mcp_config(marketplace_root, source_id, item_id)
        assert loaded is not None
        assert loaded["client_key"] == "weather"

    def test_load_mcp_config_not_found(self, tmp_path):
        """加载不存在的配置返回 None。"""
        from market.marketplace.fs import load_mcp_config

        marketplace_root = tmp_path / ".swe.marketplace"
        loaded = load_mcp_config(
            marketplace_root,
            "nonexistent",
            "nonexistent",
        )
        assert loaded is None
