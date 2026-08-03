# -*- coding: utf-8 -*-
"""swe_skills 同步核心逻辑.

封装"扫描用户文件系统下的 skills 目录 + 把技能 upsert 到 swe_skills 表"的整套流程，
供以下两处复用：
1. admin 端点 POST /market/admin/skills/init-swe-skills（事后批量补救）
2. 内部端点 POST /market/internal/tenants/{tenant_id}/sync-skills
   （由 src/swe 的 tenant_initializer 在新用户 bootstrap 末尾调用）

失败语义：单个技能写库异常被捕获到 results["errors"]，不影响其他技能的写入。
"""

import json
import logging
from pathlib import Path
from typing import Optional, TypedDict

from .fs import (
    default_workspace_skill_manifest,
    get_workspace_skill_manifest_path,
)

logger = logging.getLogger(__name__)


class SyncResult(TypedDict, total=False):
    """单次 sync 的统计结果."""

    tenant_id: str
    total_workspaces: int
    total_skills: int
    synced: int
    errors: list[dict]
    details: list[dict]


async def sync_tenant_skills(
    tenant_dir: Path,
    registry,
    source_id: Optional[str] = None,
    force: bool = False,
) -> int:
    """扫描 tenant_dir 下的所有 workspace，把 skills 全量 upsert 到 swe_skills。

    给内部端点 /market/internal/tenants/{id}/sync-skills 使用，行为最简：
    返回成功 upsert 的技能数。

    Args:
        tenant_dir: 用户根目录（如 ~/.swe/tenants/alice）
        registry: SkillRegistry 实例
        source_id: 租户 source_id（可选）
        force: 是否强制覆盖 cn_name

    Returns:
        实际 upsert 的技能数量（成功数）
    """
    result = await process_tenant_skills(
        tenant_dir,
        source_id=source_id,
        registry=registry,
        force=force,
        dry_run=False,
    )
    return result["synced"]


async def process_tenant_skills(
    tenant_dir: Path,
    source_id: Optional[str],
    registry,
    force: bool,
    dry_run: bool = False,
    write_manifest_back: bool = True,
) -> SyncResult:
    """处理单个租户目录下的所有技能.

    给 admin 端点 init-swe-skills 使用，支持 dry_run 和 details 统计。

    Args:
        tenant_dir: 用户根目录
        source_id: 租户 source_id
        registry: SkillRegistry
        force: 是否强制重新生成 skill_id / cn_name
        dry_run: 试运行模式，仅统计不写库
        write_manifest_back: 是否把生成的 metadata.skill_id / cn_name 回写到
            用户 skill.json。admin 端点补救老数据时需要，src/swe 主动触发的
            内部同步禁止（src/swe 自己负责写 skill.json，避免与 src/swe
            已写入的字段竞争并污染 per-user skill_id）。

    Returns:
        SyncResult 统计
    """
    from ..runtime.context import decode_scope_id

    dir_name = tenant_dir.name
    user_id = dir_name

    if dir_name.startswith("default_"):
        user_id = "default"
    elif "." in dir_name:
        try:
            decoded_user_id, _ = decode_scope_id(dir_name)
            user_id = decoded_user_id
        except ValueError:
            pass

    workspace_base = tenant_dir / "workspaces"
    if not workspace_base.exists():
        return {
            "tenant_id": user_id,
            "total_workspaces": 0,
            "total_skills": 0,
            "synced": 0,
            "errors": [],
            "details": [],
        }

    result: SyncResult = {
        "tenant_id": user_id,
        "total_workspaces": 0,
        "total_skills": 0,
        "synced": 0,
        "errors": [],
        "details": [],
    }

    logger.info(
        "处理租户目录: dir_name=%s, user_id=%s, source_id=%s, "
        "dry_run=%s, write_manifest_back=%s",
        dir_name,
        user_id,
        source_id,
        dry_run,
        write_manifest_back,
    )

    for workspace_dir in workspace_base.iterdir():
        if not workspace_dir.is_dir():
            continue
        result["total_workspaces"] += 1
        await _process_workspace_skills(
            workspace_dir,
            user_id,
            source_id,
            registry,
            force,
            dry_run,
            write_manifest_back,
            result,
        )

    return result


async def _process_workspace_skills(
    workspace_dir: Path,
    user_id: str,
    source_id: Optional[str],
    registry,
    force: bool,
    dry_run: bool,
    write_manifest_back: bool,
    result: SyncResult,
) -> None:
    """处理单个 workspace 下的所有技能."""
    skills_dir = workspace_dir / "skills"
    manifest_path = get_workspace_skill_manifest_path(workspace_dir)

    if not skills_dir.exists():
        return

    logger.info(
        "读取 workspace manifest: user_id=%s, workspace=%s, path=%s",
        user_id,
        workspace_dir.name,
        manifest_path,
    )

    manifest, error = _read_workspace_manifest(manifest_path)
    if error:
        result["errors"].append(
            {
                "tenant_id": user_id,
                "error": f"workspace manifest 解析失败: {error}",
            },
        )
        return

    skills_dict = manifest.get("skills", {})

    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        await _process_single_skill(
            skill_dir,
            user_id,
            source_id,
            skills_dict,
            registry,
            force,
            dry_run,
            result,
        )

    # 保存 manifest（admin 端点补救老数据时需要；内部同步显式传 False 跳过）
    if not dry_run and write_manifest_back and skills_dict:
        manifest["skills"] = skills_dict
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


