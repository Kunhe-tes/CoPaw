# -*- coding: utf-8 -*-
"""资产上传记录接口路由。"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from .models import (
    AssetUploadFileNameList,
    PaginatedAssetUploadRecords,
    QueryIdKeyRequest,
    QueryIdKeyResponse,
    TemplateResultRequest,
    TemplateResultResponse,
    TemplateSearchResponse,
)
from .service import AssetUploadRecordService
from .store import AssetUploadRecordStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/template", tags=["template"])

_store: Optional[AssetUploadRecordStore] = None
_service: Optional[AssetUploadRecordService] = None


def init_asset_upload_record_module(db=None) -> None:
    """初始化资产上传记录模块。"""
    global _store, _service

    if db is None or not getattr(db, "is_connected", False):
        raise RuntimeError(
            "AssetUploadRecord module requires a connected database.",
        )

    _store = AssetUploadRecordStore(db)
    _service = AssetUploadRecordService(_store)
    logger.info("AssetUploadRecord module initialized")


def get_service() -> AssetUploadRecordService:
    """获取资产上传记录服务实例。"""
    if _service is None:
        raise RuntimeError("AssetUploadRecord module not initialized")
    return _service


def _get_request_source_id(request: Request) -> Optional[str]:
    """从请求上下文解析当前来源标识。"""
    return getattr(request.state, "source_id", None) or request.headers.get(
        "X-Source-Id",
    )


@router.get("/records", response_model=PaginatedAssetUploadRecords)
async def query_asset_upload_records(
    request: Request,
    source_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedAssetUploadRecords:
    """分页查询资产上传记录。"""
    try:
        service = get_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    effective_source_id = source_id or _get_request_source_id(request)
    return await service.query_records(
        source_id=effective_source_id,
        page=page,
        page_size=page_size,
    )


@router.get("/file-templates", response_model=AssetUploadFileNameList)
async def list_asset_upload_file_names() -> AssetUploadFileNameList:
    """查询所有上传文件名。"""
    try:
        service = get_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return await service.list_all_file_names()


@router.get("/search", response_model=TemplateSearchResponse)
async def search_template_by_name(
    templateName: str,
) -> TemplateSearchResponse:
    """根据文件名搜索模板ID。"""
    try:
        service = get_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return await service.search_template_id(templateName)


@router.post("/result", response_model=TemplateResultResponse)
async def query_template_result(
    payload: TemplateResultRequest,
) -> TemplateResultResponse:
    """查询模板结果。"""
    try:
        service = get_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return await service.query_template_result(
        result_id=payload.resultId,
        template_id=payload.templateId,
    )


@router.post("/query-id-key", response_model=QueryIdKeyResponse)
async def query_id_key(
    payload: QueryIdKeyRequest,
) -> QueryIdKeyResponse:
    """根据ID Key查询模板信息。"""
    try:
        service = get_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return await service.query_id_key(
        template_name=payload.templateName,
        user_id=payload.userId,
        bbk_org_id=payload.bbkOrgId,
        id_key=payload.idKey,
    )
