# -*- coding: utf-8 -*-
"""用户市场浏览 API 和我的技能 API."""

import asyncio
import io
import json
import logging
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    APIRouter,
    Body,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from pydantic import BaseModel, Field

from ...marketplace.fs import (
    get_user_skills_dir,
    normalize_skill_name,
    _validate_skill_name_segment,
)
from ...marketplace.schemas import (
    BatchOperationRequest,
    BatchOperationResponse,
    FileContentResponse,
    FileTreeNode,
    MarketSkillDetail,
    MarketSkillResponse,
    MySkillItem,
    OperationResponse,
    UploadSkillResponse,
)
from ..deps import decode_user_name, require_source_id

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB
_ALLOWED_ZIP_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
}


async def _read_validated_zip_upload(file: UploadFile) -> bytes:
    """Validate and read uploaded zip file."""
    if file.content_type and file.content_type not in _ALLOWED_ZIP_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Expected a zip file, "
                f"got content-type: {file.content_type}"
            ),
        )

    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File too large ({len(data) // (1024 * 1024)} MB). "
                f"Maximum is {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
            ),
        )
    return data


def _decode_zip_filename(filename: str, info: zipfile.ZipInfo) -> str:
    """Decode zip filename, handling GBK encoding from Windows.

    ZIP file name encoding rules:
    - If flag_bits & 0x800: UTF-8 encoded (Python decodes correctly)
    - Otherwise: platform-specific encoding (often GBK on Chinese Windows)

    Python's zipfile module decodes non-UTF-8 filenames using cp437 by default,
    which causes Chinese characters to become garbled. We need to:
    1. Check if UTF-8 flag is set (already correct)
    2. Otherwise, reverse cp437 decoding and try GBK/UTF-8
    """
    # Check if UTF-8 flag is set (bit 11)
    if info.flag_bits & 0x800:
        return filename

    # Try to recover from cp437 mis-decoding
    try:
        raw = filename.encode("cp437")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return filename

    # Try GBK first (common on Chinese Windows)
    try:
        decoded = raw.decode("gbk")
        # Validate the result is printable
        if decoded.isprintable() or all(
            c.isprintable() or c in "\n\r\t" for c in decoded
        ):
            return decoded
    except UnicodeDecodeError:
        pass

    # Try UTF-8
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass

    return filename


_MAX_UNCOMPRESSED_SIZE = 200 * 1024 * 1024  # 200MB


def _validate_zip_archive(data: bytes) -> zipfile.ZipFile:
    """Validate zip data and return ZipFile object."""
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise ValueError("Uploaded file is not a valid zip archive")
    return zipfile.ZipFile(io.BytesIO(data))


def _check_zip_size(zf: zipfile.ZipFile) -> None:
    """Check uncompressed zip size limit."""
    total = sum(info.file_size for info in zf.infolist())
    if total > _MAX_UNCOMPRESSED_SIZE:
        raise ValueError("Uncompressed zip exceeds 200MB limit")


def _validate_zip_paths(zf: zipfile.ZipFile, tmp_dir: Path) -> None:
    """Zip 路径安全检查：拒绝危险字符，允许 Unicode 目录名。

    只拒绝 Windows/NTFS 真正保留的字符和控制字符，
    中文等 Unicode 目录名在后续步骤会通过 normalize_skill_name 保留原样。
    """
    import re

    root_path = tmp_dir.resolve()
    # Windows/NTFS 保留字符 + 控制字符（禁止用于目录/文件名）
    _UNSAFE_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

    for info in zf.infolist():
        decoded_name = _decode_zip_filename(info.filename, info)
        target = (tmp_dir / decoded_name).resolve()

        # 检查路径遍历
        if not target.is_relative_to(root_path):
            raise ValueError(f"Unsafe path in zip: {info.filename}")

        # 检查目录段是否包含非法字符（仅拒绝真正危险的字符）
        path_parts = decoded_name.split("/")
        for i, part in enumerate(
            path_parts[:-1],
        ):  # 检查所有目录段，不检查最后一段（可能是文件名）
            if part and _UNSAFE_CHARS_RE.search(part):
                raise ValueError(
                    f"Zip 文件中的目录名 '{part}' 包含非法字符（空格、斜杠等）。"
                    "请修改 zip 文件中的目录名。",
                )


