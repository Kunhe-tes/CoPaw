# -*- coding: utf-8 -*-
"""版本号操作工具.

统一替代散落在 service.py / version_service.py / skills_browse.py / my_mcp.py
的多个 _bump_patch 实现。
"""

from __future__ import annotations


def bump_patch(version: str) -> str:
    """递增版本号的 patch 部分.

    1.0.0 → 1.0.1
    1.0.8 → 1.0.9
    1.5   → 1.5.1（两段式补 .1，沿用 service.py 现行行为）
    其他无法解析格式 → '<version>.1'
    """
    parts = version.split(".")
    if len(parts) == 3:
        try:
            parts[2] = str(int(parts[2]) + 1)
            return ".".join(parts)
        except ValueError:
            pass
    return f"{version}.1"


def normalize_version(version: str) -> str:
    """去除前导 v/V 与引号、空白."""
    if not version:
        return ""
    val = version.strip()
    if (val.startswith('"') and val.endswith('"')) or (
        val.startswith("'") and val.endswith("'")
    ):
        val = val[1:-1]
    val = val.strip()
    if val[:1] in ("v", "V"):
        val = val[1:]
    return val
