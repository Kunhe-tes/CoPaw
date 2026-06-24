# -*- coding: utf-8 -*-
"""HTML 预览点击统计接口路由。"""

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query, Request

from .models import (
    HtmlPreviewClickCreateResponse,
    HtmlPreviewClickEventCreate,
    HtmlPreviewClickEventListResponse,
    HtmlPreviewClickSummaryResponse,
    HtmlPreviewCustomerClickResponse,
    HtmlPreviewCustomerClickSummaryResponse,
    HtmlPreviewListSnapshotCreate,
    HtmlPreviewListSnapshotResponse,
    HtmlPreviewListSummaryResponse,
)
from .service import HtmlPreviewClickService
from .store import HtmlPreviewClickStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/html-preview", tags=["html-preview"])

_store: Optional[HtmlPreviewClickStore] = None
_service: Optional[HtmlPreviewClickService] = None


def init_html_preview_click_module(db=None) -> None:
    """初始化 HTML 预览点击统计模块。

    Args:
        db: 已连接的数据库对象

    Raises:
        RuntimeError: 数据库不可用时抛出异常
    """
    global _store, _service

    if db is None or not getattr(db, "is_connected", False):
        raise RuntimeError(
            "HTML preview click module requires a connected database.",
        )

    _store = HtmlPreviewClickStore(db)
    _service = HtmlPreviewClickService(_store)
    logger.info("HTML preview click module initialized")


def get_service() -> HtmlPreviewClickService:
    """获取 HTML 预览点击统计服务实例。"""
    if _service is None:
        raise RuntimeError("HTML preview click module not initialized")
    return _service


def _first_text(*values: Optional[str]) -> Optional[str]:
    """返回第一个非空字符串。"""
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _split_text_list(value: Optional[str]) -> Optional[list[str]]:
    """解析逗号分隔的筛选值，便于后续扩展多分行查询。"""
    if not isinstance(value, str):
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


def _get_request_source_id(request: Request) -> Optional[str]:
    """从请求上下文解析当前来源标识。"""
    return getattr(request.state, "source_id", None) or request.headers.get(
        "X-Source-Id",
    )


def _get_request_user_id(request: Request) -> Optional[str]:
    """从请求上下文解析当前用户标识。"""
    return _first_text(
        getattr(request.state, "user_id", None),
        request.headers.get("X-User-Id"),
    )


def _get_request_user_name(request: Request) -> Optional[str]:
    """从请求上下文解析当前用户名称。"""
    value = _first_text(
        getattr(request.state, "user_name", None),
        request.headers.get("X-User-Name"),
    )
    return unquote(value) if value else None


def _get_request_bbk_id(request: Request) -> Optional[str]:
    """从请求上下文解析当前分行/机构标识。"""
    return _first_text(
        getattr(request.state, "bbk", None),
        getattr(request.state, "bbk_id", None),
        request.headers.get("X-Bbk-Id"),
        request.headers.get("X-BBK-Id"),
    )


@router.post("/events", response_model=HtmlPreviewClickCreateResponse)
async def create_html_preview_click_event(
    request: Request,
    event: HtmlPreviewClickEventCreate,
) -> HtmlPreviewClickCreateResponse:
    """提交一次 HTML 预览按钮点击事件。"""
    try:
        service = get_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    enriched = event.model_copy(
        update={
            "source_id": _first_text(
                _get_request_source_id(request),
                event.source_id,
            ),
            "user_id": _first_text(
                _get_request_user_id(request),
                event.user_id,
            ),
            "user_name": _first_text(
                _get_request_user_name(request),
                event.user_name,
            ),
            "bbk_id": _first_text(_get_request_bbk_id(request), event.bbk_id),
            "clicked_at": event.clicked_at or datetime.now(),
        },
    )

    try:
        await service.create_event(enriched)
    except Exception as exc:
        logger.exception("保存 HTML 预览点击事件失败: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=(
                "保存 HTML 预览点击事件失败，" "请检查数据库表结构与后端日志。"
            ),
        ) from exc

    return HtmlPreviewClickCreateResponse()


@router.post("/list-snapshot", response_model=HtmlPreviewListSnapshotResponse)
async def create_html_preview_list_snapshot(
    request: Request,
    snapshot: HtmlPreviewListSnapshotCreate,
) -> HtmlPreviewListSnapshotResponse:
    """提交一份 HTML 预览名单客户快照。"""
    try:
        service = get_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    enriched = snapshot.model_copy(
        update={
            "source_id": _first_text(
                _get_request_source_id(request),
                snapshot.source_id,
            ),
            "bbk_id": _first_text(
                _get_request_bbk_id(request),
                snapshot.bbk_id,
            ),
            "snapshot_at": snapshot.snapshot_at or datetime.now(),
        },
    )
    try:
        count = await service.create_list_snapshot(enriched)
    except Exception as exc:
        logger.exception("保存 HTML 预览名单快照失败: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=(
                "保存 HTML 预览名单快照失败，" "请检查数据库表结构与后端日志。"
            ),
        ) from exc
    return HtmlPreviewListSnapshotResponse(customer_count=count)