async def _process_single_skill(
    skill_dir: Path,
    user_id: str,
    source_id: Optional[str],
    skills_dict: dict,
    registry,
    force: bool,
    dry_run: bool,
    result: SyncResult,
) -> None:
    """处理单个技能."""
    skill_name = skill_dir.name
    result["total_skills"] += 1

    entry = skills_dict.get(skill_name, {})
    skill_id, cn_name = _extract_skill_fields(
        skill_dir,
        entry,
        skill_name,
        user_id,
        source_id,
        force,
    )

    _update_skill_entry(skills_dict, skill_name, skill_id, cn_name, entry)

    metadata = entry.get("metadata", {})
    if not dry_run:
        error = await _upsert_skill_to_db(
            registry,
            skill_id,
            skill_name,
            cn_name,
            user_id,
            source_id,
            entry,
            metadata,
        )
        if error:
            result["errors"].append(
                {
                    "tenant_id": user_id,
                    "skill_name": skill_name,
                    "error": f"数据库写入失败: {error}",
                },
            )
        else:
            result["synced"] += 1

    result["details"].append(
        {
            "tenant_id": user_id,
            "skill_name": skill_name,
            "skill_id": skill_id,
            "cn_name": cn_name,
            "source": entry.get("source", "customized"),
        },
    )

    logger.debug(
        "技能 %s (user_id=%s): skill_id=%s, cn_name=%s",
        skill_name,
        user_id,
        skill_id,
        cn_name,
    )


def _read_workspace_manifest(manifest_path: Path) -> tuple[dict, str | None]:
    """读取 workspace manifest，返回 (manifest, error)."""
    if not manifest_path.exists():
        return default_workspace_skill_manifest(), None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as e:
        return {}, str(e)


def _extract_skill_fields(
    skill_dir: Path,
    entry: dict,
    skill_name: str,
    user_id: str,
    source_id: Optional[str],
    force: bool,
) -> tuple[str, str]:
    """提取技能的 skill_id 和 cn_name."""
    from ..utils.skill_md import extract_skill_id, extract_cn_name_from_title

    metadata = entry.get("metadata", {})
    skill_source = entry.get("source", "customized")

    skill_md_path = skill_dir / "SKILL.md"
    md_content = ""
    if skill_md_path.exists():
        md_content = skill_md_path.read_text(encoding="utf-8")

    if skill_source == "customized":
        skill_id = extract_skill_id(
            md_content,
            skill_source,
            skill_name,
            creator_id=user_id,
        )
    else:
        skill_id = extract_skill_id(
            md_content,
            skill_source,
            skill_name,
            creator_id="",
        )

    logger.debug(
        "生成 skill_id: skill_name=%s, user_id=%s, source=%s, skill_id=%s",
        skill_name,
        user_id,
        skill_source,
        skill_id,
    )

    cn_name = metadata.get("cn_name", "")
    if not cn_name or force:
        if skill_md_path.exists():
            cn_name = extract_cn_name_from_title(md_content)
        if not cn_name:
            cn_name = skill_name

    return skill_id, cn_name


def _update_skill_entry(
    skills_dict: dict,
    skill_name: str,
    skill_id: str,
    cn_name: str,
    entry: dict,
) -> None:
    """更新 entry 中的 metadata 字段."""
    metadata = entry.get("metadata", {})
    metadata["skill_id"] = skill_id
    metadata["cn_name"] = cn_name
    entry["metadata"] = metadata
    skills_dict[skill_name] = entry


async def _upsert_skill_to_db(
    registry,
    skill_id: str,
    skill_name: str,
    cn_name: str,
    tenant_id: str,
    source_id: Optional[str],
    entry: dict,
    metadata: dict,
) -> str | None:
    """写入技能到数据库，返回错误信息或 None."""
    try:
        await registry.upsert_skill_by_name(
            skill_id=skill_id,
            skill_name=skill_name,
            cn_name=cn_name,
            tenant_id=tenant_id,
            tenant_name="",
            bbk_id="",
            source=entry.get("source", "customized"),
            source_id=source_id or "",
            enabled=entry.get("enabled", False),
            description=metadata.get("description", ""),
            version_text=metadata.get("version_text")
            or metadata.get("received_version")
            or "1.0.0",
        )
        return None
    except Exception as e:
        return str(e)