def _extract_zip_entries(zf: zipfile.ZipFile, tmp_dir: Path) -> None:
    """Extract zip entries with corrected encoding."""
    for info in zf.infolist():
        decoded_name = _decode_zip_filename(info.filename, info)
        target = tmp_dir / decoded_name

        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(info))


def _find_skill_directories(
    tmp_dir: Path,
    zip_filename: str | None = None,
) -> list[tuple[Path, str]]:
    """Find valid skill directories in extracted path."""
    real_entries = [
        path
        for path in tmp_dir.iterdir()
        if not path.name.startswith(".") and not path.name.startswith("_")
    ]

    # Handle single skill at root
    extract_root = (
        real_entries[0]
        if len(real_entries) == 1 and real_entries[0].is_dir()
        else tmp_dir
    )

    if (extract_root / "SKILL.md").exists():
        skill_name = _resolve_skill_name(extract_root, zip_filename)
        return [(extract_root, skill_name)]

    return [
        (path, _resolve_skill_name(path, zip_filename))
        for path in sorted(extract_root.iterdir())
        if not path.name.startswith(".")
        and not path.name.startswith("_")
        and path.is_dir()
        and (path / "SKILL.md").exists()
    ]


def _extract_zip_skills(
    data: bytes,
    zip_filename: str | None = None,
) -> tuple[Path, list[tuple[Path, str]]]:
    """Extract and validate a skill zip.

    Returns ``(tmp_dir, found_skills)`` where each skill is ``(skill_dir, skill_name)``.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="copaw_myskill_upload_"))

    try:
        zf = _validate_zip_archive(data)
        with zf:
            _check_zip_size(zf)
            _validate_zip_paths(zf, tmp_dir)
            _extract_zip_entries(zf, tmp_dir)

        found = _find_skill_directories(tmp_dir, zip_filename)
        if not found:
            raise ValueError(
                "No valid skills found in uploaded zip (missing SKILL.md)",
            )
        return tmp_dir, found
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def _infer_skill_name_from_zip_filename(filename: str) -> str:
    """从 zip 文件名推导技能名（去掉 .zip 和版本号）。"""
    if not filename:
        return ""
    # 去掉 .zip 后缀
    name = filename.lower()
    if name.endswith(".zip"):
        name = name[:-4]
    # 去掉版本号后缀（如 -1.0.0, -v1.0.0）
    import re

    name = re.sub(r"-v?\d+\.\d+\.\d+$", "", name)
    name = re.sub(r"-v?\d+$", "", name)
    return name or filename


def _resolve_skill_name(
    skill_dir: Path,
    zip_filename: str | None = None,
) -> str:
    """Resolve skill name from SKILL.md frontmatter, zip filename, or directory name."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        # 尝试使用 zip 文件名
        inferred = _infer_skill_name_from_zip_filename(zip_filename or "")
        return inferred or skill_dir.name

    try:
        content = skill_md.read_text(encoding="utf-8")
    except Exception:
        inferred = _infer_skill_name_from_zip_filename(zip_filename or "")
        return inferred or skill_dir.name

    if not content.startswith("---"):
        # 没有 frontmatter，尝试使用 zip 文件名
        inferred = _infer_skill_name_from_zip_filename(zip_filename or "")
        return inferred or skill_dir.name

    # Parse YAML frontmatter
    for line in content.split("\n")[1:]:
        if line.startswith("---"):
            break
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
            if name:
                return name

    # frontmatter 中没有 name 字段，尝试使用 zip 文件名
    inferred = _infer_skill_name_from_zip_filename(zip_filename or "")
    return inferred or skill_dir.name


