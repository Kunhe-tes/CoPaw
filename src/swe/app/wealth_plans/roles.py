# -*- coding: utf-8 -*-
"""财富工作台的服务端角色解析与数据可见范围。

岗位编号 → 角色映射必须与前端 console/src/pages/WealthWorkbench/permissions.ts
的 POSITION_ROLE_MAP 保持一致；未识别岗位按最少权限处理（同客户经理口径）。

规划可见范围统一按 bbk_id 隔离：所有角色只能查看本行规划。
"""

from __future__ import annotations

ROLE_RM = "rm"
ROLE_PRESIDENT = "president"
ROLE_MIDDLE = "middle"
ROLE_UNKNOWN = "unknown"

POSITION_ROLE_MAP: dict[str, str] = {
    "RB0101": ROLE_RM,
    "RB1101": ROLE_PRESIDENT,
    "RB0306": ROLE_PRESIDENT,
    "RB0301": ROLE_MIDDLE,
    "RB0305": ROLE_MIDDLE,
}


def resolve_role(position_id: str | None) -> str:
    """按岗位编号解析角色；缺失或未命中返回 unknown（最少权限）。"""
    if not position_id:
        return ROLE_UNKNOWN
    return POSITION_ROLE_MAP.get(position_id, ROLE_UNKNOWN)
