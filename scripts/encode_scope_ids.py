#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""根据逻辑 tenant_id 与 source_id 生成 canonical scope ID。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许直接通过 ``python scripts/...`` 运行时导入项目源码。
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# pylint: disable=wrong-import-position
from swe.config.scope_conversion import (
    EncodedScope,
    encode_canonical_scope_id as _encode_canonical_scope_id,
)

# pylint: enable=wrong-import-position


def parse_identity_ids(raw_value: str, field_name: str) -> tuple[str, ...]:
    """解析逗号分隔的租户或来源 ID 输入。"""
    identity_ids = tuple(part.strip() for part in raw_value.split(","))
    if not identity_ids or any(
        not identity_id for identity_id in identity_ids
    ):
        raise ValueError(
            f"Invalid {field_name}: expected comma-separated IDs",
        )
    return identity_ids


def encode_canonical_scope_id(
    tenant_id: str,
    source_id: str,
) -> EncodedScope:
    """把逻辑 tenant/source 编码为 canonical scope ID。"""
    return _encode_canonical_scope_id(tenant_id, source_id)


def _format_encoded_scope(encoded: EncodedScope) -> str:
    """把编码结果格式化为便于人工阅读的文本。"""
    return "\n".join(
        (
            f"tenant_id: {encoded.tenant_id}",
            f"source_id: {encoded.source_id}",
            f"scope_id: {encoded.scope_id}",
        ),
    )


def _resolve_identity_pairs(
    args: argparse.Namespace,
) -> tuple[tuple[str, str], ...]:
    """根据单个或批量参数解析待编码的 tenant/source 组合。"""
    single_provided = args.tenant_id is not None or args.source_id is not None
    batch_provided = args.tenant_ids is not None or args.source_ids is not None

    if single_provided == batch_provided:
        raise ValueError(
            "Expected either --tenant-id/--source-id "
            "or --tenant-ids/--source-ids",
        )
    if single_provided:
        if args.tenant_id is None or args.source_id is None:
            raise ValueError(
                "--tenant-id and --source-id must be used together",
            )
        return ((args.tenant_id, args.source_id),)

    if args.tenant_ids is None or args.source_ids is None:
        raise ValueError("--tenant-ids and --source-ids must be used together")

    tenant_ids = parse_identity_ids(args.tenant_ids, "tenant_ids")
    source_ids = parse_identity_ids(args.source_ids, "source_ids")
    if len(tenant_ids) != len(source_ids):
        raise ValueError("tenant_ids and source_ids must have the same length")
    return tuple(zip(tenant_ids, source_ids))


def main() -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(
        description="根据 tenant_id 和 source_id 生成 canonical scope ID",
    )
    parser.add_argument("--tenant-id", help="单个 tenant_id")
    parser.add_argument("--source-id", help="单个 source_id")
    parser.add_argument("--tenant-ids", help="逗号分隔的 tenant_id 列表")
    parser.add_argument("--source-ids", help="逗号分隔的 source_id 列表")
    args = parser.parse_args()

    try:
        identity_pairs = _resolve_identity_pairs(args)
        encoded_scopes = tuple(
            encode_canonical_scope_id(tenant_id, source_id)
            for tenant_id, source_id in identity_pairs
        )
    except ValueError as exc:
        parser.error(str(exc))

    print("\n\n".join(_format_encoded_scope(item) for item in encoded_scopes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
