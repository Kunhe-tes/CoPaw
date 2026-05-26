# -*- coding: utf-8 -*-
import json
import pytest
from pathlib import Path


def test_get_marketplace_dir(tmp_path):
    from market.marketplace.fs import get_marketplace_dir

    result = get_marketplace_dir(tmp_path, "source_a")
    assert result == tmp_path / "source_a"


def test_get_index_path(tmp_path):
    from market.marketplace.fs import get_index_path

    result = get_index_path(tmp_path, "source_a")
    assert result == tmp_path / "source_a" / "index.json"


def test_load_index_returns_empty_when_not_exists(tmp_path):
    from market.marketplace.fs import load_index

    result = load_index(tmp_path, "source_a")
    assert result == []


def test_save_and_load_index(tmp_path):
    from market.marketplace.fs import load_index, save_index
    from market.marketplace.models import MarketItem

    item = MarketItem(
        item_id="uuid-1",
        item_type="skill",
        name="test_skill",
        description="desc",
        version="1.0.0",
        creator_id="user1",
        creator_name="User One",
        category_id=None,
        bbk_ids=[],
        status="active",
    )
    save_index(tmp_path, "source_a", [item])
    loaded = load_index(tmp_path, "source_a")
    assert len(loaded) == 1
    assert loaded[0].name == "test_skill"


def test_get_skill_dir_in_marketplace(tmp_path):
    from market.marketplace.fs import get_skill_dir

    result = get_skill_dir(tmp_path, "source_a", "item-123")
    assert result == tmp_path / "source_a" / "skills" / "item-123"


def test_get_user_skills_dir(tmp_path):
    from market.marketplace.fs import get_user_skills_dir
    from market.runtime.context import encode_scope_id

    result = get_user_skills_dir(tmp_path, "user1", "agent1", "source_a")
    assert result == (
        tmp_path
        / encode_scope_id("user1", "source_a")
        / "workspaces"
        / "agent1"
        / "skills"
    )


def test_get_user_skills_dir_allows_main_service_identity_values(tmp_path):
    from market.marketplace.fs import get_user_skills_dir
    from market.runtime.context import encode_scope_id

    result = get_user_skills_dir(
        tmp_path,
        "alice@example.com",
        "agent1",
        "skill:xlsx",
    )

    assert result == (
        tmp_path
        / encode_scope_id("alice@example.com", "skill:xlsx")
        / "workspaces"
        / "agent1"
        / "skills"
    )


def test_get_user_skills_dir_keeps_legacy_scope_directory_untouched(tmp_path):
    from market.marketplace.fs import get_user_skills_dir
    from market.runtime.context import encode_scope_id

    canonical_scope_id = encode_scope_id("user1", "source_a")
    legacy_scope_dir = tmp_path / f"scope.v1.{canonical_scope_id}"
    legacy_skills_dir = legacy_scope_dir / "workspaces" / "agent1" / "skills"
    legacy_skills_dir.mkdir(parents=True)
    (legacy_skills_dir / "legacy.txt").write_text("legacy", encoding="utf-8")

    result = get_user_skills_dir(tmp_path, "user1", "agent1", "source_a")

    assert result == (
        tmp_path / canonical_scope_id / "workspaces" / "agent1" / "skills"
    )
    assert legacy_scope_dir.exists()
    assert not (result / "legacy.txt").exists()


def test_copy_skill_to_user_happy_path(tmp_path):
    from market.marketplace.fs import (
        copy_skill_to_user,
        get_skill_dir,
        get_user_skills_dir,
    )

    # Setup source skill
    src_dir = get_skill_dir(tmp_path / "market", "src_a", "item-1")
    src_dir.mkdir(parents=True)
    (src_dir / "SKILL.md").write_text("# Skill", encoding="utf-8")
    (src_dir / "skill.json").write_text(
        json.dumps({"name": "test"}),
        encoding="utf-8",
    )
    # Copy
    result = copy_skill_to_user(
        tmp_path / "market",
        "src_a",
        "item-1",
        tmp_path / "swe",
        "user1",
        "my_skill",
        "test_skill",
        "desc",
        "admin1",
        "1.0.0",
    )
    dst_dir = (
        get_user_skills_dir(tmp_path / "swe", "user1", source_id="src_a")
        / "my_skill"
    )
    assert result["status"] == "distributed"
    assert (dst_dir / "SKILL.md").read_text() == "# Skill"
    assert not (dst_dir / "skill.json").exists()
    assert result["metadata"] == {
        "name": "test_skill",
        "description": "desc",
        "distributed_by": "admin1",
        "received_version": "1.0.0",
    }


