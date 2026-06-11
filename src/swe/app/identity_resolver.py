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

    resolved_name = user_name
    resolved_bbk_id = bbk_id
    normalized_source_id = str(source_id or "").strip() or None
    normalized_tenant_id = str(tenant_id or "").strip() or None
    store = get_tenant_init_source_store()

    if (
        store is not None
        and normalized_tenant_id is not None
        and normalized_source_id is not None
    ):
        tenant_info = await store.get_tenant_source_info(
            normalized_tenant_id,
            normalized_source_id,
        )
        if tenant_info:
            resolved_name = resolved_name or tenant_info.get("tenant_name")
            resolved_bbk_id = resolved_bbk_id or tenant_info.get("bbk_id")

    if (
        allow_remote_lookup
        and normalized_tenant_id is not None
        and (not resolved_name or not resolved_bbk_id)
    ):
        fetched_name, fetched_bbk_id = await _fetch_user_info_for_tenant(
            normalized_tenant_id,
            headers or {"Content-Type": "application/json"},
        )
        resolved_name = resolved_name or fetched_name
        resolved_bbk_id = resolved_bbk_id or fetched_bbk_id

        if (
            store is not None
            and normalized_source_id is not None
            and (fetched_name or fetched_bbk_id)
        ):
            try:
                await store.update_tenant_info(
                    tenant_id=normalized_tenant_id,
                    source_id=normalized_source_id,
                    tenant_name=resolved_name,
                    bbk_id=resolved_bbk_id,
                )
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "Failed to persist resolved identity: tenant=%s source=%s error=%s",
                    normalized_tenant_id,
                    normalized_source_id,
                    exc,
                )

    return ResolvedIdentity(
        user_name=resolved_name,
        bbk_id=resolved_bbk_id,
    )
