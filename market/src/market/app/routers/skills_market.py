# -*- coding: utf-8 -*-
"""管理员市场 API."""

import asyncio
import io
import json
import logging
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TypedDict

from fastapi import (
    APIRouter,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)

from ...marketplace.fs import get_skill_dir, _atomic_write_json
from ...marketplace.schemas import (
    DistributeRequest,
    DistributeResponse,
    MarketSkillResponse,
    PublishSkillRequest,
    UploadSkillResponse,
)
from ...marketplace.service import (
    MarketItem,
    SkillNameConflictError,
    SkillVersionConflictError,
    load_index,
    save_index,
)
from ...marketplace.version_service import SkillVersionService
from ..deps import decode_user_name, require_source_id
from .skills_browse import (
    _decode_zip_filename,
    _extract_zip_skills,
    _read_validated_zip_upload,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class _InitUserSkillsResult(TypedDict):
    """init_user_skills 返回结果类型."""

    dry_run: bool
    processed_users: int
    processed_workspaces: int
    processed_skills: int
    created_skill_json: int
    updated_source: int
    skipped_marketplace: int
    errors: list[dict[str, str]]
    details: list[dict[str, str]]


def _require_manager(x_manager: Optional[str]) -> None:
    """验证管理员权限."""
    if x_manager != "true":
        raise HTTPException(status_code=403, detail="Manager access required")


def _parse_skill_metadata(
    skill_dir: Path,
    skill_name: str,
) -> tuple[dict, str, str, str, str]:
    """解析技能元数据.

    Returns:
        (skill_json, skill_md, name, description, version)
    """
    skill_json_path = skill_dir / "skill.json"
    skill_md_path = skill_dir / "SKILL.md"

    skill_json = {}
    skill_md = ""
    name_from_skill = skill_name
    description_from_skill = ""
    version_from_skill = ""

    # 读取 skill.json
    if skill_json_path.exists():
        try:
            skill_json = json.loads(
                skill_json_path.read_text(encoding="utf-8"),
            )
            name_from_skill = skill_json.get("name", skill_name)
            description_from_skill = skill_json.get("description", "")
            version_from_skill = skill_json.get("version", "")
        except json.JSONDecodeError:
            pass

    # 读取 SKILL.md 并解析 frontmatter
    if skill_md_path.exists():
        skill_md = skill_md_path.read_text(encoding="utf-8")
        name_from_skill, description_from_skill, version_from_md = (
            _parse_frontmatter(
                skill_md,
                name_from_skill,
                description_from_skill,
            )
        )
        # SKILL.md 中的 version 优先级更高（与版本历史对齐）
        if version_from_md:
            version_from_skill = version_from_md

    return (
        skill_json,
        skill_md,
        name_from_skill,
        description_from_skill,
        version_from_skill,
    )


def _parse_frontmatter(
    skill_md: str,
    default_name: str,
    default_desc: str,
) -> tuple[str, str, str]:
    """从 SKILL.md 解析 frontmatter（委托共享工具）.

    Returns:
        (name, description, version)
    """
    from ...utils.skill_md import extract_metadata

    meta = extract_metadata(skill_md)
    name = meta["name"] or default_name
    desc = meta["description"] or default_desc
    version = meta["version"]
    return name, desc, version


def _copy_skill_to_market(
    skill_dir: Path,
    market_skill_dir: Path,
    skill_json: dict,  # noqa: ARG001 - 保留参数签名兼容，但不再写入
    skill_md: str,
) -> None:
    """复制技能文件到市场目录.

    覆盖时先清空目标目录，确保旧文件不会残留。
    不再写入 skill.json，元数据从 SKILL.md frontmatter 读取。
    """
    market_skill_dir.mkdir(parents=True, exist_ok=True)

    # 清空目标目录中的旧文件（覆盖场景）
    for existing in market_skill_dir.iterdir():
        if existing.is_dir():
            shutil.rmtree(existing)
        else:
            existing.unlink()

    # 复制 SKILL.md（newline="" 防止 Windows 上 write_text 把 LF 转为 CRLF，
    # 导致与 copytree 路径写入的文件签名不一致，R7 no-op 跨路径失效）
    if skill_md:
        (market_skill_dir / "SKILL.md").write_text(
            skill_md,
            encoding="utf-8",
            newline="",
        )

    # 复制其他文件（排除 skill.json）
    for f in skill_dir.iterdir():
        if f.name not in ("skill.json", "SKILL.md"):
            target = market_skill_dir / f.name
            if f.is_dir():
                shutil.copytree(f, target)
            else:
                shutil.copy2(f, target)


async def _log_publish_operation(
    svc,
    source_id: str,
    user_id: str,
    user_name: str,
    item: MarketItem,
) -> None:
    """记录上架操作日志."""
    if not svc.db.is_connected:
        return

    try:
        await svc.db.execute(
            """
            INSERT INTO swe_marketplace_operation_logs
                (source_id, operator_id, operator_name, operation,
                 item_type, item_id, item_name,
                 target_user_id, target_user_name, target_bbk_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_id,
                user_id,
                user_name,
                "publish",
                "skill",
                item.item_id,
                item.name,
                None,
                None,
                None,
            ),
        )
    except Exception as e:
        logger.warning("Failed to log publish operation: %s", e)


def _create_market_item(
    name: str,
    description: str,
    version: str,
    user_id: str,
    user_name: str,
    category_id: Optional[int],
) -> MarketItem:
    """创建市场条目."""
    now = datetime.now(timezone.utc).isoformat()
    return MarketItem(
        item_id=str(uuid.uuid4()),
        item_type="skill",
        name=name,
        description=description,
        version=version or "1.0.0",
        creator_id=user_id,
        creator_name=user_name,
        category_id=category_id,
        bbk_ids=[],
        status="active",
        created_at=now,
        updated_at=now,
    )


def _process_single_skill(
    skill_dir: Path,
    skill_name: str,
    svc,
    source_id: str,
    user_id: str,
    user_name: str,
    category_id: Optional[int],
    overwrite: bool = False,
) -> tuple[Optional[str], Optional[dict], Optional[str], bool]:
    """处理单个技能的上架逻辑.

    Args:
        overwrite: 是否覆盖同名技能，默认 False（返回冲突）

    Returns:
        (imported_name, conflict_info, parsed_name_for_first, version_unchanged)
    """
    from ...marketplace.service import _bump_patch

    skill_json, skill_md, name, description, version = _parse_skill_metadata(
        skill_dir,
        skill_name,
    )

    # 检查市场是否已存在同名技能
    items = load_index(svc.marketplace_root, source_id)
    existing = next((i for i in items if i.name == name), None)

    # 未显式 overwrite 时返回冲突信息，由前端弹窗让用户确认
    if existing and not overwrite:
        conflict_info = {
            "skill_name": name,
            "suggested_name": name,
            "existing_creator_id": existing.creator_id,
            "existing_creator_name": existing.creator_name,
            "existing_version": existing.version,
        }
        return None, conflict_info, name, False

    version_unchanged = False

    if existing:
        # R4: 同名（已确认覆盖） → 续接到现有条目（无论 creator 是否相同）
        # F1 修复：市场版本号独立于 SKILL.md，始终走 _bump_patch（spec R3）。
        # SKILL.md 中的 version 仅作为 source_user_version 写入快照元数据。
        now = datetime.now(timezone.utc).isoformat()
        existing.created_at = now
        existing.status = "active"
        existing.description = description
        existing.version = _bump_patch(existing.version)
        existing.creator_id = user_id
        existing.creator_name = user_name
        existing.category_id = category_id
        existing.updated_at = now
        item = existing
    else:
        # 创建新市场条目，市场首发版本固定为 1.0.0（不再继承 SKILL.md version）
        item = _create_market_item(
            name,
            description,
            "",  # 让 _create_market_item 内部 fallback 到 1.0.0
            user_id,
            user_name,
            category_id,
        )
        items.append(item)

    # 复制技能文件到市场目录
    market_skill_dir = get_skill_dir(
        svc.marketplace_root,
        source_id,
        item.item_id,
    )
    _copy_skill_to_market(skill_dir, market_skill_dir, skill_json, skill_md)

    # 创建版本快照
    # admin zip 路径：source_user_id="" 表示无来源；source_user_version="v0.0.0"（spec R6）
    version_svc = SkillVersionService(svc.marketplace_root)
    try:
        snapshot = version_svc.create_version_snapshot(
            source_id=source_id,
            item_id=item.item_id,
            skill_dir=market_skill_dir,
            description="",  # 去掉重复的版本号信息
            creator=user_id,
            creator_name=user_name,
            current_market_version=item.version,
            source_user_id="",
            source_user_name="",
            source_user_version="v0.0.0",
        )
        # F2：让 MarketItem.version 严格跟随快照的 version_id（处理 R7 复用历史 id 场景）
        if snapshot.version_id and snapshot.version_id != item.version:
            # 版本被回滚 = R7 no-op（内容未变）
            version_unchanged = True
            item.version = snapshot.version_id
    except Exception as e:
        logger.warning("Failed to create version snapshot: %s", e)

    save_index(svc.marketplace_root, source_id, items)

    return name, None, name, version_unchanged


@router.post(
    "/market/skills/publish-upload",
    response_model=UploadSkillResponse,
    status_code=status.HTTP_201_CREATED,
)
async def publish_skill_upload(
    request: Request,
    file: UploadFile = File(..., description="Skill zip file to publish"),
    category_id: Optional[int] = None,
    overwrite: bool = False,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
):
    """上传 zip 文件上架技能到市场（管理员）.

    Args:
        overwrite: 是否覆盖同名技能，默认 False（返回冲突提示）
    """
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-Id header is required",
        )

    svc = request.app.state.marketplace
    user_name = decode_user_name(x_user_name) or x_user_id

    # 读取并验证 zip 文件
    data = await _read_validated_zip_upload(file)

    # 解压 zip 文件
    tmp_dir, found_skills = await asyncio.to_thread(
        _extract_zip_skills,
        data,
        file.filename,
    )
    if not found_skills:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return UploadSkillResponse(imported=[], count=0, enabled=True)

    imported = []
    conflicts = []
    parsed_name = None
    parsed_description = None
    has_unchanged = False

    try:
        for skill_dir, skill_name in found_skills:
            imported_name, conflict, first_name, version_unchanged = (
                await asyncio.to_thread(
                    _process_single_skill,
                    skill_dir,
                    skill_name,
                    svc,
                    source_id,
                    x_user_id,
                    user_name,
                    category_id,
                    overwrite,  # 传递 overwrite 参数
                )
            )

            if conflict:
                conflicts.append(conflict)
                continue

            if version_unchanged:
                has_unchanged = True

            if imported_name:
                imported.append(imported_name)

                # 记录首次解析的名称和描述
                if parsed_name is None and first_name:
                    skill_json, skill_md, _, desc, _ = _parse_skill_metadata(
                        skill_dir,
                        skill_name,
                    )
                    parsed_name = first_name
                    parsed_description = desc

                # 异步记录操作日志
                item = next(
                    (
                        i
                        for i in load_index(svc.marketplace_root, source_id)
                        if i.name == imported_name
                    ),
                    None,
                )
                if item:
                    await _log_publish_operation(
                        svc,
                        source_id,
                        x_user_id,
                        user_name,
                        item,
                    )
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

    result = UploadSkillResponse(
        imported=imported,
        count=len(imported),
        enabled=True,
        name=parsed_name,
        description=parsed_description,
        version_unchanged=has_unchanged,
    )
    if conflicts:
        result.conflicts = conflicts
    return result


@router.post(
    "/market/skills",
    response_model=MarketSkillResponse,
    status_code=status.HTTP_201_CREATED,
)
async def publish_skill(
    req: PublishSkillRequest,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
):
    """上架技能（管理员）."""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace
    operator_name = ""
    if x_user_name:
        from urllib.parse import unquote

        try:
            operator_name = unquote(x_user_name)
        except Exception:  # pylint: disable=broad-except
            operator_name = x_user_name
    try:
        item, version_unchanged = await svc.publish_skill(
            source_id,
            req,
            operator_id=x_user_id or "",
            operator_name=operator_name,
        )
    except SkillNameConflictError as exc:
        # 同名续接后此分支理论上不会触发；保留为兜底
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "existing_item_id": exc.existing_item_id,
                "existing_name": exc.existing_name,
                "existing_creator_id": exc.existing_creator_id,
                "existing_creator_name": exc.existing_creator_name,
                "existing_version": exc.existing_version,
            },
        ) from exc
    except SkillVersionConflictError as exc:
        # F3 修复：版本快照撞车不再静默吞掉，让前端可见
        raise HTTPException(
            status_code=409,
            detail={
                "code": "VERSION_CONFLICT",
                "message": str(exc),
                "hint": "本次同步内容与已有版本撞车，请稍后重试或联系管理员",
            },
        ) from exc
    return MarketSkillResponse(
        item_id=item.item_id,
        name=item.name,
        description=item.description,
        version=item.version,
        creator_id=item.creator_id,
        creator_name=item.creator_name,
        category_id=item.category_id,
        bbk_ids=item.bbk_ids,
        status=item.status,
        created_at=item.created_at,
        updated_at=item.updated_at,
        version_unchanged=version_unchanged,
    )


@router.delete(
    "/market/skills/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unpublish_skill(
    item_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
):
    """下架技能（管理员）."""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace
    ok = await svc.unpublish_skill(
        source_id,
        item_id,
        operator_id=x_user_id or "",
        operator_name=decode_user_name(x_user_name) or "",
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Skill not found")


@router.delete(
    "/market/skills/{item_id}/delete",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_skill_permanently(
    item_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
):
    """彻底删除技能及其版本历史（管理员）。"""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace
    ok = await svc.delete_market_skill(
        source_id,
        item_id,
        operator_id=x_user_id or "",
        operator_name=decode_user_name(x_user_name) or "",
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Skill not found")


@router.post(
    "/market/skills/{item_id}/distribute",
    response_model=DistributeResponse,
)
async def distribute_skill(
    item_id: str,
    req: DistributeRequest,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
):
    """分发技能（管理员）."""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace
    try:
        result = await svc.distribute_skill(
            source_id,
            item_id,
            operator_id=x_user_id or "",
            operator_name=decode_user_name(x_user_name) or "",
            req=req,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


def _process_user_skill(
    skill_dir: Path,
    skill_name: str,
    user_id: str,
    agent_id: str,
    dry_run: bool,
    results: _InitUserSkillsResult,
) -> None:
    """处理单个技能的初始化逻辑."""
    skill_json_path = skill_dir / "skill.json"

    try:
        if not skill_json_path.exists():
            # 无 skill.json，创建新文件
            skill_data = {
                "schema_version": "workspace-skill.v1",
                "name": skill_name,
                "source": "customized",
                "description": "",
                "version": "1.0.0",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            results["created_skill_json"] += 1
            results["details"].append(
                {
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "skill_name": skill_name,
                    "action": "created",
                },
            )

            if not dry_run:
                _atomic_write_json(skill_json_path, skill_data)
            return

        # 已有 skill.json，检查 source 字段
        try:
            skill_data = json.loads(
                skill_json_path.read_text(encoding="utf-8"),
            )
        except json.JSONDecodeError as e:
            results["errors"].append(
                {
                    "user_id": user_id,
                    "skill_name": skill_name,
                    "error": f"JSON decode error: {e}",
                },
            )
            return

        current_source = skill_data.get("source", "")

        if current_source.startswith("marketplace:"):
            # 已是分发技能，跳过
            results["skipped_marketplace"] += 1
            return

        if current_source == "customized":
            # 已是正确的值，跳过
            return

        # 需要更新 source
        skill_data["source"] = "customized"
        results["updated_source"] += 1
        results["details"].append(
            {
                "user_id": user_id,
                "agent_id": agent_id,
                "skill_name": skill_name,
                "action": "updated",
                "old_source": current_source,
            },
        )

        if not dry_run:
            _atomic_write_json(skill_json_path, skill_data)

    except Exception as e:
        results["errors"].append(
            {
                "user_id": user_id,
                "skill_name": skill_name,
                "error": str(e),
            },
        )


def _process_workspace_skills(
    workspace_dir: Path,
    user_id: str,
    dry_run: bool,
    results: _InitUserSkillsResult,
) -> None:
    """处理单个 workspace 下的所有技能."""
    agent_id = workspace_dir.name
    skills_dir = workspace_dir / "skills"
    if not skills_dir.exists():
        return

    results["processed_workspaces"] += 1

    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_name = skill_dir.name
        results["processed_skills"] += 1
        _process_user_skill(
            skill_dir,
            skill_name,
            user_id,
            agent_id,
            dry_run,
            results,
        )


@router.post(
    "/market/admin/skills/init-user-skills",
)
async def init_user_skills(
    request: Request,
    dry_run: bool = True,
    user_id: str | None = None,
):
    """初始化用户的历史技能数据为「我创建的」.

    处理逻辑：
    1. 遍历 SWE_ROOT 下用户目录（指定 user_id 则仅处理该用户）
    2. 对于每个用户的技能目录：
       - 无 skill.json：创建文件，设置 source=customized
       - 有 skill.json 但 source 为空或非 marketplace:：设置 source=customized
       - 已是 marketplace: 开头：跳过（保持为「我接收的」）

    Args:
        dry_run: True 仅预览变更，不实际写入；False 执行写入
        user_id: 可选，指定要初始化的用户 ID，不传则处理所有用户
    """
    svc = request.app.state.marketplace
    swe_root = svc.swe_root

    results: _InitUserSkillsResult = {
        "dry_run": dry_run,
        "processed_users": 0,
        "processed_workspaces": 0,
        "processed_skills": 0,
        "created_skill_json": 0,
        "updated_source": 0,
        "skipped_marketplace": 0,
        "errors": [],
        "details": [],
    }

    # 遍历用户目录（支持按 user_id 过滤）
    for user_dir in swe_root.iterdir():
        if not user_dir.is_dir():
            continue
        uid = user_dir.name

        # 指定了 user_id 时跳过不匹配的用户
        if user_id and uid != user_id:
            continue

        results["processed_users"] += 1

        workspace_base = user_dir / "workspaces"
        if not workspace_base.exists():
            continue

        for workspace_dir in workspace_base.iterdir():
            if not workspace_dir.is_dir():
                continue
            _process_workspace_skills(workspace_dir, uid, dry_run, results)

    return results


@router.get(
    "/market/skills/{item_id}/distributions",
)
async def get_skill_distributions(
    item_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
):
    """查询技能分发记录（管理员）."""
    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace
    distributions = await svc.get_distributions(source_id, item_id, "skill")
    return distributions


@router.post(
    "/market/skills/recall",
)
async def recall_skill_by_name(
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
) -> dict:
    """按技能名称撤回（管理员）."""
    from ...marketplace.schemas import RecallRequest

    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace

    # 解析请求体
    body = await request.json()
    target_user_ids = body.get("target_user_ids")
    skill_name = body.get("skill_name")
    req = RecallRequest(
        target_user_ids=target_user_ids,
        skill_name=skill_name,
    )

    try:
        result = await svc.recall_skill(
            source_id,
            None,
            operator_id=x_user_id or "",
            operator_name=decode_user_name(x_user_name) or "",
            req=req,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result.model_dump()


@router.post(
    "/market/skills/{item_id}/recall",
)
async def recall_skill(
    item_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
) -> dict:
    """撤回已分发的技能（管理员）."""
    from ...marketplace.schemas import RecallRequest

    source_id = require_source_id(x_source_id)
    _require_manager(x_manager)
    svc = request.app.state.marketplace

    # 解析请求体
    body = await request.json()
    target_user_ids = body.get("target_user_ids")
    force = body.get("force", False)
    req = RecallRequest(
        target_user_ids=target_user_ids,
        force=force,
    )

    try:
        result = await svc.recall_skill(
            source_id,
            item_id,
            operator_id=x_user_id or "",
            operator_name=decode_user_name(x_user_name) or "",
            req=req,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result.model_dump()
