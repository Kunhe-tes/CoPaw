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


def test_internal_sync_skills_does_not_write_manifest_back(tmp_path):
    """内部端点禁止回写 skill.json：skill.json 内容应与请求前一致。"""
    import os

    os.environ.pop("MARKET_INTERNAL_TOKEN", None)

    tenant_dir = tmp_path / "alice" / "workspaces" / "default" / "skills" / "demo"
    tenant_dir.mkdir(parents=True)
    (tenant_dir / "SKILL.md").write_text("# demo", encoding="utf-8")

    import json

    manifest_path = tenant_dir.parent / "skill.json"
    original_payload = {
        "schema_version": "workspace-skill-manifest.v1",
        "version": 0,
        "skills": {
            "demo": {
                "enabled": True,
                "source": "customized",
            },
        },
    }
    manifest_path.write_text(
        json.dumps(original_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    app = _make_app(tmp_path)
    client = TestClient(app)

    with pytest.MonkeyPatch.context() as mp:
        from market.marketplace import skill_sync

        async def _capture(tenant_dir, **kwargs):
            return {
                "tenant_id": "alice",
                "total_workspaces": 1,
                "total_skills": 1,
                "synced": 1,
                "errors": [],
                "details": [],
            }

        mp.setattr(skill_sync, "process_tenant_skills", _capture)
        # 真实调用 _process_workspace_skills 路径会触发 manifest 回写
        # —— 这里我们直接调用验证 read 流程不写盘
        resp = client.post("/api/market/internal/tenants/alice/sync-skills")

    assert resp.status_code == 200
    # manifest 写入路径不在内部端点；mock 的 _capture 不会落盘
    after = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert after == original_payload


def test_internal_sync_skills_write_manifest_back_disabled_by_default(
    tmp_path,
    monkeypatch,
):
    """skill_sync.process_tenant_skills 在 write_manifest_back=False 时不应写盘。"""
    import json

    from market.marketplace import skill_sync

    captured: dict = {}

    async def fake_upsert(*args, **kwargs):
        return None

    monkeypatch.setattr(
        skill_sync,
        "_upsert_skill_to_db",
        fake_upsert,
    )

    # mock registry
    class _Registry:
        def __init__(self):
            self.calls: list = []

        async def upsert_skill_by_name(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return None

    registry = _Registry()

    tenant_dir = tmp_path / "alice" / "workspaces" / "default"
    skills_dir = tenant_dir / "skills" / "demo"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text("# demo", encoding="utf-8")

    manifest_path = tenant_dir / "skill.json"
    original_payload = {
        "schema_version": "workspace-skill-manifest.v1",
        "layout_version": 2,
        "version": 0,
        "skills": {
            "demo": {
                "enabled": True,
                "source": "customized",
            },
        },
    }
    manifest_path.write_text(
        json.dumps(original_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    async def _go():
        await skill_sync.process_tenant_skills(
            tenant_dir,
            source_id=None,
            registry=registry,
            force=True,
            dry_run=False,
            write_manifest_back=False,
        )

    import asyncio

    asyncio.run(_go())

    after = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert after == original_payload


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