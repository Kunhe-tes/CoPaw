# -*- coding: utf-8 -*-
"""MCP 版本管理服务单元测试."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from market.marketplace.mcp_version_service import MCPVersionService


def _write_mcp_json(item_dir: Path, content: dict) -> Path:
    item_dir.mkdir(parents=True, exist_ok=True)
    p = item_dir / "mcp.json"
    p.write_text(
        json.dumps(content, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return p


def test_create_initial_snapshot(tmp_path):
    svc = MCPVersionService(tmp_path / "market")
    item_dir = tmp_path / "market" / "src1" / "mcp" / "item1"
    _write_mcp_json(
        item_dir,
        {"name": "demo", "transport": "stdio", "command": "/bin/true"},
    )
    v = svc.create_version_snapshot(
        source_id="src1",
        item_id="item1",
        mcp_dir=item_dir,
        version_id="1.0.0",
        creator="admin",
        creator_name="admin",
        source_user_id="alice",
        source_user_name="Alice",
        source_user_version="1.0.0",
    )
    assert v.version_id == "1.0.0"
    assert v.is_initial is True
    assert v.is_current is True
    assert v.source_user_id == "alice"


def test_create_two_snapshots_only_latest_is_current(tmp_path):
    svc = MCPVersionService(tmp_path / "market")
    item_dir = tmp_path / "market" / "src1" / "mcp" / "item1"
    _write_mcp_json(
        item_dir,
        {"name": "demo", "transport": "stdio", "command": "/a"},
    )
    svc.create_version_snapshot(
        source_id="src1",
        item_id="item1",
        mcp_dir=item_dir,
        version_id="1.0.0",
        creator="admin",
        creator_name="admin",
    )
    _write_mcp_json(
        item_dir,
        {"name": "demo", "transport": "stdio", "command": "/b"},
    )
    svc.create_version_snapshot(
        source_id="src1",
        item_id="item1",
        mcp_dir=item_dir,
        version_id="1.0.1",
        creator="admin",
        creator_name="admin",
    )
    listed = svc.list_versions("src1", "item1")
    versions = listed["versions"]
    currents = [v for v in versions if v["is_current"]]
    assert len(currents) == 1
    assert currents[0]["version_id"] == "1.0.1"


def test_signature_canonical_json_only(tmp_path):
    """同语义不同 key 顺序的 mcp.json 应产生相同 signature。"""
    svc = MCPVersionService(tmp_path / "market")
    item_dir = tmp_path / "market" / "src1" / "mcp" / "item1"

    p = item_dir / "mcp.json"
    item_dir.mkdir(parents=True, exist_ok=True)
    p.write_text('{"a": 1, "b": 2}', encoding="utf-8")
    sig1 = svc._calculate_signature(item_dir)

    p.write_text('{"b": 2, "a": 1}', encoding="utf-8")
    sig2 = svc._calculate_signature(item_dir)

    assert sig1 == sig2


def test_same_version_same_content_no_op(tmp_path):
    """R7：MCP 同样适用——同 version_id 同 signature 不翻 is_current。"""
    svc = MCPVersionService(tmp_path / "market")
    item_dir = tmp_path / "market" / "src1" / "mcp" / "item1"
    _write_mcp_json(
        item_dir,
        {"name": "demo", "transport": "stdio", "command": "/a"},
    )
    svc.create_version_snapshot(
        source_id="src1",
        item_id="item1",
        mcp_dir=item_dir,
        version_id="1.0.0",
        creator="admin",
        creator_name="admin",
    )
    _write_mcp_json(
        item_dir,
        {"name": "demo", "transport": "stdio", "command": "/b"},
    )
    svc.create_version_snapshot(
        source_id="src1",
        item_id="item1",
        mcp_dir=item_dir,
        version_id="1.0.1",
        creator="admin",
        creator_name="admin",
    )
    # 当前 current=1.0.1。再用 1.0.0 同内容做 snapshot
    _write_mcp_json(
        item_dir,
        {"name": "demo", "transport": "stdio", "command": "/a"},
    )
    svc.create_version_snapshot(
        source_id="src1",
        item_id="item1",
        mcp_dir=item_dir,
        version_id="1.0.0",
        creator="admin",
        creator_name="admin",
    )
    listed = svc.list_versions("src1", "item1")
    currents = [v for v in listed["versions"] if v["is_current"]]
    assert [c["version_id"] for c in currents] == ["1.0.1"]


def test_switch_version_copies_mcp_json_back(tmp_path):
    svc = MCPVersionService(tmp_path / "market")
    item_dir = tmp_path / "market" / "src1" / "mcp" / "item1"
    _write_mcp_json(item_dir, {"command": "/v1"})
    svc.create_version_snapshot(
        source_id="src1",
        item_id="item1",
        mcp_dir=item_dir,
        version_id="1.0.0",
        creator="u",
        creator_name="u",
    )
    _write_mcp_json(item_dir, {"command": "/v2"})
    svc.create_version_snapshot(
        source_id="src1",
        item_id="item1",
        mcp_dir=item_dir,
        version_id="1.0.1",
        creator="u",
        creator_name="u",
    )

    result = svc.switch_version("src1", "item1", "1.0.0", item_dir)
    assert result["success"] is True
    assert result["current_version"] == "1.0.0"
    assert result["previous_version"] == "1.0.1"
    data = json.loads((item_dir / "mcp.json").read_text(encoding="utf-8"))
    assert data["command"] == "/v1"


def test_delete_current_version_fails(tmp_path):
    svc = MCPVersionService(tmp_path / "market")
    item_dir = tmp_path / "market" / "src1" / "mcp" / "item1"
    _write_mcp_json(item_dir, {"command": "/v1"})
    svc.create_version_snapshot(
        source_id="src1",
        item_id="item1",
        mcp_dir=item_dir,
        version_id="1.0.0",
        creator="u",
        creator_name="u",
    )
    result = svc.delete_version("src1", "item1", "1.0.0")
    assert result["success"] is False
