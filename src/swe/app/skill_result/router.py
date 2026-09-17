# -*- coding: utf-8 -*-
"""技能执行结果接口路由。"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from .models import SkillResultCreate, SkillResultCreateResponse
from .service import SkillResultService
from .store import SkillResultStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skill-result", tags=["skill-result"])

_service: Optional[SkillResultService] = None


def init_skill_result_module(db=None) -> None:
    """初始化技能执行结果模块。

    Args:
        db: 已连接的数据库对象

    Raises:
        RuntimeError: 数据库不可用时抛出异常
    """
    global _service

    if db is None or not getattr(db, "is_connected", False):
        raise RuntimeError(
            "SkillResult module requires a connected database.",
        )

    _service = SkillResultService(SkillResultStore(db))
    logger.info("SkillResult module initialized")


def get_service() -> SkillResultService:
    """获取技能执行结果服务实例。"""
    if _service is None:
        raise RuntimeError("SkillResult module not initialized")
    return _service


def _first_text(*values: Optional[str]) -> Optional[str]:
    """返回第一个非空字符串。"""
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _get_request_user_id(request: Request) -> Optional[str]:
    """从请求上下文解析当前用户 ID。"""
    return _first_text(
        getattr(request.state, "user_id", None),
        request.headers.get("X-User-Id"),
    )


def _get_request_bbk(request: Request) -> Optional[str]:
    """从请求上下文解析当前分行编码。"""
    return _first_text(
        getattr(request.state, "bbk_id", None),
        request.headers.get("X-Bbk-Id"),
    )


def _get_request_source_id(request: Request) -> Optional[str]:
    """从请求上下文解析当前来源标识。"""
    return getattr(request.state, "source_id", None) or request.headers.get(
        "X-Source-Id",
    )


@router.post("", response_model=SkillResultCreateResponse)
async def create_skill_result(
    request: Request,
    payload: SkillResultCreate,
) -> SkillResultCreateResponse:
    """保存一次技能执行结果。"""
    try:
        service = get_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    enriched = payload.model_copy(
        update={
            "user_id": _first_text(
                payload.user_id,
                _get_request_user_id(request),
            ),
            "bbk": _first_text(
                payload.bbk,
                _get_request_bbk(request),
            ),
        },
    )

    try:
        record_id, trace_id = await service.create(
            enriched,
            source_id=_get_request_source_id(request),
        )
    except Exception as exc:
        logger.exception("保存技能执行结果失败: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="保存技能执行结果失败，请检查表结构与后端日志。",
        ) from exc

    return SkillResultCreateResponse(id=record_id, trace_id=trace_id)
