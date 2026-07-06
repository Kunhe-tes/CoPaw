# -*- coding: utf-8 -*-
"""平台内部的 skill 运行时约束判定。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import frontmatter
from yaml import YAMLError

from .utils.file_handling import read_text_file_with_encoding_fallback


@dataclass(frozen=True)
class SkillRuntimeProfile:
    """平台内部使用的 skill 运行时约束画像。"""

    skill_name: str
    trace_attributable: bool
    has_hook_config: bool
    declared_tools: list[str]
    declared_tool_bootstrap_allowed: bool
    reason: str


def build_skill_runtime_profile(
    skill_dir: Path,
    skill_name: str,
) -> SkillRuntimeProfile:
    """根据目录结构与 frontmatter 生成 skill 运行时画像。"""
    skill_md_path = skill_dir / "SKILL.md"
    content = (
        read_text_file_with_encoding_fallback(skill_md_path)
        if skill_md_path.exists()
        else ""
    )
    post, parse_reason = _load_frontmatter_safely(content)
    metadata = post.get("metadata") or {}
    swe_meta = metadata.get("swe", {}) if isinstance(metadata, dict) else {}
    declared_tools = _extract_uses_tools(swe_meta, metadata)
    has_hook_config = _has_enabled_hook_config(skill_dir)

    declared_tool_bootstrap_allowed, reason = _resolve_runtime_constraints(
        has_hook_config=has_hook_config,
        declared_tools=declared_tools,
    )
    if parse_reason:
        reason = f"{reason}|{parse_reason}"

    return SkillRuntimeProfile(
        skill_name=skill_name,
        trace_attributable=True,
        has_hook_config=has_hook_config,
        declared_tools=declared_tools,
        declared_tool_bootstrap_allowed=declared_tool_bootstrap_allowed,
        reason=reason,
    )


def build_skill_runtime_profiles(
    workspace_dir: Path,
    skill_names: list[str],
) -> dict[str, SkillRuntimeProfile]:
    """批量生成 skill runtime profile。"""
    from .skills_manager import resolve_effective_skill_dir

    profiles: dict[str, SkillRuntimeProfile] = {}
    for skill_name in skill_names:
        skill_dir = resolve_effective_skill_dir(workspace_dir, skill_name)
        if skill_dir is None:
            continue
        profiles[skill_name] = build_skill_runtime_profile(
            skill_dir,
            skill_name,
        )
    return profiles


def _extract_uses_tools(
    swe_meta: object,
    metadata: object,
) -> list[str]:
    """读取 frontmatter 中声明的 uses_tools。"""
    if isinstance(swe_meta, dict):
        uses_tools = swe_meta.get("uses_tools", [])
        if isinstance(uses_tools, list):
            return [str(item) for item in uses_tools if item]
    if isinstance(metadata, dict):
        uses_tools = metadata.get("uses_tools", [])
        if isinstance(uses_tools, list):
            return [str(item) for item in uses_tools if item]
    return []


def _load_frontmatter_safely(
    content: str,
) -> tuple[dict, str]:
    """安全解析 frontmatter，失败时降级为空元数据。"""
    if not content:
        return {}, ""
    try:
        post = frontmatter.loads(content)
        return post, ""
    except (ValueError, TypeError, YAMLError):
        return {}, "frontmatter_parse_failed"


def _has_enabled_hook_config(skill_dir: Path) -> bool:
    """仅当 hooks.json 存在且 enabled=true 时才视为有效 hook 配置。"""
    hook_file = skill_dir / "hooks" / "hooks.json"
    if not hook_file.is_file():
        return False
    try:
        hook_post = frontmatter.loads(
            f"---\n---\n{hook_file.read_text(encoding='utf-8')}",
        )
        payload = hook_post.content if hasattr(hook_post, "content") else ""
    except (OSError, ValueError, TypeError, YAMLError):
        return False

    try:
        import json

        data = json.loads(payload)
    except (ValueError, TypeError):
        return False

    return bool(data.get("enabled"))


def _resolve_runtime_constraints(
    *,
    has_hook_config: bool,
    declared_tools: list[str],
) -> tuple[bool, str]:
    """根据结构化事实生成运行时归因约束。"""
    if has_hook_config and declared_tools:
        return False, "hook_config_disables_declared_tool_bootstrap"
    if has_hook_config:
        return False, "hook_config_disables_declared_tool_bootstrap"
    return True, "declared_tool_bootstrap_allowed"
