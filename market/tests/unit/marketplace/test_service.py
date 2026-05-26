# -*- coding: utf-8 -*-
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


def _make_service(tmp_path, mock_db=None):
    from market.marketplace.service import MarketplaceService

    if mock_db is None:
        mock_db = AsyncMock()
        mock_db.is_connected = True
        mock_db.fetch_one = AsyncMock(return_value=None)
        mock_db.fetch_all = AsyncMock(return_value=[])
    return MarketplaceService(
        db=mock_db,
        marketplace_root=tmp_path / "market",
        swe_root=tmp_path / "swe",
    )


@pytest.mark.asyncio
async def test_publish_skill_creates_index_entry(tmp_path):
    from market.marketplace.schemas import PublishSkillRequest

    svc = _make_service(tmp_path)
    req = PublishSkillRequest(
        name="skill_a",
        description="desc",
        creator_id="user1",
        creator_name="User One",
        skill_json={"name": "skill_a"},
        skill_md="# Skill A",
    )
    item = await svc.publish_skill("src_a", req)
    assert item.name == "skill_a"
    assert item.version == "1.0.0"
    assert item.status == "active"
    # index.json should exist
    index_path = tmp_path / "market" / "src_a" / "index.json"
    assert index_path.exists()
    data = json.loads(index_path.read_text())
    assert len(data["items"]) == 1


@pytest.mark.asyncio
async def test_publish_skill_increments_version_on_republish(tmp_path):
    from market.marketplace.schemas import PublishSkillRequest

    svc = _make_service(tmp_path)
    req = PublishSkillRequest(
        name="skill_a",
        description="",
        creator_id="u1",
        creator_name="",
        skill_json={},
        skill_md="",
    )
    await svc.publish_skill("src_a", req)
    item2 = await svc.publish_skill("src_a", req)
    assert item2.version == "1.0.1"


@pytest.mark.asyncio
async def test_unpublish_skill_sets_inactive(tmp_path):
    from market.marketplace.schemas import PublishSkillRequest

    svc = _make_service(tmp_path)
    req = PublishSkillRequest(
        name="skill_b",
        description="",
        creator_id="u1",
        creator_name="",
        skill_json={},
        skill_md="",
    )
    item = await svc.publish_skill("src_a", req)
    await svc.unpublish_skill("src_a", item.item_id, "u1", "User One")
    items = await svc.list_skills("src_a", user_bbk_id="100")
    assert all(
        i.status == "inactive" for i in items if i.item_id == item.item_id
    )


@pytest.mark.asyncio
async def test_list_skills_filters_by_bbk_id(tmp_path):
    from market.marketplace.schemas import PublishSkillRequest

    svc = _make_service(tmp_path)
    # skill visible to all (bbk_ids=[])
    req_all = PublishSkillRequest(
        name="skill_all",
        description="",
        creator_id="u1",
        creator_name="",
        skill_json={},
        skill_md="",
        bbk_ids=[],
    )
    # skill visible only to bbk_id=200
    req_200 = PublishSkillRequest(
        name="skill_200",
        description="",
        creator_id="u1",
        creator_name="",
        skill_json={},
        skill_md="",
        bbk_ids=["200"],
    )
    await svc.publish_skill("src_a", req_all)
    await svc.publish_skill("src_a", req_200)
    # bbk_id=100 (总行) sees all
    items_100 = await svc.list_skills("src_a", user_bbk_id="100")
    assert len(items_100) == 2
    # bbk_id=300 sees only skill_all (bbk_ids=[])
    items_300 = await svc.list_skills("src_a", user_bbk_id="300")
    assert len(items_300) == 1
    assert items_300[0].name == "skill_all"


@pytest.mark.asyncio
async def test_get_skill_detail_returns_item(tmp_path):
    from market.marketplace.schemas import PublishSkillRequest

    svc = _make_service(tmp_path)
    req = PublishSkillRequest(
        name="skill_c",
        description="",
        creator_id="u1",
        creator_name="",
        skill_json={},
        skill_md="",
    )
    item = await svc.publish_skill("src_a", req)
    detail = await svc.get_skill_detail(
        "src_a",
        item.item_id,
        user_bbk_id="100",
    )
    assert detail is not None
    assert detail.item_id == item.item_id