def test_copy_skill_to_user_missing_skill_md(tmp_path):
    from market.marketplace.fs import (
        copy_skill_to_user,
        get_skill_dir,
        get_user_skills_dir,
    )

    src_dir = get_skill_dir(tmp_path / "market", "src_a", "item-2")
    src_dir.mkdir(parents=True)
    # No SKILL.md, only skill.json
    (src_dir / "skill.json").write_text(
        json.dumps({"name": "test"}),
        encoding="utf-8",
    )
    result = copy_skill_to_user(
        tmp_path / "market",
        "src_a",
        "item-2",
        tmp_path / "swe",
        "user1",
        "my_skill2",
        "test",
        "desc",
        "admin1",
        "1.0.0",
    )
    dst_dir = (
        get_user_skills_dir(tmp_path / "swe", "user1", source_id="src_a")
        / "my_skill2"
    )
    assert result["status"] == "distributed"
    assert not (dst_dir / "SKILL.md").exists()
    assert not (dst_dir / "skill.json").exists()
    assert result["metadata"] == {
        "name": "test",
        "description": "desc",
        "distributed_by": "admin1",
        "received_version": "1.0.0",
    }


def test_copy_skill_to_user_missing_skill_json(tmp_path):
    from market.marketplace.fs import (
        copy_skill_to_user,
        get_skill_dir,
        get_user_skills_dir,
    )

    src_dir = get_skill_dir(tmp_path / "market", "src_a", "item-3")
    src_dir.mkdir(parents=True)
    (src_dir / "SKILL.md").write_text("# Skill", encoding="utf-8")
    # No skill.json
    result = copy_skill_to_user(
        tmp_path / "market",
        "src_a",
        "item-3",
        tmp_path / "swe",
        "user1",
        "my_skill3",
        "test",
        "desc",
        "admin1",
        "2.0.0",
    )
    dst_dir = (
        get_user_skills_dir(tmp_path / "swe", "user1", source_id="src_a")
        / "my_skill3"
    )
    assert result["status"] == "distributed"
    assert (dst_dir / "SKILL.md").read_text() == "# Skill"
    assert not (dst_dir / "skill.json").exists()
    assert result["metadata"] == {
        "name": "test",
        "description": "desc",
        "distributed_by": "admin1",
        "received_version": "2.0.0",
    }


def test_validate_path_segment_rejects_traversal(tmp_path):
    from market.marketplace.fs import get_marketplace_dir

    with pytest.raises(ValueError):
        get_marketplace_dir(tmp_path, "../../etc")


# ========== normalize_skill_name 测试 ==========


def test_normalize_skill_name_preserves_chinese():
    from market.marketplace.fs import normalize_skill_name

    # 中文应保留原样
    assert normalize_skill_name("数据分析") == "数据分析"
    assert normalize_skill_name("智能助手") == "智能助手"


def test_normalize_skill_name_handles_mixed():
    from market.marketplace.fs import normalize_skill_name

    # 中文和 ASCII 混合应保留（空格会被替换为下划线）
    assert normalize_skill_name("技能 v1.0") == "技能_v1.0"
    assert normalize_skill_name("Python数据分析") == "Python数据分析"


def test_normalize_skill_name_replaces_dangerous_chars():
    from market.marketplace.fs import normalize_skill_name

    # 危险字符和空格应替换为下划线，然后合并连续下划线
    assert normalize_skill_name("Word / DOCX") == "Word_DOCX"
    assert normalize_skill_name("skill:name") == "skill_name"
    assert normalize_skill_name("test<file>") == "test_file"
    assert normalize_skill_name("a  b") == "a_b"  # 空格变下划线并合并


