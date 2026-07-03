# -*- coding: utf-8 -*-
import asyncio
import json
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient


def _make_app(tmp_path):
    from fastapi import FastAPI
    from market.app.routers.skills_browse import router
    from market.marketplace.service import MarketplaceService
    from market.database.connection import DatabaseConnection

    mock_db = AsyncMock(spec=DatabaseConnection)
    mock_db.is_connected = False  # no DB needed for fs-only tests

    svc = MarketplaceService(
        db=mock_db,
        marketplace_root=tmp_path / "market",
        swe_root=tmp_path / "swe",
    )
    app = FastAPI()
    app.state.marketplace = svc
    app.include_router(router, prefix="/api")
    return app


def _publish(svc, source_id, name, bbk_ids=None):
    from market.marketplace.schemas import PublishSkillRequest

    req = PublishSkillRequest(
        name=name,
        description="desc",
        creator_id="u1",
        creator_name="User",
        skill_json={},
        skill_md="",
        bbk_ids=bbk_ids or [],
    )
    item, _ = asyncio.run(svc.publish_skill(source_id, req))
    return item


def test_list_skills_returns_active_items(tmp_path):
    app = _make_app(tmp_path)
    _publish(app.state.marketplace, "src_a", "skill_1")
    _publish(app.state.marketplace, "src_a", "skill_2")
    client = TestClient(app)
    resp = client.get(
        "/api/market/skills",
        headers={"X-Source-Id": "src_a", "X-Bbk-Id": "100"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_skills_missing_source_id_returns_400(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/api/market/skills", headers={"X-Bbk-Id": "100"})
    assert resp.status_code == 400


def test_list_skills_filters_by_category(tmp_path):
    from market.marketplace.schemas import PublishSkillRequest

    app = _make_app(tmp_path)
    svc = app.state.marketplace
    req1 = PublishSkillRequest(
        name="skill_cat1",
        description="",
        creator_id="u1",
        creator_name="",
        skill_json={},
        skill_md="",
        category_id=1,
    )
    req2 = PublishSkillRequest(
        name="skill_cat2",
        description="",
        creator_id="u1",
        creator_name="",
        skill_json={},
        skill_md="",
        category_id=2,
    )
    asyncio.run(svc.publish_skill("src_a", req1))
    asyncio.run(svc.publish_skill("src_a", req2))
    client = TestClient(app)
    resp = client.get(
        "/api/market/skills?category_id=1",
        headers={"X-Source-Id": "src_a", "X-Bbk-Id": "100"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "skill_cat1"


def test_get_skill_detail_returns_200(tmp_path):
    app = _make_app(tmp_path)
    item = _publish(app.state.marketplace, "src_a", "skill_d")
    client = TestClient(app)
    resp = client.get(
        f"/api/market/skills/{item.item_id}",
        headers={"X-Source-Id": "src_a", "X-Bbk-Id": "100"},
    )
    assert resp.status_code == 200
    assert resp.json()["item_id"] == item.item_id


def test_get_skill_detail_not_found_returns_404(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get(
        "/api/market/skills/no-such-id",
        headers={"X-Source-Id": "src_a", "X-Bbk-Id": "100"},
    )
    assert resp.status_code == 404


def test_get_my_skills_returns_list(tmp_path):
    from market.marketplace.fs import get_user_skills_dir

    skills_dir = get_user_skills_dir(
        tmp_path / "swe",
        "user1",
        source_id="src_a",
    )
    skill_dir = skills_dir / "my_skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "skill.json").write_text(
        json.dumps({"source": "customized", "description": "my skill"}),
        encoding="utf-8",
    )
    app = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get(
        "/api/market/skills/mine",
        headers={"X-Source-Id": "src_a", "X-User-Id": "user1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["skill_name"] == "my_skill"
    assert data[0]["is_received"] is False


def test_get_received_skills_returns_only_received(tmp_path):
    from market.marketplace.fs import (
        get_user_skill_manifest_path,
        get_user_skills_dir,
    )

    skills_dir = get_user_skills_dir(
        tmp_path / "swe",
        "user2",
        source_id="src_a",
    )
    d1 = skills_dir / "created_skill"
    d1.mkdir(parents=True)
    (d1 / "skill.json").write_text(
        json.dumps({"source": "customized"}),
        encoding="utf-8",
    )
    d2 = skills_dir / "received_skill"
    d2.mkdir(parents=True)
    manifest_path = get_user_skill_manifest_path(
        tmp_path / "swe",
        "user2",
        source_id="src_a",
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-skill-manifest.v1",
                "version": 1,
                "skills": {
                    "created_skill": {
                        "source": "customized",
                        "metadata": {},
                    },
                    "received_skill": {
                        "source": "marketplace:item-1",
                        "metadata": {
                            "received_version": "1.0.0",
                        },
                    },
                },
            },
        ),
        encoding="utf-8",
    )
    app = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get(
        "/api/market/skills/received",
        headers={"X-Source-Id": "src_a", "X-User-Id": "user2"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["skill_name"] == "received_skill"
    assert data[0]["is_received"] is True


def test_decode_zip_filename_with_gbk_encoding():
    """Test that GBK-encoded Chinese filenames are correctly decoded."""
    from market.app.routers.skills_browse import _decode_zip_filename
    import zipfile

    # Simulate a ZipInfo object
    class MockInfo:
        def __init__(self, filename, flag_bits=0):
            self.filename = filename
            self.flag_bits = flag_bits

    # Test 1: UTF-8 flagged filename (should pass through unchanged)
    utf8_name = "测试技能/SKILL.md"
    info_utf8 = MockInfo(utf8_name, flag_bits=0x800)
    result = _decode_zip_filename(info_utf8.filename, info_utf8)
    assert result == utf8_name

    # Test 2: GBK encoded filename (simulating cp437 mis-decoding)
    original = "测试技能"
    gbk_bytes = original.encode("gbk")
    # Python's zipfile decodes non-UTF-8 filenames using cp437
    mis_decoded = gbk_bytes.decode("cp437")
    info_gbk = MockInfo(mis_decoded + "/SKILL.md", flag_bits=0)
    result = _decode_zip_filename(info_gbk.filename, info_gbk)
    assert result == original + "/SKILL.md"

    # Test 3: ASCII filename (should work normally)
    info_ascii = MockInfo("my_skill/SKILL.md", flag_bits=0)
    result = _decode_zip_filename(info_ascii.filename, info_ascii)
    assert result == "my_skill/SKILL.md"


def test_extract_zip_with_chinese_filename(tmp_path):
    """Test extracting a ZIP with Chinese filenames."""
    import zipfile
    import io
    from market.app.routers.skills_browse import _extract_zip_skills

    # Create a ZIP with Chinese filename (GBK encoded, no UTF-8 flag)
    skill_content = "---\nname: 中文技能\n---\n# 中文技能\n"
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        # Create entry with GBK-encoded filename (no UTF-8 flag)
        info = zipfile.ZipInfo("中文技能/SKILL.md")
        info.flag_bits = 0  # No UTF-8 flag
        info.compress_type = zipfile.ZIP_STORED
        # Write with GBK filename in the ZIP
        zf.writestr(info, skill_content.encode("utf-8"))

    zip_data = zip_buffer.getvalue()
    tmp_dir, found_skills = _extract_zip_skills(zip_data)
    assert len(found_skills) == 1
    skill_dir, skill_name = found_skills[0]
    # The skill name should be correctly decoded
    assert skill_name == "中文技能"
    assert (skill_dir / "SKILL.md").exists()

    # Cleanup
    import shutil

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_log_skill_operation_returns_200(tmp_path):
    """测试操作日志上报端点返回成功。"""
    from fastapi import FastAPI
    from market.app.routers.skills_browse import router
    from market.marketplace.service import MarketplaceService
    from market.database.connection import DatabaseConnection

    mock_db = AsyncMock(spec=DatabaseConnection)
    mock_db.is_connected = True
    mock_db.execute = AsyncMock()

    svc = MarketplaceService(
        db=mock_db,
        marketplace_root=tmp_path / "market",
        swe_root=tmp_path / "swe",
    )
    app = FastAPI()
    app.state.marketplace = svc
    app.include_router(router, prefix="/api")

    client = TestClient(app)
    resp = client.post(
        "/api/market/skills/operation-log",
        headers={
            "X-Source-Id": "console",
            "X-User-Id": "user123",
        },
        json={
            "operation": "create",
            "item_type": "skill",
            "item_name": "my_new_skill",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"success": True}
    mock_db.execute.assert_called_once()


def test_log_skill_operation_with_url_encoded_user_name(tmp_path):
    """测试 URL 编码的 user_name 能被正确解码。"""
    from fastapi import FastAPI
    from market.app.routers.skills_browse import router
    from market.marketplace.service import MarketplaceService
    from market.database.connection import DatabaseConnection

    mock_db = AsyncMock(spec=DatabaseConnection)
    mock_db.is_connected = True
    mock_db.execute = AsyncMock()

    svc = MarketplaceService(
        db=mock_db,
        marketplace_root=tmp_path / "market",
        swe_root=tmp_path / "swe",
    )
    app = FastAPI()
    app.state.marketplace = svc
    app.include_router(router, prefix="/api")

    client = TestClient(app)
    # 模拟 Agent 发送 URL 编码的中文名
    resp = client.post(
        "/api/market/skills/operation-log",
        headers={
            "X-Source-Id": "console",
            "X-User-Id": "user123",
        },
        json={
            "operation": "create",
            "item_type": "skill",
            "item_name": "my_skill",
            "user_name": "%E5%BC%A0%E4%B8%89",  # "张三" 的 URL 编码
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"success": True}
    # 验证解码后的 user_name 是 "张三"
    call_args = mock_db.execute.call_args
    assert call_args[0][1][2] == "张三"  # user_name 是第三个参数


def test_log_skill_operation_missing_user_id_returns_400(tmp_path):
    """测试缺少 X-User-Id 返回 400。"""
    from fastapi import FastAPI
    from market.app.routers.skills_browse import router
    from market.marketplace.service import MarketplaceService
    from market.database.connection import DatabaseConnection

    mock_db = AsyncMock(spec=DatabaseConnection)
    mock_db.is_connected = False

    svc = MarketplaceService(
        db=mock_db,
        marketplace_root=tmp_path / "market",
        swe_root=tmp_path / "swe",
    )
    app = FastAPI()
    app.state.marketplace = svc
    app.include_router(router, prefix="/api")

    client = TestClient(app)
    resp = client.post(
        "/api/market/skills/operation-log",
        headers={"X-Source-Id": "console"},
        json={
            "operation": "create",
            "item_type": "skill",
            "item_name": "my_new_skill",
        },
    )
    assert resp.status_code == 400


def test_log_skill_operation_db_failure_returns_success(tmp_path):
    """测试数据库写入失败仍返回成功（失败忽略策略）。"""
    from fastapi import FastAPI
    from market.app.routers.skills_browse import router
    from market.marketplace.service import MarketplaceService
    from market.database.connection import DatabaseConnection

    mock_db = AsyncMock(spec=DatabaseConnection)
    mock_db.is_connected = True
    mock_db.execute = AsyncMock(side_effect=Exception("DB error"))

    svc = MarketplaceService(
        db=mock_db,
        marketplace_root=tmp_path / "market",
        swe_root=tmp_path / "swe",
    )
    app = FastAPI()
    app.state.marketplace = svc
    app.include_router(router, prefix="/api")

    client = TestClient(app)
    resp = client.post(
        "/api/market/skills/operation-log",
        headers={
            "X-Source-Id": "console",
            "X-User-Id": "user123",
        },
        json={
            "operation": "create",
            "item_type": "skill",
            "item_name": "my_new_skill",
        },
    )
    # 失败忽略：即使 DB 写入失败，仍返回成功
    assert resp.status_code == 200
    assert resp.json() == {"success": True}