def _import_skill_dir(
    skill_dir: Path,
    skills_root: Path,
    skill_name: str,
    original_name: str,
    overwrite: bool,
) -> bool:
    """Import a skill directory to the user skills folder.

    Args:
        skill_name: 规范的目录名（normalize 后，保留中文等 Unicode 字符）
        original_name: 原始技能名称（用于 skill.json 的 name 字段）
    """
    # 验证目录名是否合法（允许中文等 Unicode 字符）
    try:
        _validate_skill_name_segment(skill_name)
    except ValueError as e:
        raise ValueError(
            f"技能目录名 '{skill_name}' 包含非法字符: {e}",
        ) from e

    target_dir = skills_root / skill_name
    if target_dir.exists() and not overwrite:
        return False

    if target_dir.exists():
        shutil.rmtree(target_dir)

    shutil.copytree(skill_dir, target_dir)
    return True


def _get_existing_skill_names(skills_dir: Path) -> set[str]:
    """Get set of existing skill directory names."""
    if not skills_dir.exists():
        return set()
    return {p.name for p in skills_dir.iterdir() if p.is_dir()}


def _parse_frontmatter_description(skill_md_path: Path) -> str:
    """从 SKILL.md frontmatter 中提取 description."""
    if not skill_md_path.exists():
        return ""
    try:
        content = skill_md_path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return ""
        end_idx = content.index("---", 3)
        fm_text = content[3:end_idx].strip()
        for line in fm_text.split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip().lower()
                val = val.strip()
                if key == "description":
                    return val
    except (ValueError, OSError):
        pass
    return ""


def _build_skill_metadata(
    skill_dir: Path,
    skill_name: str,
    original_name: str,
) -> dict[str, Any]:
    """构建技能元数据（用于写入 manifest），不再写入 skill.json 文件.

    Args:
        skill_dir: 技能目录
        skill_name: 安全的目录名
        original_name: 原始技能名称（用于前端展示）

    Returns:
        技能元数据字典
    """
    skill_json_path = skill_dir / "skill.json"
    skill_data: dict[str, Any] = {}

    # 读取已有的 skill.json（如果存在）
    if skill_json_path.exists():
        try:
            skill_data = json.loads(
                skill_json_path.read_text(encoding="utf-8"),
            )
        except (json.JSONDecodeError, OSError):
            pass

    # name 字段优先使用用户指定的名称（original_name），其次保留已有名称
    skill_data["name"] = original_name or skill_data.get("name") or skill_name

    # 优先从 skill.json 获取 description，其次从 SKILL.md frontmatter
    if not skill_data.get("description"):
        skill_md_path = skill_dir / "SKILL.md"
        desc_from_md = _parse_frontmatter_description(skill_md_path)
        if desc_from_md:
            skill_data["description"] = desc_from_md
        else:
            skill_data.setdefault("description", "")

    skill_data["source"] = skill_data.get("source", "customized")

    # 时间字段处理
    current_time = datetime.now(timezone.utc).isoformat()
    if not skill_data.get("created_at"):
        skill_data["created_at"] = current_time
    else:
        skill_data["updated_at"] = current_time

    return skill_data