def test_normalize_skill_name_rejects_empty():
    from market.marketplace.fs import normalize_skill_name

    with pytest.raises(ValueError, match="cannot be empty"):
        normalize_skill_name("")
    with pytest.raises(ValueError, match="cannot be empty"):
        normalize_skill_name("   ")


def test_normalize_skill_name_rejects_nul():
    from market.marketplace.fs import normalize_skill_name

    with pytest.raises(ValueError, match="NUL"):
        normalize_skill_name("a\x00b")


def test_normalize_skill_name_rejects_dot_dot():
    from market.marketplace.fs import normalize_skill_name

    with pytest.raises(ValueError, match="Invalid skill name"):
        normalize_skill_name("..")
    with pytest.raises(ValueError, match="Invalid skill name"):
        normalize_skill_name(".")


def test_normalize_skill_name_truncates_64():
    from market.marketplace.fs import normalize_skill_name

    long_name = "数据分析" * 20  # 80 个字符
    result = normalize_skill_name(long_name)
    assert len(result) <= 64
    # 截断后应保留中文
    assert result.startswith("数据分析")


def test_normalize_skill_name_all_invalid_returns_error():
    from market.marketplace.fs import normalize_skill_name

    # 全是危险字符，过滤后为空
    with pytest.raises(ValueError, match="only invalid characters"):
        normalize_skill_name("///:::")


# ========== _validate_skill_name_segment 测试 ==========


def test_validate_skill_name_segment_allows_chinese():
    from market.marketplace.fs import _validate_skill_name_segment

    # 中文名应通过校验
    _validate_skill_name_segment("数据分析")
    _validate_skill_name_segment("技能_v1")


def test_validate_skill_name_segment_rejects_nul():
    from market.marketplace.fs import _validate_skill_name_segment

    with pytest.raises(ValueError, match="NUL"):
        _validate_skill_name_segment("a\x00b")


def test_validate_skill_name_segment_rejects_path_separators():
    from market.marketplace.fs import _validate_skill_name_segment

    with pytest.raises(ValueError, match="unsafe"):
        _validate_skill_name_segment("a/b")
    with pytest.raises(ValueError, match="unsafe"):
        _validate_skill_name_segment("a\\b")


# ========== _validate_path_segment 系统标识符测试 ==========


def test_validate_path_segment_still_rejects_chinese_for_system_ids(tmp_path):
    from market.marketplace.fs import get_marketplace_dir

    # source_id 应拒绝中文
    with pytest.raises(ValueError):
        get_marketplace_dir(tmp_path, "数据分析")

    # source_id 应拒绝特殊字符
    with pytest.raises(ValueError):
        get_marketplace_dir(tmp_path, "source-id with spaces")


# ========== copy_skill_to_user 中文目录名测试 ==========


def test_copy_skill_to_user_with_chinese_name(tmp_path):
    from market.marketplace.fs import (
        copy_skill_to_user,
        get_skill_dir,
        get_user_skills_dir,
    )

    # Setup source skill
    src_dir = get_skill_dir(tmp_path / "market", "src_a", "item-cn")
    src_dir.mkdir(parents=True)
    (src_dir / "SKILL.md").write_text("# 数据分析技能", encoding="utf-8")
    (src_dir / "skill.json").write_text(
        json.dumps({"name": "数据分析", "description": "测试技能"}),
        encoding="utf-8",
    )
    # Copy 使用中文目录名
    result = copy_skill_to_user(
        tmp_path / "market",
        "src_a",
        "item-cn",
        tmp_path / "swe",
        "user1",
        "数据分析",  # 中文目录名
        "数据分析",  # 原始名称
        "测试技能",
        "admin1",
        "1.0.0",
    )
    assert result["status"] == "distributed"
    dst_dir = (
        get_user_skills_dir(tmp_path / "swe", "user1", source_id="src_a")
        / "数据分析"
    )
    assert dst_dir.exists()
    assert (dst_dir / "SKILL.md").read_text(
        encoding="utf-8",
    ) == "# 数据分析技能"
    assert not (dst_dir / "skill.json").exists()
    assert result["metadata"] == {
        "name": "数据分析",
        "description": "测试技能",
        "distributed_by": "admin1",
        "received_version": "1.0.0",
    }


