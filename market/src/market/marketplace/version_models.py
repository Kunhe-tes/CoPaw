# -*- coding: utf-8 -*-
"""技能版本管理数据模型."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class SkillVersion(BaseModel):
    """单个版本信息."""

    version_id: str
    created_at: str  # ISO8601 时间字符串
    created_by: str = ""  # 操作者 ID（按按钮的人，admin 的 X-User-Id）
    created_by_name: str = ""  # 操作者名称
    description: str = ""
    signature: str = ""  # 内容签名（SHA256）
    is_current: bool = False
    is_initial: bool = False
    # 新增：内容来源用户。空串表示无来源（admin 走 zip 上传路径）
    source_user_id: str = ""
    source_user_name: str = ""
    source_user_version: str = ""


class VersionsManifest(BaseModel):
    """版本清单文件结构."""

    skill_name: str = ""
    versions: list[SkillVersion] = Field(default_factory=list)


class VersionDiffStats(BaseModel):
    """变更统计信息."""

    added_lines: int = 0
    deleted_lines: int = 0
    changed_files: int = 0


class VersionDiffFile(BaseModel):
    """单个文件的差异信息."""

    path: str
    added_lines: int = 0
    deleted_lines: int = 0
    diff: str = ""  # Unified diff 格式
    original_content: str = ""  # 基准版本文件内容
    modified_content: str = ""  # 目标版本文件内容


class VersionCompareRequest(BaseModel):
    """版本比对请求."""

    base_version_id: str
    target_version_id: str


class VersionCompareResult(BaseModel):
    """版本比对结果."""

    base_version: str
    target_version: str
    stats: VersionDiffStats
    files: list[VersionDiffFile] = Field(default_factory=list)


class VersionSwitchResult(BaseModel):
    """版本切换结果."""

    success: bool
    previous_version: str = ""
    current_version: str = ""
    message: str = ""


class VersionDeleteResult(BaseModel):
    """版本删除结果."""

    success: bool
    deleted_version: str = ""
    message: str = ""


class MCPVersion(BaseModel):
    """单个 MCP 版本信息（与 SkillVersion 字段对齐）."""

    version_id: str
    created_at: str
    created_by: str = ""
    created_by_name: str = ""
    description: str = ""
    signature: str = ""  # SHA256(canonical_json(mcp.json))
    is_current: bool = False
    is_initial: bool = False
    source_user_id: str = ""
    source_user_name: str = ""
    source_user_version: str = ""


class MCPVersionsManifest(BaseModel):
    """MCP 版本清单文件结构."""

    client_key: str = ""
    name: str = ""
    versions: list[MCPVersion] = Field(default_factory=list)
