# -*- coding: utf-8 -*-
"""版本管理服务单元测试."""

import json
import pytest
from pathlib import Path
from datetime import datetime, timezone

from market.marketplace.version_service import SkillVersionService
from market.marketplace.version_models import (
    SkillVersion,
    VersionsManifest,
    VersionCompareResult,
)


def _make_version_service(tmp_path: Path) -> SkillVersionService:
    """创建版本服务实例."""
    return SkillVersionService(tmp_path / "market")


def _create_skill_dir(
    tmp_path: Path,
    source_id: str,
    item_id: str,
    skill_md: str = "",
    skill_json: dict = None,
) -> Path:
    """创建技能目录."""
    skill_dir = tmp_path / "market" / source_id / "skills" / item_id
    skill_dir.mkdir(parents=True, exist_ok=True)

    if skill_md:
        (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    if skill_json:
        (skill_dir / "skill.json").write_text(
            json.dumps(skill_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return skill_dir


def test_create_version_snapshot_creates_directory(tmp_path):
    """测试创建版本快照生成目录."""
    svc = _make_version_service(tmp_path)
    skill_md = """---
name: "测试技能"
version: "1.0.0"
description: "测试技能描述"
---
# 测试技能
"""
    skill_dir = _create_skill_dir(
        tmp_path,
        "src_a",
        "item_1",
        skill_md=skill_md,
        skill_json={"name": "测试技能"},
    )

    version = svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="初始版本",
        creator="测试用户",
    )

    assert version.version_id == "1.0.0"
    assert version.is_current
    assert version.is_initial
    assert version.created_by == "测试用户"

    # 验证版本目录存在
    version_dir = (
        tmp_path / "market" / "src_a" / "skill_versions" / "item_1" / "1.0.0"
    )
    assert version_dir.exists()
    assert (version_dir / "SKILL.md").exists()


def test_create_version_snapshot_updates_manifest(tmp_path):
    """测试创建版本快照更新版本清单."""
    svc = _make_version_service(tmp_path)
    skill_md = """---
name: "测试技能"
version: "1.0.0"
---
# 测试技能
"""
    skill_dir = _create_skill_dir(
        tmp_path,
        "src_a",
        "item_1",
        skill_md=skill_md,
    )

    svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="初始版本",
        creator="测试用户",
    )

    # 验证 versions.json 存在
    manifest_path = (
        tmp_path
        / "market"
        / "src_a"
        / "skill_versions"
        / "item_1"
        / "versions.json"
    )
    assert manifest_path.exists()

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(data["versions"]) == 1
    assert data["versions"][0]["version_id"] == "1.0.0"


def test_create_second_version_updates_current_flag(tmp_path):
    """测试创建第二个版本更新 is_current 标识."""
    svc = _make_version_service(tmp_path)

    # 创建第一个版本
    skill_md_v1 = """---
name: "测试技能"
version: "1.0.0"
---
# 测试技能 v1
"""
    skill_dir = _create_skill_dir(
        tmp_path,
        "src_a",
        "item_1",
        skill_md=skill_md_v1,
    )

    svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="初始版本",
        creator="测试用户",
    )

    # 更新 SKILL.md 并创建第二个版本
    skill_md_v2 = """---
name: "测试技能"
version: "1.0.1"
---
# 测试技能 v2
"""
    (skill_dir / "SKILL.md").write_text(skill_md_v2, encoding="utf-8")

    version2 = svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="更新版本",
        creator="测试用户",
    )

    assert version2.version_id == "1.0.1"
    assert version2.is_current
    assert not version2.is_initial

    # 验证第一个版本的 is_current 已更新
    manifest = svc._load_versions_manifest("src_a", "item_1")
    v1 = next(v for v in manifest.versions if v.version_id == "1.0.0")
    assert not v1.is_current


def test_list_versions_returns_sorted_list(tmp_path):
    """测试获取版本列表按时间倒序排列."""
    svc = _make_version_service(tmp_path)

    skill_md_v1 = """---
name: "测试技能"
version: "1.0.0"
---
# v1
"""
    skill_dir = _create_skill_dir(
        tmp_path,
        "src_a",
        "item_1",
        skill_md=skill_md_v1,
    )

    svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="v1",
        creator="user",
    )

    # 创建第二个版本
    skill_md_v2 = """---
name: "测试技能"
version: "1.0.1"
---
# v2
"""
    (skill_dir / "SKILL.md").write_text(skill_md_v2, encoding="utf-8")
    svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="v2",
        creator="user",
    )

    versions = svc.list_versions("src_a", "item_1")

    assert len(versions["versions"]) == 2
    # 最新版本在前
    assert versions["versions"][0]["version_id"] == "1.0.1"
    assert versions["versions"][1]["version_id"] == "1.0.0"