# ========== created_at 时间字段测试 ==========


def test_copy_skill_to_user_preserves_created_at_on_redistribute(tmp_path):
    """重复分发时应通过返回 metadata 保留原有 created_at 时间戳."""
    from market.marketplace.fs import (
        copy_skill_to_user,
        get_skill_dir,
        get_user_skill_manifest_path,
        get_user_skills_dir,
    )

    # Setup: 创建市场技能、旧目录和已有 manifest
    src_dir = get_skill_dir(
        tmp_path / "marketplace",
        "test_source",
        "test_item",
    )
    src_dir.mkdir(parents=True)
    (src_dir / "SKILL.md").write_text("# Test Skill", encoding="utf-8")
    skill_json = {"name": "Test Skill", "description": "A test skill"}
    (src_dir / "skill.json").write_text(
        json.dumps(skill_json, ensure_ascii=False),
        encoding="utf-8",
    )

    swe_root = tmp_path / "swe"
    user_id = "test_user"
    dst_dir = (
        get_user_skills_dir(swe_root, user_id, source_id="test_source")
        / "test_skill"
    )
    dst_dir.mkdir(parents=True)
    (dst_dir / "SKILL.md").write_text("# Old Skill", encoding="utf-8")

    first_created_at = "2025-05-14T10:00:00+00:00"
    manifest_path = get_user_skill_manifest_path(
        swe_root,
        user_id,
        source_id="test_source",
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-skill-manifest.v1",
                "version": 1,
                "skills": {
                    "test_skill": {
                        "source": "marketplace:test_item",
                        "created_at": first_created_at,
                    },
                },
            },
        ),
        encoding="utf-8",
    )

    result2 = copy_skill_to_user(
        marketplace_root=tmp_path / "marketplace",
        source_id="test_source",
        item_id="test_item",
        swe_root=swe_root,
        user_id=user_id,
        skill_name="test_skill",
        original_name="Test Skill",
        description="A test skill",
        distributed_by="admin",
        version="1.0.0",
    )
    assert result2["status"] == "distributed"
    assert (dst_dir / "SKILL.md").read_text() == "# Test Skill"
    assert result2["metadata"]["created_at"] == first_created_at


def test_copy_skill_to_user_returns_distribution_metadata(tmp_path):
    """首次分发时应返回供 manifest 写入的分发元数据."""
    from market.marketplace.fs import (
        copy_skill_to_user,
        get_skill_dir,
        get_user_skills_dir,
    )

    # 创建市场技能目录
    src_dir = get_skill_dir(tmp_path / "market", "test_source", "test_item")
    src_dir.mkdir(parents=True)
    (src_dir / "SKILL.md").write_text("# Test Skill", encoding="utf-8")
    (src_dir / "skill.json").write_text(
        json.dumps({"name": "Test Skill", "description": "A test skill"}),
        encoding="utf-8",
    )

    # 执行分发
    result = copy_skill_to_user(
        marketplace_root=tmp_path / "market",
        source_id="test_source",
        item_id="test_item",
        swe_root=tmp_path / "swe",
        user_id="test_user",
        skill_name="test_skill",
        original_name="Test Skill",
        description="A test skill",
        distributed_by="admin",
        version="1.0.0",
    )
    assert result["status"] == "distributed"

    # 验证用户技能文件
    dst_dir = (
        get_user_skills_dir(
            tmp_path / "swe",
            "test_user",
            source_id="test_source",
        )
        / "test_skill"
    )
    assert (dst_dir / "SKILL.md").read_text() == "# Test Skill"
    assert not (dst_dir / "skill.json").exists()
    assert result["metadata"] == {
        "name": "Test Skill",
        "description": "A test skill",
        "distributed_by": "admin",
        "received_version": "1.0.0",
    }


