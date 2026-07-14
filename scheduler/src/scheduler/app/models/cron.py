# -*- coding: utf-8 -*-
"""Cron Scheduler request and response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ExecutionSyncRequest(BaseModel):
    """Execution feedback sent from SWE to Scheduler."""

    job_id: str = Field(..., description="cron job id")
    job_name: str = Field(default="", description="cron job name")
    tenant_id: str = Field(default="", description="tenant id")
    source_id: str = Field(default="", description="source id")
    scheduled_time: datetime | None = Field(default=None)
    actual_time: datetime
    end_time: datetime | None = Field(default=None)
    duration_ms: int = Field(default=0)
    status: str
    error_message: str = Field(default="")
    instance_id: str = Field(default="")
    executor_leader: str = Field(default="")
    is_manual: bool = Field(default=False)
    trace_id: str = Field(default="")
    session_id: str = Field(default="")
    input_snapshot: str = Field(default="")
    output_preview: str = Field(default="")
    meta: str = Field(default="")
    notification_status: str = Field(default="not_required")
    notification_due_at: datetime | None = Field(default=None)
    notification_timezone: str = Field(default="")
    is_read: bool = Field(default=False)
    read_at: datetime | None = Field(default=None)


class RecordExecutionResponse(BaseModel):
    """Response for Scheduler execution feedback."""

    recorded: bool = Field(default=True)
    execution_id: int | None = Field(default=None)
