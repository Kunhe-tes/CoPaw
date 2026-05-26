# -*- coding: utf-8 -*-
"""Scope ID 解码工具。

用于将加密后的 scope_id 解码还原为原始 tenant_id 和 source_id。

scope_id 格式：base64(tenant_id).base64(source_id)
例如："5LqM5Li9.cnVpY2U" 解码后为 ("张三", "ruice")
"""

import base64
import re
from typing import Optional, Tuple

# Base64 URL-safe 编码的正则模式（不含填充符）
_BASE64_URLSAFE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def is_encoded_scope_id(value: str) -> bool:
    """判断字符串是否为加密后的 scope_id 格式。

    加密后的 scope_id 特征：
    - 包含一个 "." 分隔符
    - "." 前后两部分都是 base64 url-safe 编码字符串

    Args:
        value: 待判断的字符串

    Returns:
        True 如果是加密后的 scope_id 格式
    """
    if not value or "." not in value:
        return False

    parts = value.split(".")
    if len(parts) != 2:
        return False

    # 检查两部分是否都是有效的 base64 url-safe 字符串
    tenant_part, source_part = parts
    if not tenant_part or not source_part:
        return False

    # base64 url-safe 字符集：A-Za-z0-9_-
    return bool(
        _BASE64_URLSAFE_PATTERN.match(tenant_part)
        and _BASE64_URLSAFE_PATTERN.match(source_part),
    )


def _decode_base64_component(encoded: str) -> str:
    """解码单个 base64 url-safe 编码组件。

    Args:
        encoded: base64 url-safe 编码字符串（不含填充符）

    Returns:
        解码后的原始字符串

    Raises:
        ValueError: 如果解码失败
    """
    # 补充填充符（base64 编码长度必须是 4 的倍数）
    padding = "=" * (-len(encoded) % 4)
    try:
        decoded = base64.urlsafe_b64decode(
            (encoded + padding).encode("ascii"),
        ).decode("utf-8")
        return decoded
    except Exception as e:
        raise ValueError(
            f"Failed to decode base64 component: {encoded}",
        ) from e


def decode_scope_id(scope_id: str) -> Tuple[str, str]:
    """将加密后的 scope_id 解码还原为原始 tenant_id 和 source_id。

    Args:
        scope_id: 加密后的 scope_id，格式为 base64(tenant_id).base64(source_id)

    Returns:
        (tenant_id, source_id) 元组

    Raises:
        ValueError: 如果 scope_id 格式无效或解码失败
    """
    if not is_encoded_scope_id(scope_id):
        raise ValueError(f"Invalid scope_id format: {scope_id}")

    parts = scope_id.split(".")
    tenant_id = _decode_base64_component(parts[0])
    source_id = _decode_base64_component(parts[1])

    return tenant_id, source_id


def try_decode_tenant_id(tenant_id: str) -> Tuple[str, Optional[str]]:
    """尝试解码 tenant_id，如果是加密格式则还原。

    Args:
        tenant_id: 可能是原始值或加密后的 scope_id

    Returns:
        (decoded_tenant_id, decoded_source_id) 元组
        - 如果是加密格式，decoded_source_id 为解码后的 source_id
        - 如果不是加密格式，decoded_source_id 为 None，decoded_tenant_id 为原值
    """
    if not tenant_id:
        return tenant_id, None

    if not is_encoded_scope_id(tenant_id):
        return tenant_id, None

    try:
        decoded_tenant_id, decoded_source_id = decode_scope_id(tenant_id)
        return decoded_tenant_id, decoded_source_id
    except ValueError:
        # 解码失败，返回原值
        return tenant_id, None


__all__ = [
    "is_encoded_scope_id",
    "decode_scope_id",
    "try_decode_tenant_id",
]