def _process_single_skill(
    skill_dir: Path,
    skills_dir: Path,
    skill_name: str,
    original_name: str,
    existing_names: set[str],
    user_id: str,
    user_name: str,
    bbk_id: str,
    overwrite: bool,
    category_id: int | None,
) -> tuple[bool, dict[str, str] | None, dict[str, Any] | None]:
    """Process single skill import. Returns (imported, conflict_or_none, metadata).

    Args:
        skill_name: 安全的目录名
        original_name: 原始技能名称

    Returns:
        (是否导入成功, 冲突信息, 技能元数据用于写入 manifest)
    """
    if skill_name in existing_names and not overwrite:
        # 递增计数器直到找到不冲突的建议名
        counter = 1
        while True:
            suggested = f"{original_name}_{counter}"
            safe_suggested = normalize_skill_name(suggested)
            if safe_suggested not in existing_names:
                break
            counter += 1
        return (
            False,
            {
                "reason": "already_exists",
                "skill_name": skill_name,
                "original_name": original_name,
                "suggested_name": suggested,
            },
            None,
        )

    if not _import_skill_dir(
        skill_dir,
        skills_dir,
        skill_name,
        original_name,
        overwrite,
    ):
        return False, None, None

    # 构建技能元数据（不再写入 skill.json 文件）
    imported_skill_dir = skills_dir / skill_name
    skill_metadata = _build_skill_metadata(
        imported_skill_dir,
        skill_name,
        original_name,
    )

    # 添加上传者信息到元数据
    skill_metadata["creator_id"] = user_id
    skill_metadata["creator_name"] = user_name
    skill_metadata["bbk_id"] = bbk_id
    if category_id is not None:
        skill_metadata["category_id"] = category_id

    return True, None, skill_metadata


def _import_skill_from_zip(
    skills_dir: Path,
    data: bytes,
    user_id: str,
    user_name: str,
    bbk_id: str,
    overwrite: bool = False,
    target_name: str = "",
    rename_map: dict[str, str] | None = None,
    category_id: int | None = None,
    zip_filename: str | None = None,
) -> dict[str, Any]:
    """Import skill from zip data to user skills directory."""
    imported: list[str] = []
    conflicts: list[dict[str, str]] = []
    skills_metadata: dict[str, dict[str, Any]] = {}  # skill_name -> metadata
    tmp_dir: Path | None = None
    parsed_name: str | None = None
    parsed_description: str | None = None

    try:
        tmp_dir, found_skills = _extract_zip_skills(data, zip_filename)
        existing_names = _get_existing_skill_names(skills_dir)

        for skill_dir, original_name in found_skills:
            # original_name 来自 SKILL.md frontmatter 或 zip 文件名
            # 将原始名称规范化为目录名（保留中文等 Unicode 字符）
            safe_skill_name = normalize_skill_name(original_name)

            # 应用 rename_map 映射（用户手动指定的重命名）
            # 需要传递解析：rename_map 可能包含链式映射
            # 如 {A→B, B→C}，表示最终要将 A 重命名为 C
            if rename_map and original_name in rename_map:
                resolved = original_name
                seen = {resolved}
                while resolved in rename_map:
                    resolved = rename_map[resolved]
                    if resolved in seen:
                        break  # 防止循环引用
                    seen.add(resolved)
                original_name = resolved
                safe_skill_name = normalize_skill_name(original_name)
            elif target_name and len(found_skills) == 1:
                safe_skill_name = normalize_skill_name(target_name.strip())

            success, conflict, metadata = _process_single_skill(
                skill_dir,
                skills_dir,
                safe_skill_name,
                original_name,
                existing_names,
                user_id,
                user_name,
                bbk_id,
                overwrite,
                category_id,
            )

            if conflict:
                conflicts.append(conflict)
                continue

            if success and metadata:
                imported.append(safe_skill_name)
                skills_metadata[safe_skill_name] = metadata
                if parsed_name is None:
                    parsed_name = metadata.get("name")
                    parsed_description = metadata.get("description")

    except zipfile.BadZipFile as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid zip file: {e}",
        ) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

    result = {
        "imported": imported,
        "count": len(imported),
        "name": parsed_name,
        "description": parsed_description,
        "skills_metadata": skills_metadata,  # 返回 metadata 用于写入 manifest
    }
    if conflicts:
        result["conflicts"] = conflicts
    return result


