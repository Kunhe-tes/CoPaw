# -*- coding: utf-8 -*-
"""High-frequency question analysis API router."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..models.high_frequency_question import (
    HighFrequencyQuestionMessageListResponse,
    HighFrequencyQuestionMessageQueryRequest,
    HighFrequencyQuestionResultSaveRequest,
    HighFrequencyQuestionResultSaveResponse,
)
from ..services.tracing.high_frequency_question import (
    HighFrequencyQuestionService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/monitor/high-frequency-question",
    tags=["high-frequency-question"],
)


@router.post(
    "/messages",
    response_model=HighFrequencyQuestionMessageListResponse,
    summary="查询高频问题分析源消息",
)
async def query_high_frequency_question_messages(
    body: HighFrequencyQuestionMessageQueryRequest,
) -> HighFrequencyQuestionMessageListResponse:
    """Query clean source messages for high-frequency question analysis."""
    try:
        service = HighFrequencyQuestionService.get_instance()
        return await service.query_messages(body)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Database not available",
        ) from exc


@router.post(
    "/results",
    response_model=HighFrequencyQuestionResultSaveResponse,
    summary="批量保存高频问题分析结果",
)
async def save_high_frequency_question_results(
    body: HighFrequencyQuestionResultSaveRequest,
) -> HighFrequencyQuestionResultSaveResponse:
    """Save AI-generated high-frequency question analysis results."""
    try:
        service = HighFrequencyQuestionService.get_instance()
        return await service.save_results(body)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Database not available",
        ) from exc
