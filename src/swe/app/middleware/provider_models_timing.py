# -*- coding: utf-8 -*-
"""Provider models 列表接口的端到端耗时埋点。"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

_MODELS_LIST_PATHS = frozenset(
    {
        "/models",
        "/models/",
        "/api/models",
        "/api/models/",
    },
)


def _is_models_list_request(request: Request) -> bool:
    """判断当前请求是否为 provider 模型列表接口。"""
    return request.method == "GET" and request.url.path in _MODELS_LIST_PATHS


class ProviderModelsTimingMiddleware(BaseHTTPMiddleware):
    """记录 GET /api/models 从业务中间件入口到响应生成的总耗时。"""

    def __init__(self, app: ASGIApp) -> None:
        """初始化 middleware。"""
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """围绕模型列表请求记录端到端耗时。"""
        if not _is_models_list_request(request):
            return await call_next(request)

        started_at = time.perf_counter()
        request.state.provider_models_request_started_at = started_at
        logger.info(
            "provider_models_request_start method=%s path=%s query=%s",
            request.method,
            request.url.path,
            request.url.query,
        )
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            logger.exception(
                "provider_models_request_error path=%s duration_ms=%d "
                "dependency_ms=%s handler_ms=%s after_handler_ms=%s "
                "tenant_id=%s source_id=%s scope_id=%s",
                request.url.path,
                duration_ms,
                getattr(request.state, "provider_manager_dependency_ms", None),
                getattr(request.state, "provider_models_handler_ms", None),
                _elapsed_after_handler_ms(request, duration_ms),
                getattr(request.state, "tenant_id", None),
                getattr(request.state, "source_id", None),
                getattr(request.state, "scope_id", None),
            )
            raise

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            "provider_models_request_done path=%s status_code=%s "
            "duration_ms=%d tenant_id=%s source_id=%s scope_id=%s "
            "dependency_ms=%s dependency_ensure_ms=%s "
            "dependency_get_instance_ms=%s dependency_cache_hit_before=%s "
            "handler_ms=%s after_handler_ms=%s content_length=%s",
            request.url.path,
            response.status_code,
            duration_ms,
            getattr(request.state, "tenant_id", None),
            getattr(request.state, "source_id", None),
            getattr(request.state, "scope_id", None),
            getattr(request.state, "provider_manager_dependency_ms", None),
            getattr(
                request.state,
                "provider_manager_dependency_ensure_ms",
                None,
            ),
            getattr(
                request.state,
                "provider_manager_dependency_get_instance_ms",
                None,
            ),
            getattr(
                request.state,
                "provider_manager_dependency_cache_hit_before",
                None,
            ),
            getattr(request.state, "provider_models_handler_ms", None),
            _elapsed_after_handler_ms(request, duration_ms),
            response.headers.get("content-length"),
        )
        return response


def _elapsed_after_handler_ms(
    request: Request,
    fallback_total_ms: int,
) -> int | None:
    """计算 handler 返回后到 middleware 收到响应之间的耗时。"""
    handler_done_at = getattr(
        request.state,
        "provider_models_handler_done_at",
        None,
    )
    request_started_at = getattr(
        request.state,
        "provider_models_request_started_at",
        None,
    )
    if not isinstance(handler_done_at, float) or not isinstance(
        request_started_at,
        float,
    ):
        return None
    handler_done_ms = int((handler_done_at - request_started_at) * 1000)
    return max(fallback_total_ms - handler_done_ms, 0)