@router.get("/market/skills", response_model=list[MarketSkillResponse])
async def list_skills(
    request: Request,
    category_id: Optional[int] = None,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_bbk_id: Optional[str] = Header(default=None, alias="X-Bbk-Id"),
):
    """浏览市场技能列表（按 source_id + bbk_id 过滤）."""
    source_id = require_source_id(x_source_id)
    user_bbk_id = x_bbk_id or "100"
    svc = request.app.state.marketplace
    return await svc.list_skills(
        source_id,
        user_bbk_id,
        category_id=category_id,
    )


@router.get("/market/skills/mine", response_model=list[MySkillItem])
async def get_my_skills(
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    agent_id: str = "default",
):
    """我创建的技能列表."""
    source_id = require_source_id(x_source_id)
    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-Id header is required",
        )
    svc = request.app.state.marketplace
    all_skills = await svc.get_my_skills(source_id, x_user_id, agent_id)
    return [s for s in all_skills if not s.is_received]


@router.get("/market/skills/received", response_model=list[MySkillItem])
async def get_received_skills(
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    agent_id: str = "default",
):
    """我接收的技能列表."""
    source_id = require_source_id(x_source_id)
    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-Id header is required",
        )
    svc = request.app.state.marketplace
    all_skills = await svc.get_my_skills(source_id, x_user_id, agent_id)
    return [s for s in all_skills if s.is_received]


