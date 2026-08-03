# -*- coding: utf-8 -*-
"""sync_tenant_skills 单元测试."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_sync_tenant_skills_inserts_into_db(tmp_path: Path):
    """新用户的 manifest + skills 目录扫描后应全部 upsert 到 swe_skills。"""
    from market.marketplace.skill_sync import sync_tenant_skills

    tenant_dir = tmp_path / "alice"
    workspace = tenant_dir / "workspaces" / "default"
    skill_dir = workspace / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nskill_id: demo\ncn_name: 示例\n---\n# 示例技能",
        encoding="utf-8",
    )

    manifest_path = workspace / "skill.json"
    manifest_path.write_text(
        json.dumps(
            {
                "skills": {
                    "demo": {
                        "source": "marketplace:42",
                        "enabled": True,
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    registry = MagicMock()
    registry.upsert_skill_by_name = AsyncMock(return_value=True)

    inserted = await sync_tenant_skills(
        tenant_dir,
        registry,
        source_id="default",
        force=False,
    )

    assert inserted == 1
    registry.upsert_skill_by_name.assert_called_once()
    call_kwargs = registry.upsert_skill_by_name.call_args.kwargs
    assert call_kwargs["skill_name"] == "demo"
    assert call_kwargs["tenant_id"] == "alice"
    assert call_kwargs["source"] == "marketplace:42"


@pytest.mark.asyncio
async def test_sync_tenant_skills_source_defaults_to_customized(
    tmp_path: Path,
):
    """manifest 缺 source 字段时，source 应兜底为 customized。"""
    from market.marketplace.skill_sync import sync_tenant_skills

    tenant_dir = tmp_path / "bob"
    workspace = tenant_dir / "workspaces" / "default"
    skill_dir = workspace / "skills" / "myskill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nskill_id: myskill\ncn_name: 我的技能\n---\n# 我的技能",
        encoding="utf-8",
    )

    manifest_path = workspace / "skill.json"
    manifest_path.write_text(
        json.dumps(
            {"skills": {"myskill": {"enabled": True}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    registry = MagicMock()
    registry.upsert_skill_by_name = AsyncMock(return_value=True)

    inserted = await sync_tenant_skills(
        tenant_dir, registry, source_id="default"
    )

    assert inserted == 1
    call_kwargs = registry.upsert_skill_by_name.call_args.kwargs
    assert call_kwargs["source"] == "customized"


@pytest.mark.asyncio
async def test_sync_tenant_skills_idempotent(tmp_path: Path):
    """重跑 sync 不应报错（upsert 幂等由 SkillRegistry 保证）。"""
    from market.marketplace.skill_sync import sync_tenant_skills

    tenant_dir = tmp_path / "carol"
    workspace = tenant_dir / "workspaces" / "default"
    skill_dir = workspace / "skills" / "x"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# x", encoding="utf-8")

    manifest_path = workspace / "skill.json"
    manifest_path.write_text(
        json.dumps(
            {"skills": {"x": {"source": "customized", "enabled": True}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    registry = MagicMock()
    registry.upsert_skill_by_name = AsyncMock(return_value=True)

    first = await sync_tenant_skills(tenant_dir, registry, source_id="default")
    second = await sync_tenant_skills(
        tenant_dir, registry, source_id="default"
    )

    assert first == 1
    assert second == 1
    assert registry.upsert_skill_by_name.call_count == 2


@pytest.mark.asyncio
async def test_sync_tenant_skills_empty_workspace_returns_zero(tmp_path: Path):
    """空 workspace 不应报错，返回 0。"""
    from market.marketplace.skill_sync import sync_tenant_skills

    tenant_dir = tmp_path / "dan"
    (tenant_dir / "workspaces" / "default").mkdir(parents=True)

    registry = MagicMock()
    registry.upsert_skill_by_name = AsyncMock(return_value=True)

    inserted = await sync_tenant_skills(
        tenant_dir, registry, source_id="default"
    )

    assert inserted == 0
    registry.upsert_skill_by_name.assert_not_called()


def test_extract_skill_fields_prefers_manifest_skill_id(tmp_path: Path):
    """manifest entry 的 metadata.skill_id 优先于 SKILL.md 派生。"""
    from market.marketplace.skill_sync import _extract_skill_fields

    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nskill_id: should_be_ignored\n---\n# demo",
        encoding="utf-8",
    )

    entry = {
        "source": "customized",
        "metadata": {"skill_id": "explicit_locked_id"},
    }

    skill_id, _ = _extract_skill_fields(
        skill_dir,
        entry,
        skill_name="demo",
        user_id="alice",
        source_id="default",
        force=False,
    )

    assert skill_id == "explicit_locked_id"


def test_extract_skill_fields_ignores_manifest_skill_id_when_force(
    tmp_path: Path,
):
    """force=True 时跳过 manifest metadata.skill_id，走派生路径。"""
    from market.marketplace.skill_sync import _extract_skill_fields

    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# demo", encoding="utf-8")

    entry = {
        "source": "customized",
        "metadata": {"skill_id": "explicit_locked_id"},
    }

    skill_id, _ = _extract_skill_fields(
        skill_dir,
        entry,
        skill_name="demo",
        user_id="alice",
        source_id="default",
        force=True,
    )

    # force=True 时走 extract_skill_id 派生，creator_id="" → "customized_demo"
    assert skill_id == "customized_demo"


def test_extract_skill_fields_consistent_across_users(tmp_path: Path):
    """同一技能名不同 user_id 应派生相同 skill_id（creator_id 段被剥离）。"""
    from market.marketplace.skill_sync import _extract_skill_fields

    skill_dir = tmp_path / "skills" / "weather"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# weather", encoding="utf-8")

    entry = {"source": "customized", "metadata": {}}

    id_alice, _ = _extract_skill_fields(
        skill_dir,
        entry,
        skill_name="weather",
        user_id="alice",
        source_id="default",
        force=False,
    )
    id_bob, _ = _extract_skill_fields(
        skill_dir,
        entry,
        skill_name="weather",
        user_id="bob",
        source_id="default",
        force=False,
    )

    # 不同用户走 _extract_skill_fields 应得到相同 skill_id
    assert id_alice == id_bob == "customized_weather"