@router.get("/events", response_model=HtmlPreviewClickEventListResponse)
async def list_html_preview_click_events(
    request: Request,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    bbk_ids: Optional[str] = None,
    cron_task_id: Optional[str] = None,
    file_url: Optional[str] = None,
    list_key: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> HtmlPreviewClickEventListResponse:
    """查询 HTML 预览按钮点击明细。"""
    try:
        service = get_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    items = await service.list_events(
        source_id=_get_request_source_id(request),
        start_time=start_time,
        end_time=end_time,
        bbk_ids=_split_text_list(bbk_ids),
        cron_task_id=_first_text(cron_task_id),
        file_url=_first_text(file_url),
        list_key=_first_text(list_key),
        limit=limit,
    )
    return HtmlPreviewClickEventListResponse(items=items)


@router.get("/events/summary", response_model=HtmlPreviewClickSummaryResponse)
async def get_html_preview_click_summary(
    request: Request,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    bbk_ids: Optional[str] = None,
    cron_task_id: Optional[str] = None,
    file_url: Optional[str] = None,
    list_key: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=200),
) -> HtmlPreviewClickSummaryResponse:
    """按按钮聚合查询 HTML 预览点击次数。"""
    try:
        service = get_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    items = await service.list_summary(
        source_id=_get_request_source_id(request),
        start_time=start_time,
        end_time=end_time,
        bbk_ids=_split_text_list(bbk_ids),
        cron_task_id=_first_text(cron_task_id),
        file_url=_first_text(file_url),
        list_key=_first_text(list_key),
        limit=limit,
    )
    return HtmlPreviewClickSummaryResponse(items=items)


@router.get(
    "/events/customer-summary",
    response_model=HtmlPreviewCustomerClickSummaryResponse,
)
async def get_html_preview_customer_click_summary(
    request: Request,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    bbk_ids: Optional[str] = None,
    cron_task_id: Optional[str] = None,
    file_url: Optional[str] = None,
    list_key: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=200),
) -> HtmlPreviewCustomerClickSummaryResponse:
    """按客户聚合查询洞察和电访按钮点击次数。"""
    try:
        service = get_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    items = await service.list_customer_summary(
        source_id=_get_request_source_id(request),
        start_time=start_time,
        end_time=end_time,
        bbk_ids=_split_text_list(bbk_ids),
        cron_task_id=_first_text(cron_task_id),
        file_url=_first_text(file_url),
        list_key=_first_text(list_key),
        limit=limit,
    )
    return HtmlPreviewCustomerClickSummaryResponse(items=items)


@router.get("/lists", response_model=HtmlPreviewListSummaryResponse)
async def list_html_preview_lists(
    request: Request,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    bbk_ids: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: Optional[int] = Query(default=None, ge=1, le=100),
    limit: Optional[int] = Query(default=None, ge=1, le=200),
) -> HtmlPreviewListSummaryResponse:
    """查询 HTML 名单维度统计。"""
    try:
        service = get_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    resolved_page_size = page_size or (min(limit, 100) if limit else 100)
    return await service.list_lists(
        source_id=_get_request_source_id(request),
        start_time=start_time,
        end_time=end_time,
        bbk_ids=_split_text_list(bbk_ids),
        page=page,
        page_size=resolved_page_size,
    )


@router.get(
    "/customer-clicks",
    response_model=HtmlPreviewCustomerClickResponse,
)
async def list_html_preview_customer_clicks(
    request: Request,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    bbk_ids: Optional[str] = None,
    cron_task_id: Optional[str] = None,
    file_url: Optional[str] = None,
    list_key: Optional[str] = None,
    include_unclicked: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
) -> HtmlPreviewCustomerClickResponse:
    """查询 HTML 名单客户维度洞察和电访点击明细。"""
    try:
        service = get_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    items = await service.list_customer_clicks(
        source_id=_get_request_source_id(request),
        start_time=start_time,
        end_time=end_time,
        bbk_ids=_split_text_list(bbk_ids),
        cron_task_id=_first_text(cron_task_id),
        file_url=_first_text(file_url),
        list_key=_first_text(list_key),
        include_unclicked=include_unclicked,
        limit=limit,
    )
    return HtmlPreviewCustomerClickResponse(items=items)