@router.get("/market/skills/{item_id}", response_model=MarketSkillDetail)
async def get_skill_detail(
    item_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_bbk_id: Optional[str] = Header(default=None, alias="X-Bbk-Id"),
):
    """预览技能详情."""
    source_id = require_source_id(x_source_id)
    user_bbk_id = x_bbk_id or "100"
    svc = request.app.state.marketplace
    detail = await svc.get_skill_detail(source_id, item_id, user_bbk_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return detail


@router.get(
    "/market/skills/{item_id}/files",
    response_model=list[FileTreeNode],
)
async def list_market_skill_files(
    item_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_bbk_id: Optional[str] = Header(default=None, alias="X-Bbk-Id"),
):
    """获取市场技能详情页文件树。"""
    source_id = require_source_id(x_source_id)
    user_bbk_id = x_bbk_id or "100"
    svc = request.app.state.marketplace
    files = svc.list_market_skill_files(source_id, item_id, user_bbk_id)
    if files is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return files


@router.get(
    "/market/skills/{item_id}/files/{file_path:path}",
    response_model=FileContentResponse,
)
async def read_market_skill_file(
    item_id: str,
    file_path: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_bbk_id: Optional[str] = Header(default=None, alias="X-Bbk-Id"),
):
    """读取市场技能详情页文件内容。"""
    source_id = require_source_id(x_source_id)
    user_bbk_id = x_bbk_id or "100"
    svc = request.app.state.marketplace
    content, file_type = svc.read_market_skill_file(
        source_id,
        item_id,
        file_path,
        user_bbk_id,
    )
    if file_type == "binary":
        return FileContentResponse(content="", file_type=file_type)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    return FileContentResponse(content=content, file_type=file_type)


@router.post("/market/skills/upload", response_model=UploadSkillResponse)
async def upload_skill_to_workspace(
    request: Request,
    file: UploadFile = File(..., description="Skill zip file to upload"),
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
    x_bbk_id: Optional[str] = Header(default=None, alias="X-Bbk-Id"),
    enable: bool = True,
    overwrite: bool = False,
    target_name: str = "",
    rename_map: str = "",
    category_id: Optional[int] = None,
):
    """上传技能到工作区，记录 user_id, bbk_id, user_name。可选指定分类。"""
    source_id = require_source_id(x_source_id)
    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-Id header is required",
        )

    # 解析 rename_map JSON
    parsed_rename_map: dict[str, str] = {}
    if rename_map:
        try:
            parsed_rename_map = json.loads(rename_map)
        except json.JSONDecodeError:
            logger.warning("Invalid rename_map JSON: %s", rename_map)

    svc = request.app.state.marketplace
    swe_root = svc.swe_root
    user_name = decode_user_name(x_user_name) or x_user_id
    bbk_id = x_bbk_id or "100"
    agent_id = "default"

    # 通过统一 scope_id 定位用户技能目录，避免跨 source 共享本地状态。
    skills_dir = get_user_skills_dir(swe_root, x_user_id, agent_id, source_id)
    skills_dir.mkdir(parents=True, exist_ok=True)

    # Read and validate zip
    data = await _read_validated_zip_upload(file)

    # Import skill
    result = await asyncio.to_thread(
        _import_skill_from_zip,
        skills_dir,
        data,
        x_user_id,
        user_name,
        bbk_id,
        overwrite=overwrite,
        target_name=target_name,
        rename_map=parsed_rename_map,
        category_id=category_id,
        zip_filename=file.filename,
    )

    # Log upload operation
    imported_skills = result.get("imported") or []
    if svc.db.is_connected and imported_skills:
        try:
            await svc.db.execute(
                """
                INSERT INTO swe_user_item_operation_logs
                    (source_id, user_id, user_name, operation,
                     item_type, item_name)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    source_id,
                    x_user_id,
                    user_name,
                    "upload",
                    "skill",
                    ",".join(imported_skills),
                ),
            )
        except Exception as e:
            logger.warning("Failed to log upload operation: %s", e)

    # 注册技能到 manifest（使用已构建的 metadata）
    if result.get("imported"):
        skills_metadata = result.get("skills_metadata") or {}
        for skill_name in result["imported"]:
            skill_metadata = skills_metadata.get(skill_name) or {}
            svc.register_skill_in_manifest(
                x_user_id,
                skill_name,
                agent_id,
                source_id,
                enabled=enable,
                source="customized",
                extra_metadata=skill_metadata,
            )

    # 移除 skills_metadata，不返回给前端
    result.pop("skills_metadata", None)
    result["enabled"] = enable
    return result


@router.get(
    "/market/skills/mine/{skill_name}/files",
    response_model=list[FileTreeNode],
)
async def list_skill_files(
    skill_name: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    agent_id: str = "default",
):
    """获取技能文件树."""
    source_id = require_source_id(x_source_id)
    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-Id header is required",
        )
    svc = request.app.state.marketplace
    return svc.list_skill_files(x_user_id, skill_name, agent_id, source_id)


@router.get(
    "/market/skills/mine/{skill_name}/files/{file_path:path}",
    response_model=FileContentResponse,
)
async def read_skill_file(
    skill_name: str,
    file_path: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    agent_id: str = "default",
):
    """读取技能文件内容."""
    source_id = require_source_id(x_source_id)
    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-Id header is required",
        )
    svc = request.app.state.marketplace
    content, file_type = svc.read_skill_file(
        x_user_id,
        skill_name,
        file_path,
        agent_id,
        source_id,
    )
    if content is None:
        if file_type == "binary":
            raise HTTPException(
                status_code=400,
                detail="Binary file not supported for preview",
            )
        raise HTTPException(status_code=404, detail="File not found")
    return FileContentResponse(content=content, file_type=file_type)


@router.put(
    "/market/skills/mine/{skill_name}/files/{file_path:path}",
    response_model=OperationResponse,
)
async def save_skill_file(
    skill_name: str,
    file_path: str,
    request: Request,
    content: str = Body(..., embed=True),
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
    agent_id: str = "default",
):
    """保存技能文件内容（仅我创建的技能支持）."""
    source_id = require_source_id(x_source_id)
    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-Id header is required",
        )

    svc = request.app.state.marketplace
    skills = await svc.get_my_skills(source_id, x_user_id, agent_id)
    skill = next((s for s in skills if s.skill_name == skill_name), None)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill.is_received:
        raise HTTPException(
            status_code=403,
            detail="Only created skills can be edited",
        )

    ok = svc.save_skill_file(
        x_user_id,
        skill_name,
        file_path,
        content,
        user_name=decode_user_name(x_user_name),
        agent_id=agent_id,
        source_id=source_id,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save file")

    # Log edit operation
    if svc.db.is_connected:
        try:
            await svc.db.execute(
                """
                INSERT INTO swe_user_item_operation_logs
                    (source_id, user_id, user_name, operation,
                     item_type, item_name)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    source_id,
                    x_user_id,
                    decode_user_name(x_user_name),
                    "edit",
                    "skill",
                    skill_name,
                ),
            )
        except Exception as e:
            logger.warning("Failed to log edit operation: %s", e)

    return OperationResponse(success=True)


