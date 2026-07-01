# -*- coding: utf-8 -*-
"""Source 系统配置 HTTP 请求绑定中间件。"""

import logging
import time
from typing import Awaitable, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from .runtime import (
    reset_current_source_system_config,
    set_current_source_system_config,
)
from .service import (
    SourceSystemConfigDataInvalid,
    SourceSystemConfigService,
    SourceSystemConfigUnavailable,
)
from swe.app.middleware.provider_models_timing import (
    is_provider_models_list_request,
    log_provider_models_middleware_before_next,
    log_provider_models_middleware_done,
    log_provider_models_middleware_error,
)

logger = logging.getLogger(__name__)


class SourceSystemConfigMiddleware(BaseHTTPMiddleware):
    """按请求 source_id 加载并绑定 effective source 系统配置。"""

    def __init__(
        self,
        app: ASGIApp,
        service: SourceSystemConfigService | None = None,
    ):
        """初始化中间件。"""
        super().__init__(app)
        self.service = service

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """在 request.state 和 ContextVar 中绑定 source 系统配置。"""
        is_timing = is_provider_models_list_request(request)
        started_at = time.perf_counter()
        source_id = getattr(request.state, "source_id", None)
        service = self.service or getattr(
            request.app.state,
            "source_system_config_service",
            None,
        )
        before_next_at = None
        if source_id is None or service is None:
            try:
                if is_timing:
                    before_next_at = (
                        log_provider_models_middleware_before_next(
                            logger,
                            "SourceSystemConfigMiddleware",
                            request,
                            started_at,
                            source_id=source_id,
                            has_service=service is not None,
                            resolve_config_ms=None,
                        )
                    )
                response = await call_next(request)
                if is_timing and before_next_at is not None:
                    log_provider_models_middleware_done(
                        logger,
                        "SourceSystemConfigMiddleware",
                        request,
                        started_at,
                        before_next_at,
                        response,
                        source_id=source_id,
                        has_service=service is not None,
                        resolve_config_ms=None,
                    )
                return response
            except Exception:
                if is_timing:
                    log_provider_models_middleware_error(
                        logger,
                        "SourceSystemConfigMiddleware",
                        request,
                        started_at,
                        before_next_at,
                        source_id=source_id,
                        has_service=service is not None,
                        resolve_config_ms=None,
                    )
                raise

        token = None
        resolve_config_ms = 0
        try:
            resolve_started_at = time.perf_counter()
            config = await service.resolve_config(source_id)
            resolve_config_ms = int(
                (time.perf_counter() - resolve_started_at) * 1000,
            )
            request.state.source_system_config = config
            token = set_current_source_system_config(config)
            if is_timing:
                before_next_at = log_provider_models_middleware_before_next(
                    logger,
                    "SourceSystemConfigMiddleware",
                    request,
                    started_at,
                    source_id=source_id,
                    has_service=True,
                    resolve_config_ms=resolve_config_ms,
                )
            response = await call_next(request)
            if is_timing and before_next_at is not None:
                log_provider_models_middleware_done(
                    logger,
                    "SourceSystemConfigMiddleware",
                    request,
                    started_at,
                    before_next_at,
                    response,
                    source_id=source_id,
                    has_service=True,
                    resolve_config_ms=resolve_config_ms,
                )
            return response
        except SourceSystemConfigUnavailable as exc:
            logger.error("Source 系统配置不可用: %s", exc)
            return JSONResponse(
                status_code=503,
                content={"detail": "Source system config unavailable"},
            )
        except SourceSystemConfigDataInvalid as exc:
            logger.error("Source 系统配置数据损坏: %s", exc)
            return JSONResponse(
                status_code=500,
                content={"detail": "Source system config data is invalid"},
            )
        except Exception:
            if is_timing:
                log_provider_models_middleware_error(
                    logger,
                    "SourceSystemConfigMiddleware",
                    request,
                    started_at,
                    before_next_at,
                    source_id=source_id,
                    has_service=True,
                    resolve_config_ms=resolve_config_ms,
                )
            raise
        finally:
            if token is not None:
                reset_current_source_system_config(token)
