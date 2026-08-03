# -*- coding: utf-8 -*-
"""market 内部端点 /market/internal/tenants/{id}/sync-skills 单元测试."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app(tmp_path, internal_token: str = ""):
    """构造带路由的 FastAPI 应用，swe_root 指向 tmp_path。"""
    from market.app.routers.skills_market import router
    from market.database.connection import DatabaseConnection
    from market.marketplace.service import MarketplaceService

    mock_db = MagicMock(spec=DatabaseConnection)
    mock_db.is_connected = True
    mock_db.execute = AsyncMock(return_value=1)
    mock_db.fetch_one = AsyncMock(return_value=None)
    mock_db.fetch_all = AsyncMock(return_value=[])

    svc = MarketplaceService(
        db=mock_db,
        marketplace_root=tmp_path / "market",
        swe_root=tmp_path,
    )

    if internal_token:
        import os

        os.environ["MARKET_INTERNAL_TOKEN"] = internal_token

    app = FastAPI()
    app.state.marketplace = svc
    app.include_router(router, prefix="/api")
    return app


def test_internal_sync_skills_endpoint_returns_synced(tmp_path):
    """POST /api/market/internal/tenants/{tenant_id}/sync-skills 应返回 synced 数。"""
    import os

    os.environ.pop("MARKET_INTERNAL_TOKEN", None)

    tenant = tmp_path / "alice" / "workspaces" / "default" / "skills" / "demo"
    tenant.mkdir(parents=True)
    (tenant / "SKILL.md").write_text("# demo", encoding="utf-8")

    import json

    (tenant.parent / "skill.json").write_text(
        json.dumps({"skills": {"demo": {"source": "customized", "enabled": True}}}),
        encoding="utf-8",
    )

    app = _make_app(tmp_path)
    client = TestClient(app)

    with pytest.MonkeyPatch.context() as mp:
        from market.marketplace import skill_sync

        captured: dict = {}

        async def _capture(tenant_dir, **kwargs):
            captured["source_id"] = kwargs.get("source_id")
            captured["tenant_dir"] = tenant_dir
            return {
                "tenant_id": "alice",
                "total_workspaces": 1,
                "total_skills": 1,
                "synced": 1,
                "errors": [],
                "details": [],
            }

        mp.setattr(skill_sync, "process_tenant_skills", _capture)
        resp = client.post("/api/market/internal/tenants/alice/sync-skills")

    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == "alice"
    assert data["synced"] == 1
    # tenant_id 无 "." 时 source_id 应为 None，保持向后兼容
    assert captured["source_id"] is None


def test_internal_sync_skills_decodes_source_from_scope_id(tmp_path):
    """scope 编码的 tenant_id 应解出 source_id 传入 process_tenant_skills。"""
    import os

    os.environ.pop("MARKET_INTERNAL_TOKEN", None)

    # bootstrap_tenant_id 形如 encode_scope_id(tenant_id, source_id)：
    # 两个 base64 段以 "." 连接。模拟 src/swe 真实传过来的 scope 编码值。
    from market.runtime.context import encode_scope_id

    tenant_id = encode_scope_id("alice", "paasuat")
    tenant = tmp_path / tenant_id / "workspaces" / "default" / "skills" / "demo"
    tenant.mkdir(parents=True)
    (tenant / "SKILL.md").write_text("# demo", encoding="utf-8")

    import json

    (tenant.parent / "skill.json").write_text(
        json.dumps({"skills": {"demo": {"source": "customized", "enabled": True}}}),
        encoding="utf-8",
    )

    app = _make_app(tmp_path)
    client = TestClient(app)

    with pytest.MonkeyPatch.context() as mp:
        from market.marketplace import skill_sync

        captured: dict = {}

        async def _capture(tenant_dir, **kwargs):
            captured["source_id"] = kwargs.get("source_id")
            return {
                "tenant_id": tenant_id,
                "total_workspaces": 1,
                "total_skills": 1,
                "synced": 1,
                "errors": [],
                "details": [],
            }

        mp.setattr(skill_sync, "process_tenant_skills", _capture)
        resp = client.post(f"/api/market/internal/tenants/{tenant_id}/sync-skills")

    assert resp.status_code == 200
    # decode_scope_id 应还原出 source_id = "paasuat"
    assert captured["source_id"] == "paasuat"


def test_internal_sync_skills_rejects_missing_token(tmp_path, monkeypatch):
    """配置了 MARKET_INTERNAL_TOKEN 但请求未带 token 时应返回 403。"""
    from market.config import constant

    monkeypatch.setattr(constant, "MARKET_INTERNAL_TOKEN", "secret123")

    app = _make_app(tmp_path)
    client = TestClient(app)

    resp = client.post("/api/market/internal/tenants/alice/sync-skills")

    assert resp.status_code == 403


def test_internal_sync_skills_accepts_correct_token(tmp_path, monkeypatch):
    """配置了 token 且请求带正确 token 时应通过。"""
    from market.config import constant

    monkeypatch.setattr(constant, "MARKET_INTERNAL_TOKEN", "secret123")

    app = _make_app(tmp_path)
    client = TestClient(app)

    with pytest.MonkeyPatch.context() as mp:
        from market.marketplace import skill_sync

        mp.setattr(
            skill_sync,
            "process_tenant_skills",
            AsyncMock(
                return_value={
                    "tenant_id": "alice",
                    "total_workspaces": 0,
                    "total_skills": 0,
                    "synced": 0,
                    "errors": [],
                    "details": [],
                },
            ),
        )
        resp = client.post(
            "/api/market/internal/tenants/alice/sync-skills",
            headers={"X-Internal-Token": "secret123"},
        )

    assert resp.status_code == 200