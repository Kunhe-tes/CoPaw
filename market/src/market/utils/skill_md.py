# -*- coding: utf-8 -*-
"""SKILL.md frontmatter 解析工具.

统一替代散落在 service.py / version_service.py / skills_market.py /
skills_browse.py / skill_versions.py 的多个手写 line parser。

实现基于 python-frontmatter 包，与 swe 侧 skills_manager.py 保持一致的解析方式
（仅对 market 内部生效；swe 侧本次不改）。
"""

from __future__ import annotations

from typing import Any, Dict

import frontmatter

from .version import normalize_version


def parse_frontmatter(md_content: str) -> Dict[str, Any]:
    """解析 SKILL.md frontmatter，返回 metadata dict（无 frontmatter 时返回空 dict）."""
    if not md_content:
        return {}
    try:
        post = frontmatter.loads(md_content)
    except Exception:  # pylint: disable=broad-except
        return {}
    return dict(post.metadata or {})


def extract_version(md_content: str) -> str:
    """提取 frontmatter 中的 version 字段，去除 v 前缀与引号；不存在则返回空串.

    优先级：顶层 version > metadata.version。
    （swe 侧 skills_manager._extract_version 还会回退 metadata.builtin_skill_version，
    但 market 侧本次不引入该字段——保持纯 version 语义。）
    """
    fm = parse_frontmatter(md_content)
    raw = fm.get("version", "")
    if isinstance(raw, (int, float)):
        raw = str(raw)
    if not isinstance(raw, str):
        return ""
    return normalize_version(raw)


def extract_metadata(md_content: str) -> Dict[str, str]:
    """提取常用元数据字段，缺失字段返回空串.

    Returns:
        包含 name / description / version / chinese_name 的 dict。
    """
    fm = parse_frontmatter(md_content)

    def _str(key: str) -> str:
        val = fm.get(key, "")
        if isinstance(val, (int, float)):
            return str(val)
        return val if isinstance(val, str) else ""

    return {
        "name": _str("name"),
        "description": _str("description"),
        "version": extract_version(md_content),
        "chinese_name": _str("chinese_name"),
    }
