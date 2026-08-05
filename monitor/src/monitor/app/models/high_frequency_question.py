# -*- coding: utf-8 -*-
"""Models for high-frequency question analysis APIs."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


MAX_QUERY_DAYS = 31
MAX_MESSAGE_ROWS = 10000
MAX_RANK_NO = 10
MAX_SAMPLE_QUESTIONS = 4
MAX_SAMPLE_QUESTION_LENGTH = 1000


def _strip_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class HighFrequencyQuestionMessageQueryRequest(BaseModel):
    """Request for querying source user messages."""

    source_id: str = Field(..., min_length=1, max_length=64)
    start_time: datetime
    end_time: datetime
    bbk_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("source_id")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("source_id is required")
        return stripped

    @field_validator("bbk_id")
    @classmethod
    def _strip_bbk_id(cls, value: Optional[str]) -> Optional[str]:
        return _strip_optional(value)

    @model_validator(mode="after")
    def _validate_time_range(
        self,
    ) -> "HighFrequencyQuestionMessageQueryRequest":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be earlier than end_time")
        if self.end_time - self.start_time > timedelta(days=MAX_QUERY_DAYS):
            raise ValueError("time range must not exceed 31 days")
        return self


class HighFrequencyQuestionMessageResponse(BaseModel):
    """Single source message returned for analysis."""

    message_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    bbk_id: Optional[str] = None
    content: str
    message_time: datetime


class HighFrequencyQuestionMessageListResponse(BaseModel):
    """Message query response."""

    total: int
    data: list[HighFrequencyQuestionMessageResponse] = Field(
        default_factory=list,
    )


class HighFrequencyQuestionResultItem(BaseModel):
    """Single high-frequency question ranking result."""

    scope_type: Literal["ALL", "ORG"]
    bbk_id: str = Field(..., min_length=1, max_length=64)
    rank_no: int = Field(..., ge=1, le=MAX_RANK_NO)
    topic_name: str = Field(..., min_length=1, max_length=255)
    message_count: int = Field(..., ge=0)
    user_count: int = Field(..., ge=0)
    valid_message_count: int = Field(..., ge=0)
    sample_questions: list[str] = Field(default_factory=list)

    @field_validator("bbk_id", "topic_name")
    @classmethod
    def _strip_required_fields(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("field must not be blank")
        return stripped

    @field_validator("sample_questions")
    @classmethod
    def _validate_sample_questions(cls, values: list[str]) -> list[str]:
        if len(values) > MAX_SAMPLE_QUESTIONS:
            raise ValueError("sample_questions must contain at most 4 items")

        normalized: list[str] = []
        for value in values:
            stripped = str(value or "").strip()
            if not stripped:
                continue
            if len(stripped) > MAX_SAMPLE_QUESTION_LENGTH:
                raise ValueError(
                    "sample question must not exceed 1000 characters",
                )
            normalized.append(stripped)
        return normalized

    @model_validator(mode="after")
    def _validate_result_item(self) -> "HighFrequencyQuestionResultItem":
        if self.scope_type == "ALL" and self.bbk_id != "ALL":
            raise ValueError("bbk_id must be ALL when scope_type is ALL")
        if self.scope_type == "ORG" and self.bbk_id == "ALL":
            raise ValueError("bbk_id must not be ALL when scope_type is ORG")
        if self.message_count > self.valid_message_count:
            raise ValueError(
                "message_count must not exceed valid_message_count",
            )
        if self.user_count > self.message_count:
            raise ValueError("user_count must not exceed message_count")
        return self


class HighFrequencyQuestionResultSaveRequest(BaseModel):
    """Request for saving high-frequency question results."""

    batch_id: str = Field(..., min_length=1, max_length=64)
    stat_start_time: datetime
    stat_end_time: datetime
    results: list[HighFrequencyQuestionResultItem] = Field(
        ...,
        min_length=1,
    )

    @field_validator("batch_id")
    @classmethod
    def _strip_batch_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("batch_id is required")
        return stripped

    @model_validator(mode="after")
    def _validate_save_request(
        self,
    ) -> "HighFrequencyQuestionResultSaveRequest":
        if self.stat_start_time >= self.stat_end_time:
            raise ValueError(
                "stat_start_time must be earlier than stat_end_time",
            )

        seen: set[tuple[str, str, str, int]] = set()
        for result in self.results:
            key = (
                self.batch_id,
                result.scope_type,
                result.bbk_id,
                result.rank_no,
            )
            if key in seen:
                raise ValueError(
                    "duplicate batch_id + scope_type + bbk_id + rank_no",
                )
            seen.add(key)
        return self


class HighFrequencyQuestionResultSaveResponse(BaseModel):
    """Response for saving a result batch."""

    batch_id: str
    saved_count: int
