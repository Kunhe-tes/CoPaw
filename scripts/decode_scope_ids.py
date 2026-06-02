#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""反解当前 canonical scope ID，输出逻辑 tenant_id 与 source_id。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许直接通过 ``python scripts/...`` 运行时导入项目源码。
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# pylint: disable=wrong-import-position
from swe.config.scope_conversion import (
    DecodedScope,
    decode_canonical_scope_id as _decode_canonical_scope_id,
)

# pylint: enable=wrong-import-position


def parse_scope_ids(raw_value: str) -> tuple[str, ...]:
    """解析逗号分隔的 scope ID 输入。"""
    scope_ids = tuple(part.strip() for part in raw_value.split(","))
    if not scope_ids or any(not scope_id for scope_id in scope_ids):
        raise ValueError("Invalid scope_ids: expected comma-separated IDs")
    return scope_ids


def decode_canonical_scope_id(scope_id: str) -> DecodedScope:
    """仅反解 canonical scope ID，不接受 legacy 前缀格式。"""
    return _decode_canonical_scope_id(scope_id)


def _format_decoded_scope(decoded: DecodedScope) -> str:
    """把反解结果格式化为便于人工阅读的文本。"""
    return "\n".join(
        (
            f"scope_id: {decoded.scope_id}",
            f"tenant_id: {decoded.tenant_id}",
            f"source_id: {decoded.source_id}",
        ),
    )


def main() -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(
        description="反解 canonical scope ID 为 tenant_id 和 source_id",
    )
    scope_group = parser.add_mutually_exclusive_group(required=True)
    scope_group.add_argument("--scope-id", help="单个 canonical scope ID")
    scope_group.add_argument(
        "--scope-ids",
        help="逗号分隔的 canonical scope ID 列表",
    )
    args = parser.parse_args()

    try:
        scope_ids = (
            parse_scope_ids(args.scope_ids)
            if args.scope_ids is not None
            else (args.scope_id,)
        )
        decoded_scopes = tuple(
            decode_canonical_scope_id(scope_id) for scope_id in scope_ids
        )
    except ValueError as exc:
        parser.error(str(exc))

    print("\n\n".join(_format_decoded_scope(item) for item in decoded_scopes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