@router.delete(
    "/market/skills/mine/{skill_name}",
    response_model=OperationResponse,
)
async def delete_my_skill(
    skill_name: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
    agent_id: str = "default",
):
    """删除技能."""
    source_id = require_source_id(x_source_id)
    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-Id header is required",
        )

    svc = request.app.state.marketplace
    ok = svc.delete_skill(x_user_id, skill_name, agent_id, source_id)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Skill not found or delete failed",
        )

    # Log delete operation
    if svc.db.is_connected:
        try:
            await svc.db.execute(
                """
                INSERT INTO swe_user_item_operation_logs
                    (source_id, user_id, user_name, operation,
                     item_type, item_name)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    source_id,
                    x_user_id,
                    decode_user_name(x_user_name),
                    "delete",
                    "skill",
                    skill_name,
                ),
            )
        except Exception as e:
            logger.warning("Failed to log delete operation: %s", e)

    return OperationResponse(success=True)


@router.post(
    "/market/skills/mine/{skill_name}/enable",
    response_model=OperationResponse,
)
async def enable_my_skill(
    skill_name: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    agent_id: str = "default",
):
    """启用技能（含安全扫描）."""
    source_id = require_source_id(x_source_id)
    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-Id header is required",
        )
    svc = request.app.state.marketplace
    result = await svc.enable_skill(x_user_id, skill_name, agent_id, source_id)
    if not result.get("success"):
        if result.get("reason") == "security_scan_failed":
            raise HTTPException(
                status_code=422,
                detail=result,
            )
        raise HTTPException(
            status_code=404,
            detail=result.get("reason", "Skill not found"),
        )
    return OperationResponse(success=True)


@router.post(
    "/market/skills/mine/{skill_name}/disable",
    response_model=OperationResponse,
)
async def disable_my_skill(
    skill_name: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    agent_id: str = "default",
):
    """禁用技能."""
    source_id = require_source_id(x_source_id)
    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-Id header is required",
        )
    svc = request.app.state.marketplace
    result = await svc.disable_skill(
        x_user_id,
        skill_name,
        agent_id,
        source_id,
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=404,
            detail="Skill not found",
        )
    return OperationResponse(success=True)


@router.post(
    "/market/skills/mine/batch-delete",
    response_model=BatchOperationResponse,
)
async def batch_delete_my_skills(
    body: BatchOperationRequest,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    agent_id: str = "default",
):
    """批量删除技能."""
    source_id = require_source_id(x_source_id)
    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-Id header is required",
        )
    svc = request.app.state.marketplace
    results = await svc.batch_delete_skills(
        x_user_id,
        body.skills,
        agent_id,
        source_id,
    )
    success_count = sum(1 for r in results.values() if r.get("success"))
    return BatchOperationResponse(
        results=results,
        success_count=success_count,
        failed_count=len(body.skills) - success_count,
    )


@router.post(
    "/market/skills/mine/batch-enable",
    response_model=BatchOperationResponse,
)
async def batch_enable_my_skills(
    body: BatchOperationRequest,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    agent_id: str = "default",
):
    """批量启用技能."""
    source_id = require_source_id(x_source_id)
    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-Id header is required",
        )
    svc = request.app.state.marketplace
    results = await svc.batch_enable_skills(
        x_user_id,
        body.skills,
        agent_id,
        source_id,
    )
    success_count = sum(1 for r in results.values() if r.get("success"))
    return BatchOperationResponse(
        results=results,
        success_count=success_count,
        failed_count=len(body.skills) - success_count,
    )


@router.post(
    "/market/skills/mine/batch-disable",
    response_model=BatchOperationResponse,
)
async def batch_disable_my_skills(
    body: BatchOperationRequest,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    agent_id: str = "default",
):
    """批量禁用技能."""
    source_id = require_source_id(x_source_id)
    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-Id header is required",
        )
    svc = request.app.state.marketplace
    results = await svc.batch_disable_skills(
        x_user_id,
        body.skills,
        agent_id,
        source_id,
    )
    success_count = sum(1 for r in results.values() if r.get("success"))
    return BatchOperationResponse(
        results=results,
        success_count=success_count,
        failed_count=len(body.skills) - success_count,
    )


# -----------------------------------------------------------
# 操作日志上报端点
# -----------------------------------------------------------


class OperationLogRequest(BaseModel):
    """操作日志上报请求体。"""

    operation: str = Field(..., description="操作类型: create/edit/delete")
    item_type: str = Field(default="skill", description="条目类型: skill/mcp")
    item_name: str = Field(..., description="条目名称")
    user_name: Optional[str] = Field(default=None, description="用户名称")
    bbk_id: Optional[str] = Field(default=None, description="机构ID")


@router.post("/market/skills/operation-log")
async def log_skill_operation(
    request: Request,
    body: OperationLogRequest,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """上报技能操作日志。

    用于 Agent 通过 skill_creator 创建技能后记录操作日志。
    采用失败忽略策略，写入失败不影响业务。
    """
    source_id = require_source_id(x_source_id)
    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-Id header is required",
        )

    svc = request.app.state.marketplace
    user_name = decode_user_name(body.user_name) or x_user_id

    if svc.db.is_connected:
        try:
            await svc.db.execute(
                """
                INSERT INTO swe_user_item_operation_logs
                    (source_id, user_id, user_name, operation,
                     item_type, item_name)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    source_id,
                    x_user_id,
                    user_name,
                    body.operation,
                    body.item_type,
                    body.item_name,
                ),
            )
        except Exception as e:
            logger.warning("Failed to log operation: %s", e)

    return {"success": True}