def test_switch_version_copies_files(tmp_path):
    """测试切换版本复制文件."""
    svc = _make_version_service(tmp_path)

    skill_md_v1 = """---
name: "测试技能"
version: "1.0.0"
---
# v1 content
"""
    skill_dir = _create_skill_dir(
        tmp_path,
        "src_a",
        "item_1",
        skill_md=skill_md_v1,
    )

    svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="v1",
        creator="user",
    )

    # 创建第二个版本
    skill_md_v2 = """---
name: "测试技能"
version: "1.0.1"
---
# v2 content
"""
    (skill_dir / "SKILL.md").write_text(skill_md_v2, encoding="utf-8")
    svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="v2",
        creator="user",
    )

    # 切换回 v1
    result = svc.switch_version(
        source_id="src_a",
        item_id="item_1",
        target_version_id="1.0.0",
        current_skill_dir=skill_dir,
    )

    assert result.success
    assert result.previous_version == "1.0.1"
    assert result.current_version == "1.0.0"

    # 验证文件已切换
    content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "v1 content" in content

    # 验证 is_current 标识已更新
    manifest = svc._load_versions_manifest("src_a", "item_1")
    v1 = next(v for v in manifest.versions if v.version_id == "1.0.0")
    assert v1.is_current


def test_compare_versions_computes_diff(tmp_path):
    """测试版本比对计算差异."""
    svc = _make_version_service(tmp_path)

    skill_md_v1 = """---
name: "测试技能"
version: "1.0.0"
---
# v1

line 1
line 2
"""
    skill_dir = _create_skill_dir(
        tmp_path,
        "src_a",
        "item_1",
        skill_md=skill_md_v1,
    )

    svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="v1",
        creator="user",
    )

    # 创建第二个版本（有差异）
    skill_md_v2 = """---
name: "测试技能"
version: "1.0.1"
---
# v1

line 1
line 2 modified
line 3 added
"""
    (skill_dir / "SKILL.md").write_text(skill_md_v2, encoding="utf-8")
    svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="v2",
        creator="user",
    )

    result = svc.compare_versions(
        source_id="src_a",
        item_id="item_1",
        base_version_id="1.0.0",
        target_version_id="1.0.1",
    )

    assert result.base_version == "1.0.0"
    assert result.target_version == "1.0.1"
    assert result.stats.changed_files >= 1
    assert result.stats.added_lines >= 1
    assert result.stats.deleted_lines >= 1


def test_delete_version_removes_directory(tmp_path):
    """测试删除版本移除目录."""
    svc = _make_version_service(tmp_path)

    skill_md_v1 = """---
name: "测试技能"
version: "1.0.0"
---
# v1
"""
    skill_dir = _create_skill_dir(
        tmp_path,
        "src_a",
        "item_1",
        skill_md=skill_md_v1,
    )

    svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="v1",
        creator="user",
    )

    # 创建第二个版本
    skill_md_v2 = """---
name: "测试技能"
version: "1.0.1"
---
# v2
"""
    (skill_dir / "SKILL.md").write_text(skill_md_v2, encoding="utf-8")
    svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="v2",
        creator="user",
    )

    # 删除 v1（非当前、非初始）
    # 先将 v1 设为非初始（模拟有更早版本）
    manifest = svc._load_versions_manifest("src_a", "item_1")
    for v in manifest.versions:
        if v.version_id == "1.0.0":
            v.is_initial = False
    svc._save_versions_manifest("src_a", "item_1", manifest)

    result = svc.delete_version(
        source_id="src_a",
        item_id="item_1",
        version_id="1.0.0",
    )

    assert result.success
    assert result.deleted_version == "1.0.0"

    # 验证版本目录已删除
    version_dir = (
        tmp_path / "market" / "src_a" / "skill_versions" / "item_1" / "1.0.0"
    )
    assert not version_dir.exists()


def test_delete_current_version_fails(tmp_path):
    """测试删除当前版本失败."""
    svc = _make_version_service(tmp_path)

    skill_md = """---
name: "测试技能"
version: "1.0.0"
---
# v1
"""
    skill_dir = _create_skill_dir(
        tmp_path,
        "src_a",
        "item_1",
        skill_md=skill_md,
    )

    svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="v1",
        creator="user",
    )

    # 删除当前版本（应该失败）
    result = svc.delete_version(
        source_id="src_a",
        item_id="item_1",
        version_id="1.0.0",
    )

    assert not result.success
    assert "current version" in result.message.lower()


def test_delete_initial_version_succeeds_and_reassigns(tmp_path):
    """测试删除初始版本成功，并自动重新分配初始版本."""
    svc = _make_version_service(tmp_path)

    skill_md_v1 = """---
name: "测试技能"
version: "1.0.0"
---
# v1
"""
    skill_dir = _create_skill_dir(
        tmp_path,
        "src_a",
        "item_1",
        skill_md=skill_md_v1,
    )

    svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="v1",
        creator="user",
    )

    # 创建第二个版本，使 v1 成为初始版本
    skill_md_v2 = """---
name: "测试技能"
version: "1.0.1"
---
# v2
"""
    (skill_dir / "SKILL.md").write_text(skill_md_v2, encoding="utf-8")
    svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="v2",
        creator="user",
    )

    # 删除初始版本 v1（应该成功）
    result = svc.delete_version(
        source_id="src_a",
        item_id="item_1",
        version_id="1.0.0",
    )

    assert result.success
    assert result.deleted_version == "1.0.0"

    # 验证版本目录已删除
    version_dir = (
        tmp_path / "market" / "src_a" / "skill_versions" / "item_1" / "1.0.0"
    )
    assert not version_dir.exists()

    # 验证新的初始版本是 v2
    manifest = svc._load_versions_manifest("src_a", "item_1")
    v2 = next(v for v in manifest.versions if v.version_id == "1.0.1")
    assert v2.is_initial