# ========== 自建技能冲突保护测试 ==========


def test_copy_skill_to_user_skips_customized_skill(tmp_path):
    """目标用户有同名自建技能时，应跳过分发并返回冲突."""
    from market.marketplace.fs import (
        copy_skill_to_user,
        get_skill_dir,
        get_user_skill_manifest_path,
        get_user_skills_dir,
    )

    # 创建市场技能
    src_dir = get_skill_dir(tmp_path / "market", "src_a", "item-1")
    src_dir.mkdir(parents=True)
    (src_dir / "SKILL.md").write_text("# Market Skill", encoding="utf-8")
    (src_dir / "skill.json").write_text(
        json.dumps({"name": "my_skill", "description": "from market"}),
        encoding="utf-8",
    )

    # 目标用户已有同名自建技能
    dst_dir = (
        get_user_skills_dir(tmp_path / "swe", "user1", source_id="src_a")
        / "my_skill"
    )
    dst_dir.mkdir(parents=True)
    (dst_dir / "SKILL.md").write_text("# My Own Skill", encoding="utf-8")
    (dst_dir / "skill.json").write_text(
        json.dumps(
            {
                "name": "my_skill",
                "source": "customized",
                "creator_id": "user1",
            },
        ),
        encoding="utf-8",
    )

    manifest_path = get_user_skill_manifest_path(
        tmp_path / "swe",
        "user1",
        source_id="src_a",
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-skill-manifest.v1",
                "version": 1,
                "skills": {
                    "my_skill": {
                        "source": "customized",
                        "metadata": {
                            "name": "my_skill",
                            "creator_id": "user1",
                        },
                    },
                },
            },
        ),
        encoding="utf-8",
    )

    # 分发应跳过
    result = copy_skill_to_user(
        tmp_path / "market",
        "src_a",
        "item-1",
        tmp_path / "swe",
        "user1",
        "my_skill",
        "my_skill",
        "from market",
        "admin1",
        "1.0.0",
    )
    assert result["status"] == "conflict"
    assert result["reason"] == "customized"

    # 原有文件不应被修改
    assert (dst_dir / "SKILL.md").read_text() == "# My Own Skill"
    data = json.loads((dst_dir / "skill.json").read_text())
    assert data["source"] == "customized"


def test_copy_skill_to_user_overwrites_customized_skill_without_creator_id(
    tmp_path,
):
    """同名 customized 技能缺少 creator_id 时，应允许覆盖."""
    from market.marketplace.fs import (
        copy_skill_to_user,
        get_skill_dir,
        get_user_skill_manifest_path,
        get_user_skills_dir,
    )

    # 创建市场技能
    src_dir = get_skill_dir(tmp_path / "market", "src_a", "item-1")
    src_dir.mkdir(parents=True)
    (src_dir / "SKILL.md").write_text("# Market Skill", encoding="utf-8")
    (src_dir / "skill.json").write_text(
        json.dumps({"name": "my_skill", "description": "from market"}),
        encoding="utf-8",
    )

    # 目标用户已有同名 customized 技能，但 manifest 中缺少 creator_id
    dst_dir = (
        get_user_skills_dir(tmp_path / "swe", "user1", source_id="src_a")
        / "my_skill"
    )
    dst_dir.mkdir(parents=True)
    (dst_dir / "SKILL.md").write_text("# Legacy Skill", encoding="utf-8")
    (dst_dir / "skill.json").write_text(
        json.dumps({"name": "my_skill", "source": "customized"}),
        encoding="utf-8",
    )

    manifest_path = get_user_skill_manifest_path(
        tmp_path / "swe",
        "user1",
        source_id="src_a",
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-skill-manifest.v1",
                "version": 1,
                "skills": {
                    "my_skill": {
                        "source": "customized",
                        "metadata": {
                            "name": "my_skill",
                            "description": "legacy customized",
                        },
                    },
                },
            },
        ),
        encoding="utf-8",
    )

    result = copy_skill_to_user(
        tmp_path / "market",
        "src_a",
        "item-1",
        tmp_path / "swe",
        "user1",
        "my_skill",
        "my_skill",
        "from market",
        "admin1",
        "1.0.0",
    )

    assert result["status"] == "distributed"
    assert (dst_dir / "SKILL.md").read_text() == "# Market Skill"