@pytest.mark.asyncio
async def test_get_skill_detail_returns_none_for_unknown(tmp_path):
    svc = _make_service(tmp_path)
    detail = await svc.get_skill_detail(
        "src_a",
        "nonexistent-id",
        user_bbk_id="100",
    )
    assert detail is None


@pytest.mark.asyncio
async def test_get_my_skills_returns_time_fields(tmp_path):
    """get_my_skills 应返回 created_at 和 updated_at 字段."""
    from market.marketplace.fs import get_user_skill_manifest_path
    from market.marketplace.service import get_user_skills_dir

    svc = _make_service(tmp_path)
    user_id = "test_user"
    source_id = "test_source"
    agent_id = "default"

    # 创建用户技能目录
    skills_dir = get_user_skills_dir(
        tmp_path / "swe",
        user_id,
        agent_id,
        source_id,
    )
    skill_dir = skills_dir / "test_skill"
    skill_dir.mkdir(parents=True)

    manifest_path = get_user_skill_manifest_path(
        tmp_path / "swe",
        user_id,
        agent_id,
        source_id,
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-skill-manifest.v1",
                "version": 1,
                "skills": {
                    "test_skill": {
                        "source": "customized",
                        "created_at": "2025-05-14T10:00:00+00:00",
                        "updated_at": "2025-05-14T12:00:00+00:00",
                        "metadata": {
                            "name": "Test Skill",
                            "description": "A test skill",
                        },
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text("# Test Skill", encoding="utf-8")

    # 调用服务
    result = await svc.get_my_skills(source_id, user_id, agent_id)

    assert len(result) == 1
    assert result[0].skill_name == "test_skill"
    assert result[0].created_at == "2025-05-14T10:00:00+00:00"
    assert result[0].updated_at == "2025-05-14T12:00:00+00:00"


@pytest.mark.asyncio
async def test_get_my_skills_handles_missing_time_fields(tmp_path):
    """get_my_skills 应处理缺失的时间字段."""
    from market.marketplace.fs import get_user_skill_manifest_path
    from market.marketplace.service import get_user_skills_dir

    svc = _make_service(tmp_path)
    user_id = "test_user"
    source_id = "test_source"
    agent_id = "default"

    # 创建用户技能目录
    skills_dir = get_user_skills_dir(
        tmp_path / "swe",
        user_id,
        agent_id,
        source_id,
    )
    skill_dir = skills_dir / "old_skill"
    skill_dir.mkdir(parents=True)

    manifest_path = get_user_skill_manifest_path(
        tmp_path / "swe",
        user_id,
        agent_id,
        source_id,
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-skill-manifest.v1",
                "version": 1,
                "skills": {
                    "old_skill": {
                        "source": "customized",
                        "metadata": {
                            "name": "Old Skill",
                            "description": "An old skill without time fields",
                        },
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text("# Old Skill", encoding="utf-8")

    # 调用服务
    result = await svc.get_my_skills(source_id, user_id, agent_id)

    assert len(result) == 1
    assert result[0].skill_name == "old_skill"
    assert result[0].created_at is None
    assert result[0].updated_at is None


@pytest.mark.asyncio
async def test_get_my_skills_reads_frontmatter_and_market_metadata(tmp_path):
    """get_my_skills 应组合 frontmatter、manifest 和市场版本信息."""
    from market.marketplace.fs import get_user_skill_manifest_path
    from market.marketplace.schemas import PublishSkillRequest
    from market.marketplace.service import get_user_skills_dir

    svc = _make_service(tmp_path)
    user_id = "test_user"
    source_id = "test_source"
    agent_id = "default"

    published = await svc.publish_skill(
        source_id,
        PublishSkillRequest(
            name="Market Skill",
            description="market desc",
            creator_id="creator-1",
            creator_name="张三",
            skill_json={},
            skill_md="",
        ),
    )

    skills_dir = get_user_skills_dir(
        tmp_path / "swe",
        user_id,
        agent_id,
        source_id,
    )
    skill_dir = skills_dir / "market_skill_copy"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: Market Skill\n"
        "description: 从前言读取\n"
        "---\n"
        "# Market Skill\n",
        encoding="utf-8",
    )

    manifest_path = get_user_skill_manifest_path(
        tmp_path / "swe",
        user_id,
        agent_id,
        source_id,
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-skill-manifest.v1",
                "version": 1,
                "skills": {
                    "market_skill_copy": {
                        "source": f"marketplace:{published.item_id}",
                        "enabled": False,
                        "created_at": "2025-05-14T10:00:00+00:00",
                        "updated_at": "2025-05-14T12:00:00+00:00",
                        "metadata": {
                            "received_version": "0.9.0",
                            "distributed_by": "admin1",
                            "creator_name": "%E5%BC%A0%E4%B8%89",
                            "category_id": 9,
                        },
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = await svc.get_my_skills(source_id, user_id, agent_id)

    assert len(result) == 1
    assert result[0].display_name == "Market Skill"
    assert result[0].description == "从前言读取"
    assert result[0].is_received is True
    assert result[0].has_update is True
    assert result[0].enabled is False
    assert result[0].distributed_by == "admin1"
    assert result[0].creator_name == "张三"
    assert result[0].category == "9"
    assert result[0].created_at == "2025-05-14T10:00:00+00:00"
    assert result[0].updated_at == "2025-05-14T12:00:00+00:00"


@pytest.mark.asyncio
async def test_recall_skill_by_name_removes_skill_dir_and_manifest(tmp_path):
    """按名称撤回技能时，应删除目录并移除 manifest 记录."""
    from market.marketplace.fs import (
        get_user_skill_manifest_path,
        get_user_skills_dir,
    )
    from market.marketplace.schemas import RecallRequest

    mock_db = AsyncMock()
    mock_db.is_connected = False
    svc = _make_service(tmp_path, mock_db=mock_db)
    svc.disable_skill = AsyncMock(return_value={"success": True})
    svc._trigger_agent_reload = AsyncMock()

    user_id = "user-1"
    source_id = "source-1"
    skill_name = "skill_to_recall"

    skills_dir = get_user_skills_dir(
        tmp_path / "swe",
        user_id,
        "default",
        source_id,
    )
    skill_dir = skills_dir / skill_name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Skill", encoding="utf-8")

    manifest_path = get_user_skill_manifest_path(
        tmp_path / "swe",
        user_id,
        "default",
        source_id,
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-skill-manifest.v1",
                "version": 1,
                "skills": {
                    skill_name: {
                        "source": "customized",
                        "metadata": {"name": skill_name},
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = await svc.recall_skill(
        source_id,
        None,
        "admin-1",
        "Admin",
        RecallRequest(skill_name=skill_name, target_user_ids=[user_id]),
    )

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert result.recalled_count == 1
    assert result.failed_count == 0
    assert result.results[0].success is True
    assert not skill_dir.exists()
    assert skill_name not in manifest_data["skills"]


@pytest.mark.asyncio
async def test_recall_mcp_by_name_removes_client_from_agent_config(tmp_path):
    """按名称撤回 MCP 时，应从 agent 配置中移除目标 client."""
    from market.marketplace.fs import resolve_effective_user_id
    from market.marketplace.schemas import RecallRequest

    mock_db = AsyncMock()
    mock_db.is_connected = False
    svc = _make_service(tmp_path, mock_db=mock_db)
    svc._trigger_agent_reload = AsyncMock()

    user_id = "user-1"
    source_id = "source-1"
    client_key = "mcp_client"
    effective_user_id = resolve_effective_user_id(user_id, source_id)
    agent_config_path = (
        tmp_path
        / "swe"
        / effective_user_id
        / "workspaces"
        / "default"
        / "agent.json"
    )
    agent_config_path.parent.mkdir(parents=True, exist_ok=True)
    agent_config_path.write_text(
        json.dumps(
            {
                "mcp": {
                    "clients": {
                        client_key: {"source": "marketplace:item-1"},
                        "other_client": {"source": "marketplace:item-2"},
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = await svc.recall_mcp(
        source_id,
        None,
        "admin-1",
        "Admin",
        RecallRequest(mcp_name=client_key, target_user_ids=[user_id]),
    )

    config_data = json.loads(agent_config_path.read_text(encoding="utf-8"))
    assert result.recalled_count == 1
    assert result.failed_count == 0
    assert result.results[0].success is True
    assert client_key not in config_data["mcp"]["clients"]
    assert "other_client" in config_data["mcp"]["clients"]
