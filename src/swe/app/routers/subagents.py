# -*- coding: utf-8 -*-
"""SubAgent run monitor APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..agent_context import get_agent_for_request
from ..subagents.monitor import (
    SubAgentCancelResult,
    SubAgentMonitorService,
    SubAgentRunNotManageableError,
    SubAgentRunSnapshot,
    create_monitor_service,
)

router = APIRouter(prefix="/subagents", tags=["subagents"])


class CancelSubAgentRunRequest(BaseModel):
    """Frontend stop request for one Background SubAgent Run."""

    chat_id: str = Field(..., min_length=1)


async def _get_workspace(request: Request) -> Any:
    workspace = getattr(request.state, "workspace", None)
    if workspace is not None:
        return workspace
    workspace = getattr(request.app.state, "workspace", None)
    if workspace is not None:
        return workspace
    return await get_agent_for_request(request)


async def _get_chat(workspace: Any, chat_id: str) -> Any:
    chat_manager = getattr(workspace, "chat_manager", None)
    if chat_manager is None:
        raise HTTPException(
            status_code=500,
            detail="ChatManager not initialized",
        )
    chat = await chat_manager.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return chat


def _monitor_service(workspace: Any) -> SubAgentMonitorService:
    return create_monitor_service(workspace)


@router.get("/runs", response_model=SubAgentRunSnapshot)
async def get_subagent_runs(
    chat_id: str = Query(..., min_length=1),
    workspace: Any = Depends(_get_workspace),
) -> SubAgentRunSnapshot:
    """Return slim Background SubAgent Run snapshots for one chat."""
    chat = await _get_chat(workspace, chat_id)
    return await _monitor_service(workspace).snapshot(
        chat_id=chat.id,
        session_id=chat.session_id,
    )


@router.post(
    "/runs/{run_id}/cancel",
    response_model=SubAgentCancelResult,
)
async def cancel_subagent_run(
    run_id: str,
    body: CancelSubAgentRunRequest,
    workspace: Any = Depends(_get_workspace),
) -> SubAgentCancelResult:
    """Cancel one running Background SubAgent Run in the current chat."""
    chat = await _get_chat(workspace, body.chat_id)
    try:
        run = await _monitor_service(workspace).cancel(
            run_id=run_id,
            session_id=chat.session_id,
        )
    except SubAgentRunNotManageableError as exc:
        raise HTTPException(status_code=409, detail=exc.reason) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="subagent run not found")
    return SubAgentCancelResult(run=run)
