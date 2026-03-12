# -*- coding: utf-8 -*-
"""Chat management API."""
from __future__ import annotations
import json

from typing import Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from agentscope.session import JSONSession
from agentscope.memory import InMemoryMemory

from .manager import ChatManager
from .models import (
    ChatSpec,
    ChatHistory,
)
from .utils import agentscope_msg_to_message
from ...constant import get_request_user_id


router = APIRouter(prefix="/chats", tags=["chats"])


def get_chat_manager(request: Request) -> ChatManager:
    """Get the chat manager from app state.

    Args:
        request: FastAPI request object

    Returns:
        ChatManager instance

    Raises:
        HTTPException: If manager is not initialized
    """
    mgr = getattr(request.app.state, "chat_manager", None)
    if mgr is None:
        raise HTTPException(
            status_code=503,
            detail="Chat manager not initialized",
        )
    return mgr


def get_session(request: Request) -> JSONSession:
    """Get the session from app state.

    Args:
        request: FastAPI request object

    Returns:
        JSONSession instance

    Raises:
        HTTPException: If session is not initialized
    """
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        raise HTTPException(
            status_code=503,
            detail="Session not initialized",
        )
    return runner.session


@router.get("", response_model=list[ChatSpec])
async def list_chats(
    channel: Optional[str] = Query(None, description="Filter by channel"),
    request: Request = None,
    mgr: ChatManager = Depends(get_chat_manager),
):
    """List all chats with optional filters.

    Args:
        channel: Optional channel name to filter chats
        request: FastAPI request for getting user_id from context
        mgr: Chat manager dependency
    """
    user_id = get_request_user_id()
    if user_id is None:
        raise HTTPException(
            status_code=400,
            detail="X-User-ID header required",
        )
    return await mgr.list_chats(user_id=user_id, channel=channel)


@router.post("", response_model=ChatSpec)
async def create_chat(
    request_body: ChatSpec,
    request: Request = None,
    mgr: ChatManager = Depends(get_chat_manager),
):
    """Create a new chat.

    Server generates chat_id (UUID) automatically.

    Args:
        request_body: Chat creation request
        request: FastAPI request for getting user_id from context
        mgr: Chat manager dependency

    Returns:
        Created chat spec with UUID
    """
    user_id = get_request_user_id()
    if user_id is None:
        raise HTTPException(
            status_code=400,
            detail="X-User-ID header required",
        )
    chat_id = str(uuid4())
    spec = ChatSpec(
        id=chat_id,
        name=request_body.name,
        session_id=request_body.session_id,
        user_id=user_id,
        channel=request_body.channel,
        meta=request_body.meta,
    )
    return await mgr.create_chat(spec, user_id=user_id)


@router.post("/batch-delete", response_model=dict)
async def batch_delete_chats(
    chat_ids: list[str],
    request: Request = None,
    mgr: ChatManager = Depends(get_chat_manager),
):
    """Delete chats by chat IDs.

    Args:
        chat_ids: List of chat IDs
        request: FastAPI request for getting user_id from context
        mgr: Chat manager dependency
    Returns:
        True if deleted, False if failed

    """
    user_id = get_request_user_id()
    if user_id is None:
        raise HTTPException(
            status_code=400,
            detail="X-User-ID header required",
        )
    deleted = await mgr.delete_chats(chat_ids=chat_ids, user_id=user_id)
    return {"deleted": deleted}


@router.get("/{chat_id}", response_model=ChatHistory)
async def get_chat(
    chat_id: str,
    request: Request = None,
    mgr: ChatManager = Depends(get_chat_manager),
    session: JSONSession = Depends(get_session),
):
    """Get detailed information about a specific chat by UUID.

    Args:
        chat_id: Chat UUID
        request: FastAPI request for getting user_id from context
        mgr: Chat manager dependency
        session: JSONSession  dependency

    Returns:
        ChatHistory with messages

    Raises:
        HTTPException: If chat not found (404)
    """
    user_id = get_request_user_id()
    if user_id is None:
        raise HTTPException(
            status_code=400,
            detail="X-User-ID header required",
        )
    chat_spec = await mgr.get_chat(chat_id, user_id=user_id)
    if not chat_spec:
        raise HTTPException(
            status_code=404,
            detail=f"Chat not found: {chat_id}",
        )

    # pylint: disable=protected-access
    session_path = session._get_save_path(
        chat_spec.session_id,
        chat_spec.user_id,
    )

    try:
        with open(session_path, "r", encoding="utf-8") as file:
            state = json.load(file)
    except Exception:
        return ChatHistory(messages=[])
    memories = state.get("agent", {}).get("memory", [])
    memory = InMemoryMemory()
    memory.load_state_dict(memories)

    memories = await memory.get_memory()
    messages = agentscope_msg_to_message(memories)
    return ChatHistory(messages=messages)


@router.put("/{chat_id}", response_model=ChatSpec)
async def update_chat(
    chat_id: str,
    spec: ChatSpec,
    request: Request = None,
    mgr: ChatManager = Depends(get_chat_manager),
):
    """Update an existing chat.

    Args:
        chat_id: Chat UUID
        spec: Updated chat specification
        request: FastAPI request for getting user_id from context
        mgr: Chat manager dependency

    Returns:
        Updated chat spec

    Raises:
        HTTPException: If chat_id mismatch (400) or not found (404)
    """
    user_id = get_request_user_id()
    if user_id is None:
        raise HTTPException(
            status_code=400,
            detail="X-User-ID header required",
        )
    if spec.id != chat_id:
        raise HTTPException(
            status_code=400,
            detail="chat_id mismatch",
        )

    # Check if exists
    existing = await mgr.get_chat(chat_id, user_id=user_id)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"Chat not found: {chat_id}",
        )

    updated = await mgr.update_chat(spec, user_id=user_id)
    return updated


@router.delete("/{chat_id}", response_model=dict)
async def delete_chat(
    chat_id: str,
    request: Request = None,
    mgr: ChatManager = Depends(get_chat_manager),
):
    """Delete a chat by UUID.

    Note: This only deletes the chat spec (UUID mapping).
    JSONSession state is NOT deleted.

    Args:
        chat_id: Chat UUID
        request: FastAPI request for getting user_id from context
        mgr: Chat manager dependency

    Returns:
        True if deleted, False if failed

    Raises:
        HTTPException: If chat not found (404)
    """
    user_id = get_request_user_id()
    if user_id is None:
        raise HTTPException(
            status_code=400,
            detail="X-User-ID header required",
        )
    deleted = await mgr.delete_chats(chat_ids=[chat_id], user_id=user_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Chat not found: {chat_id}",
        )
    return {"deleted": True}