def test_generate_timestamp_version_when_no_version_in_skill_md(tmp_path):
    """测试 SKILL.md 无版本号时生成时间戳格式."""
    svc = _make_version_service(tmp_path)

    skill_md = """---
name: "测试技能"
---
# 测试技能
"""
    skill_dir = _create_skill_dir(
        tmp_path,
        "src_a",
        "item_1",
        skill_md=skill_md,
    )

    # 测试无 current_market_version 时，默认使用 1.0.0
    version = svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="无版本号",
        creator="user",
    )

    # 版本号应默认为 1.0.0
    assert version.version_id == "1.0.0"


def test_version_auto_bump_when_no_version_in_skill_md(tmp_path):
    """测试 SKILL.md 无版本号时，使用传入的版本号."""
    svc = _make_version_service(tmp_path)

    skill_md = """---
name: "测试技能"
---
# 测试技能
"""
    skill_dir = _create_skill_dir(
        tmp_path,
        "src_a",
        "item_2",
        skill_md=skill_md,
    )

    # 传入 current_market_version=1.0.8，无版本历史时应直接使用
    version = svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_2",
        skill_dir=skill_dir,
        description="无版本号使用传入版本",
        creator="user",
        current_market_version="1.0.8",
    )

    # 版本号应直接使用传入的版本号
    assert version.version_id == "1.0.8"


def test_version_bump_from_history(tmp_path):
    """测试版本历史存在时，接着最后版本递增."""
    svc = _make_version_service(tmp_path)

    skill_md = """---
name: "测试技能"
---
# 测试技能
"""
    skill_dir = _create_skill_dir(
        tmp_path,
        "src_a",
        "item_3",
        skill_md=skill_md,
    )

    # 先创建一个版本 1.0.5
    svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_3",
        skill_dir=skill_dir,
        description="初始版本",
        creator="user",
        current_market_version="1.0.5",
    )

    # 再次创建版本，SKILL.md 无版本号时，应接着历史版本递增
    version2 = svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_3",
        skill_dir=skill_dir,
        description="递增版本",
        creator="user",
    )

    # 版本号应递增为 1.0.6（接着历史版本 1.0.5）
    assert version2.version_id == "1.0.6"


def test_version_new_skill_starts_from_1_0_0(tmp_path):
    """测试新技能（无版本历史）从 1.0.0 开始."""
    svc = _make_version_service(tmp_path)

    skill_md = """---
name: "新技能"
---
# 新技能
"""
    skill_dir = _create_skill_dir(
        tmp_path,
        "src_a",
        "item_new",
        skill_md=skill_md,
    )

    # 新技能，无版本历史，无 current_market_version
    version = svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_new",
        skill_dir=skill_dir,
        description="新技能",
        creator="user",
    )

    # 版本号应默认为 1.0.0
    assert version.version_id == "1.0.0"


def test_calculate_signature_consistent(tmp_path):
    """测试签名计算一致性."""
    svc = _make_version_service(tmp_path)

    skill_md = """---
name: "测试技能"
version: "1.0.0"
---
# 内容
"""
    skill_dir = _create_skill_dir(
        tmp_path,
        "src_a",
        "item_1",
        skill_md=skill_md,
    )

    sig1 = svc._calculate_signature(skill_dir)
    sig2 = svc._calculate_signature(skill_dir)

    assert sig1 == sig2
    assert len(sig1) == 64  # SHA256 hexdigest


def test_version_detail_includes_file_tree(tmp_path):
    """测试版本详情包含文件树."""
    svc = _make_version_service(tmp_path)

    skill_md = """---
name: "测试技能"
version: "1.0.0"
---
# v1
"""
    skill_dir = _create_skill_dir(
        tmp_path,
        "src_a",
        "item_1",
        skill_md=skill_md,
        skill_json={"name": "测试技能"},
    )

    # 创建子目录
    refs_dir = skill_dir / "references"
    refs_dir.mkdir(exist_ok=True)
    (refs_dir / "template.md").write_text("# template", encoding="utf-8")

    svc.create_version_snapshot(
        source_id="src_a",
        item_id="item_1",
        skill_dir=skill_dir,
        description="v1",
        creator="user",
    )

    detail = svc.get_version_detail("src_a", "item_1", "1.0.0")

    assert "version_info" in detail
    assert "file_tree" in detail
    assert len(detail["file_tree"]) >= 1