def test_copy_skill_to_user_overwrites_marketplace_skill(tmp_path):
    """目标用户有同名接收技能时，应覆盖更新."""
    from market.marketplace.fs import (
        copy_skill_to_user,
        get_skill_dir,
        get_user_skill_manifest_path,
        get_user_skills_dir,
    )

    # 创建市场技能（新版本）
    src_dir = get_skill_dir(tmp_path / "market", "src_a", "item-1")
    src_dir.mkdir(parents=True)
    (src_dir / "SKILL.md").write_text("# Market Skill v2", encoding="utf-8")
    (src_dir / "skill.json").write_text(
        json.dumps({"name": "my_skill", "description": "v2"}),
        encoding="utf-8",
    )

    # 目标用户已有旧版接收技能
    dst_dir = (
        get_user_skills_dir(tmp_path / "swe", "user1", source_id="src_a")
        / "my_skill"
    )
    dst_dir.mkdir(parents=True)
    (dst_dir / "SKILL.md").write_text("# Market Skill v1", encoding="utf-8")
    (dst_dir / "skill.json").write_text(
        json.dumps(
            {
                "name": "my_skill",
                "source": "marketplace:old-item",
                "received_version": "1.0.0",
            },
        ),
        encoding="utf-8",
    )

    manifest_path = get_user_skill_manifest_path(
        tmp_path / "swe",
        "user1",
        source_id="src_a",
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-skill-manifest.v1",
                "version": 1,
                "skills": {
                    "my_skill": {
                        "source": "marketplace:old-item",
                        "created_at": "2025-05-14T10:00:00+00:00",
                    },
                },
            },
        ),
        encoding="utf-8",
    )

    # 分发应覆盖
    result = copy_skill_to_user(
        tmp_path / "market",
        "src_a",
        "item-1",
        tmp_path / "swe",
        "user1",
        "my_skill",
        "my_skill",
        "v2",
        "admin1",
        "2.0.0",
    )
    assert result["status"] == "distributed"

    # 文件应被更新
    assert (dst_dir / "SKILL.md").read_text() == "# Market Skill v2"
    assert not (dst_dir / "skill.json").exists()
    assert result["metadata"] == {
        "name": "my_skill",
        "description": "v2",
        "distributed_by": "admin1",
        "received_version": "2.0.0",
        "created_at": "2025-05-14T10:00:00+00:00",
    }


def test_copy_skill_to_user_no_existing_skill(tmp_path):
    """目标用户无同名技能时，正常分发."""
    from market.marketplace.fs import (
        copy_skill_to_user,
        get_skill_dir,
        get_user_skills_dir,
    )

    # 创建市场技能
    src_dir = get_skill_dir(tmp_path / "market", "src_a", "item-1")
    src_dir.mkdir(parents=True)
    (src_dir / "SKILL.md").write_text("# New Skill", encoding="utf-8")
    (src_dir / "skill.json").write_text(
        json.dumps({"name": "new_skill"}),
        encoding="utf-8",
    )

    # 目标用户无同名技能
    result = copy_skill_to_user(
        tmp_path / "market",
        "src_a",
        "item-1",
        tmp_path / "swe",
        "user1",
        "new_skill",
        "new_skill",
        "a new skill",
        "admin1",
        "1.0.0",
    )
    assert result["status"] == "distributed"

    dst_dir = (
        get_user_skills_dir(tmp_path / "swe", "user1", source_id="src_a")
        / "new_skill"
    )
    assert dst_dir.exists()
    assert (dst_dir / "SKILL.md").read_text() == "# New Skill"
    assert not (dst_dir / "skill.json").exists()
    assert result["metadata"] == {
        "name": "new_skill",
        "description": "a new skill",
        "distributed_by": "admin1",
        "received_version": "1.0.0",
    }
