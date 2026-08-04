# -*- coding: utf-8 -*-
"""HTTP 客户端：bootstrap 完成后调用 market 同步 swe_skills 表。

失败语义：market 调用失败仅记 warning 日志，不抛异常，
以确保 src/swe 的 ensure_bootstrap() 整体成功。
"""

import logging

import httpx

from ...constant import MARKET_INTERNAL_TOKEN, MARKET_INTERNAL_URL

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 5.0


def _market_url() -> str:
    """market 内部端点的 base URL（去掉尾部斜杠）。"""
    return MARKET_INTERNAL_URL.rstrip("/")


def _build_headers() -> dict[str, str]:
    """构造请求头，包含可选的内部 token。"""
    headers: dict[str, str] = {}
    token = MARKET_INTERNAL_TOKEN.strip()
    if token:
        headers["X-Internal-Token"] = token
    return headers


async def sync_skills_to_db(tenant_id: str) -> None:
    """为新初始化的租户触发一次 swe_skills 同步。

    调用 market 内部端点 POST /market/internal/tenants/{tenant_id}/sync-skills。
    任何失败（连接、超时、非 200）仅记 warning，不抛异常。

    Args:
        tenant_id: 用户的 bootstrap_tenant_id
    """
    url = f"{_market_url()}/market/internal/tenants/{tenant_id}/sync-skills"
    headers = _build_headers()

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.post(url, headers=headers)

        if resp.status_code != 200:
            logger.warning(
                "swe_skills 同步失败 status=%d tenant=%s body=%s",
                resp.status_code,
                tenant_id,
                resp.text[:200],
            )
            return

        try:
            body = resp.json()
            synced = body.get("synced", "?")
        except Exception:
            synced = "?"
        logger.info(
            "swe_skills 同步完成 tenant=%s synced=%s",
            tenant_id,
            synced,
        )
    except (httpx.HTTPError, ConnectionError, TimeoutError) as exc:
        logger.warning(
            "swe_skills 同步异常 tenant=%s err=%s（不影响初始化）",
            tenant_id,
            exc,
        )
    except Exception as exc:
        # 兜底捕获任何异常，保证不影响 bootstrap 流程
        logger.warning(
            "swe_skills 同步未知异常 tenant=%s err=%s（不影响初始化）",
            tenant_id,
            exc,
        )
