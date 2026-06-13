# -*- coding: utf-8 -*-
"""身份信息补齐辅助工具。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .routers.user_info import _fetch_user_info_for_tenant
from .workspace.tenant_init_source_store import get_tenant_init_source_store

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedIdentity:
    """封装补齐后的身份信息。"""

    user_name: str | None
    bbk_id: str | None


def _normalize_identity_value(value: str | None) -> str | None:
    """归一化身份字段，空白字符串统一视为 None。"""
    return str(value or "").strip() or None


async def _load_identity_from_store(
    *,
    store,
    tenant_id: str | None,
    source_id: str | None,
    user_name: str | None,
    bbk_id: str | None,
) -> ResolvedIdentity:
    """优先从本地映射表补齐身份字段。"""
    resolved_name = user_name
    resolved_bbk_id = bbk_id

    if store is None or tenant_id is None or source_id is None:
        return ResolvedIdentity(resolved_name, resolved_bbk_id)

    tenant_info = await store.get_tenant_source_info(tenant_id, source_id)
    if tenant_info:
        resolved_name = resolved_name or tenant_info.get("tenant_name")
        resolved_bbk_id = resolved_bbk_id or tenant_info.get("bbk_id")

    return ResolvedIdentity(resolved_name, resolved_bbk_id)


async def _persist_remote_identity(
    *,
    store,
    tenant_id: str | None,
    source_id: str | None,
    user_name: str | None,
    bbk_id: str | None,
) -> None:
    """将远端补齐结果回写到本地映射表。"""
    if (
        store is None
        or tenant_id is None
        or source_id is None
        or (not user_name and not bbk_id)
    ):
        return

    try:
        await store.update_tenant_info(
            tenant_id=tenant_id,
            source_id=source_id,
            tenant_name=user_name,
            bbk_id=bbk_id,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "Failed to persist resolved identity: tenant=%s source=%s error=%s",
            tenant_id,
            source_id,
            exc,
        )


async def _load_identity_from_remote(
    *,
    store,
    tenant_id: str | None,
    source_id: str | None,
    user_name: str | None,
    bbk_id: str | None,
    headers: Optional[dict[str, str]],
) -> ResolvedIdentity:
    """从远端接口补齐缺失身份字段，并按需回写本地表。"""
    if tenant_id is None or (user_name and bbk_id):
        return ResolvedIdentity(user_name, bbk_id)

    fetched_name, fetched_bbk_id = await _fetch_user_info_for_tenant(
        tenant_id,
        headers or {"Content-Type": "application/json"},
    )
    resolved_name = user_name or fetched_name
    resolved_bbk_id = bbk_id or fetched_bbk_id
    await _persist_remote_identity(
        store=store,
        tenant_id=tenant_id,
        source_id=source_id,
        user_name=resolved_name,
        bbk_id=resolved_bbk_id,
    )
    return ResolvedIdentity(resolved_name, resolved_bbk_id)


async def resolve_user_identity(
    *,
    tenant_id: str | None,
    source_id: str | None,
    user_name: str | None,
    bbk_id: str | None,
    headers: Optional[dict[str, str]] = None,
    allow_remote_lookup: bool = True,
) -> ResolvedIdentity:
    """补齐用户身份信息。

    优先保留调用方已提供的 user_name / bbk_id，再尝试本地映射表，
    最后按需回退到 USER_INFO_API_URL。
    """
    if user_name and bbk_id:
        return ResolvedIdentity(user_name=user_name, bbk_id=bbk_id)

    normalized_source_id = _normalize_identity_value(source_id)
    normalized_tenant_id = _normalize_identity_value(tenant_id)
    store = get_tenant_init_source_store()
    resolved = await _load_identity_from_store(
        store=store,
        tenant_id=normalized_tenant_id,
        source_id=normalized_source_id,
        user_name=user_name,
        bbk_id=bbk_id,
    )
    if not allow_remote_lookup:
        return resolved

    return await _load_identity_from_remote(
        store=store,
        tenant_id=normalized_tenant_id,
        source_id=normalized_source_id,
        user_name=resolved.user_name,
        bbk_id=resolved.bbk_id,
        headers=headers,
    )