class MigrateSkillJsonRequest(BaseModel):
    """迁移 skill.json 字段请求."""

    delete_skill_json: bool = Field(
        default=False,
        description="是否删除技能目录内的 skill.json 文件",
    )


class MigrateSkillJsonResponse(BaseModel):
    """迁移 skill.json 字段响应."""

    migrated: int = Field(description="成功迁移的技能数量")
    skipped: int = Field(
        description="跳过的技能数量（无 skill.json 或无额外字段）",
    )
    errors: list[str] = Field(default_factory=list, description="错误信息列表")


@router.post(
    "/market/skills/migrate-skill-json",
    response_model=MigrateSkillJsonResponse,
)
async def migrate_skill_json_to_manifest(
    request: Request,
    body: MigrateSkillJsonRequest,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    agent_id: str = "default",
):
    """迁移技能目录内 skill.json 字段到 workspace manifest.

    将以下字段从 skills/<技能名>/skill.json 合并到 workspaces/<agent_id>/skill.json:
    - creator_id
    - creator_name
    - bbk_id
    - distributed_by
    - received_version
    - category_id

    Args:
        delete_skill_json: 是否删除技能目录内的 skill.json 文件（默认不删除）
    """
    source_id = require_source_id(x_source_id)
    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-Id header is required",
        )

    svc = request.app.state.marketplace
    result = svc.migrate_skill_json_to_manifest(
        x_user_id,
        agent_id,
        source_id,
        delete_skill_json=body.delete_skill_json,
    )

    return MigrateSkillJsonResponse(
        migrated=result["migrated"],
        skipped=result["skipped"],
        errors=result["errors"],
    )
