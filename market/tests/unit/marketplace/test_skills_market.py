# -*- coding: utf-8 -*-
import asyncio
import json
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from market.app.routers import skills_market as skills_router


def _make_app(tmp_path):
    from fastapi import FastAPI
    from market.app.routers.skills_market import router
    from market.marketplace.service import MarketplaceService
    from market.database.connection import DatabaseConnection

    mock_db = AsyncMock(spec=DatabaseConnection)
    mock_db.is_connected = True
    mock_db.execute = AsyncMock(return_value=1)
    mock_db.fetch_one = AsyncMock(return_value=None)
    mock_db.fetch_all = AsyncMock(return_value=[])

    svc = MarketplaceService(
        db=mock_db,
        marketplace_root=tmp_path / "market",
        swe_root=tmp_path / "swe",
    )
    app = FastAPI()
    app.state.marketplace = svc
    app.include_router(router, prefix="/api")
    return app


def test_publish_skill_returns_201(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    payload = {
        "name": "skill_x",
        "description": "test",
        "creator_id": "u1",
        "creator_name": "User",
        "skill_json": {"name": "skill_x"},
        "skill_md": "# Skill X",
    }
    resp = client.post(
        "/api/market/skills",
        json=payload,
        headers={"X-Source-Id": "src_a", "X-Manager": "true"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "skill_x"
    assert data["version"] == "1.0.0"


def test_publish_skill_non_manager_returns_403(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    payload = {
        "name": "skill_x",
        "description": "",
        "creator_id": "u1",
        "creator_name": "",
        "skill_json": {},
        "skill_md": "",
    }
    resp = client.post(
        "/api/market/skills",
        json=payload,
        headers={"X-Source-Id": "src_a"},
    )
    assert resp.status_code == 403


def test_unpublish_skill_returns_204(tmp_path):
    from market.marketplace.schemas import PublishSkillRequest

    app = _make_app(tmp_path)
    svc = app.state.marketplace
    req = PublishSkillRequest(
        name="skill_y",
        description="",
        creator_id="u1",
        creator_name="",
        skill_json={},
        skill_md="",
    )
    item, _ = asyncio.run(svc.publish_skill("src_a", req))
    client = TestClient(app)
    resp = client.delete(
        f"/api/market/skills/{item.item_id}",
        headers={
            "X-Source-Id": "src_a",
            "X-Manager": "true",
            "X-User-Id": "u1",
            "X-User-Name": "User",
        },
    )
    assert resp.status_code == 204


def test_unpublish_skill_not_found_returns_404(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.delete(
        "/api/market/skills/nonexistent-id",
        headers={
            "X-Source-Id": "src_a",
            "X-Manager": "true",
            "X-User-Id": "u1",
            "X-User-Name": "User",
        },
    )
    assert resp.status_code == 404


def test_distribute_skill_returns_200(tmp_path, monkeypatch):
    from market.marketplace.schemas import PublishSkillRequest

    app = _make_app(tmp_path)
    svc = app.state.marketplace
    req = PublishSkillRequest(
        name="skill_z",
        description="",
        creator_id="u1",
        creator_name="",
        skill_json={},
        skill_md="",
    )
    item, _ = asyncio.run(svc.publish_skill("src_a", req))
    svc.db.fetch_all = AsyncMock(
        return_value=[
            {"tenant_id": "user1", "tenant_name": "User One", "bbk_id": "200"},
        ],
    )

    monkeypatch.setattr(
        skills_router.asyncio,
        "create_task",
        lambda coro: coro.close() or object(),
    )
    client = TestClient(app)
    resp = client.post(
        f"/api/market/skills/{item.item_id}/distribute",
        json={"target_type": "all", "target_values": []},
        headers={
            "X-Source-Id": "src_a",
            "X-Manager": "true",
            "X-User-Id": "u1",
            "X-User-Name": "User",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["task_id"]


def test_publish_skill_missing_source_id_returns_400(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    payload = {
        "name": "skill_x",
        "description": "",
        "creator_id": "u1",
        "creator_name": "",
        "skill_json": {},
        "skill_md": "",
    }
    resp = client.post(
        "/api/market/skills",
        json=payload,
        headers={"X-Manager": "true"},
    )
    assert resp.status_code == 400


def test_publish_skill_upload_reactivates_inactive_skill(tmp_path):
    """验证下架后重新上传同名技能可以成功上架（复用条目，版本号递增）."""
    import io
    import zipfile
    from market.marketplace.fs import load_index

    app = _make_app(tmp_path)
    svc = app.state.marketplace
    client = TestClient(app)

    # 第一步：通过 JSON API 创建技能
    payload = {
        "name": "test_skill",
        "description": "initial",
        "creator_id": "u1",
        "creator_name": "User",
        "skill_json": {"name": "test_skill"},
        "skill_md": "# Test Skill",
    }
    resp = client.post(
        "/api/market/skills",
        json=payload,
        headers={"X-Source-Id": "src_a", "X-Manager": "true"},
    )
    assert resp.status_code == 201
    item_id = resp.json()["item_id"]
    assert resp.json()["version"] == "1.0.0"

    # 第二步：下架技能
    resp = client.delete(
        f"/api/market/skills/{item_id}",
        headers={
            "X-Source-Id": "src_a",
            "X-Manager": "true",
            "X-User-Id": "u1",
            "X-User-Name": "User",
        },
    )
    assert resp.status_code == 204

    # 验证状态已变为 inactive
    items = load_index(svc.marketplace_root, "src_a")
    inactive_item = next(i for i in items if i.item_id == item_id)
    assert inactive_item.status == "inactive"

    # 第三步：创建同名技能的 zip 文件并上传
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr(
            "test_skill/skill.json",
            json.dumps({"name": "test_skill", "description": "updated"}),
        )
        zf.writestr("test_skill/SKILL.md", "# Updated Skill")

    zip_buffer.seek(0)
    resp = client.post(
        "/api/market/skills/publish-upload?overwrite=true",
        files={"file": ("skill.zip", zip_buffer, "application/zip")},
        headers={
            "X-Source-Id": "src_a",
            "X-Manager": "true",
            "X-User-Id": "u1",
            "X-User-Name": "User",
        },
    )
    assert resp.status_code == 201
    data = resp.json()

    # 验证：成功上传，没有冲突，版本号递增
    assert "test_skill" in data["imported"]
    assert data["count"] == 1
    assert data.get("conflicts") is None or len(data.get("conflicts", [])) == 0

    # 验证条目被复用，状态重新激活，版本号递增
    items = load_index(svc.marketplace_root, "src_a")
    reactivated_item = next(i for i in items if i.item_id == item_id)
    assert reactivated_item.status == "active"
    assert reactivated_item.version == "1.0.1"  # patch 版本递增


def test_switch_version_updates_market_item_creator(tmp_path):
    """T4 R8：switch_version 同步更新 MarketItem.creator_id/creator_name 到目标快照来源."""
    import json as _json
    from market.marketplace.fs import save_index, load_index
    from market.marketplace.models import MarketItem
    from market.app.routers.skill_versions import _update_skill_index

    marketplace_root = tmp_path / "market"
    source_id = "src1"
    item_id = "item1"
    skill_dir = marketplace_root / source_id / "skills" / item_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        '---\nname: t\ndescription: d\nversion: "2.0.0"\n---\n',
        encoding="utf-8",
    )

    # 起始：creator=alice，市场版本 2.0.0
    save_index(
        marketplace_root,
        source_id,
        [
            MarketItem(
                item_id=item_id,
                item_type="skill",
                name="t",
                description="d",
                version="2.0.0",
                creator_id="alice_id",
                creator_name="alice",
                status="active",
            ),
        ],
    )

    # 准备 versions.json：v1.0.0 source_user=bob
    versions_path = (
        marketplace_root
        / source_id
        / "skill_versions"
        / item_id
        / "versions.json"
    )
    versions_path.parent.mkdir(parents=True, exist_ok=True)
    versions_path.write_text(
        _json.dumps(
            {
                "skill_name": "t",
                "versions": [
                    {
                        "version_id": "1.0.0",
                        "created_at": "2025-01-01T00:00:00+00:00",
                        "created_by": "admin",
                        "created_by_name": "admin",
                        "source_user_id": "bob_id",
                        "source_user_name": "bob",
                        "source_user_version": "1.0.0",
                        "signature": "x",
                        "is_current": True,
                        "is_initial": True,
                        "description": "",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class _FakeMarketplace:
        pass

    fake = _FakeMarketplace()
    fake.marketplace_root = marketplace_root

    _update_skill_index(fake, source_id, item_id, skill_dir, "1.0.0")

    items = load_index(marketplace_root, source_id)
    item = items[0]
    assert item.version == "1.0.0"
    # R8: creator_id/name 跟随目标快照的 source_user_*
    assert item.creator_id == "bob_id"
    assert item.creator_name == "bob"


def test_switch_version_falls_back_to_created_by_when_no_source_user(tmp_path):
    """T4 R8 边界：source_user_* 为空时回退到 created_by."""
    import json as _json
    from market.marketplace.fs import save_index, load_index
    from market.marketplace.models import MarketItem
    from market.app.routers.skill_versions import _update_skill_index

    marketplace_root = tmp_path / "market"
    source_id = "src1"
    item_id = "item2"
    skill_dir = marketplace_root / source_id / "skills" / item_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        '---\nname: t\ndescription: d\nversion: "1.0.0"\n---\n',
        encoding="utf-8",
    )
    save_index(
        marketplace_root,
        source_id,
        [
            MarketItem(
                item_id=item_id,
                item_type="skill",
                name="t",
                description="d",
                version="2.0.0",
                creator_id="alice_id",
                creator_name="alice",
                status="active",
            ),
        ],
    )
    versions_path = (
        marketplace_root
        / source_id
        / "skill_versions"
        / item_id
        / "versions.json"
    )
    versions_path.parent.mkdir(parents=True, exist_ok=True)
    versions_path.write_text(
        _json.dumps(
            {
                "skill_name": "t",
                "versions": [
                    {
                        "version_id": "1.0.0",
                        "created_at": "2025-01-01T00:00:00+00:00",
                        "created_by": "admin_id",
                        "created_by_name": "Admin",
                        "source_user_id": "",
                        "source_user_name": "",
                        "source_user_version": "",
                        "signature": "x",
                        "is_current": True,
                        "is_initial": True,
                        "description": "",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class _FakeMarketplace:
        pass

    fake = _FakeMarketplace()
    fake.marketplace_root = marketplace_root
    _update_skill_index(fake, source_id, item_id, skill_dir, "1.0.0")

    items = load_index(marketplace_root, source_id)
    item = items[0]
    assert item.creator_id == "admin_id"
    assert item.creator_name == "Admin"
