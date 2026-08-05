# -*- coding: utf-8 -*-
"""Zhaohu channel callback router.

Exports ``zhaohu_router`` with Zhaohu callback endpoint:
``/api/zhaohu/callback`` - receives inbound messages from Zhaohu platform.
"""

from __future__ import annotations

import json
import logging
import ssl
from typing import Any, Optional, Dict

import httpx

from fastapi import APIRouter, BackgroundTasks, Request, Response

from pydantic import BaseModel, Field

from ...constant import EnvVarLoader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Zhaohu callback router
# ---------------------------------------------------------------------------
zhaohu_router = APIRouter(tags=["zhaohu"])


class ZhaohuCallbackRequest(BaseModel):
    """Zhaohu message callback request body."""

    msg_id: Optional[str] = Field(default=None, alias="msgId")
    source_id: str = Field(default="", alias="sourceId")
    from_id: str = Field(default="", alias="fromId")
    to_id: str = Field(default="", alias="toId")
    group_id: Optional[int] = Field(default=None, alias="groupId")
    group_name: Optional[str] = Field(default=None, alias="groupName")
    msg_type: str = Field(default="", alias="msgType")
    msg_content: str = Field(default="", alias="msgContent")
    timestamp: int = Field(default=0)
    custom_info: Optional[Any] = Field(default=None, alias="customInfo")

    model_config = {"populate_by_name": True, "extra": "ignore"}


# Default timeout for user query requests
_DEFAULT_TIMEOUT = 30.0


def _json_response(
    code: str,
    message: str,
    status_code: int = 200,
) -> Response:
    return Response(
        content=json.dumps({"code": code, "message": message}),
        status_code=status_code,
        media_type="application/json",
    )


async def _query_user_info(open_id: str) -> Optional[Dict[str, Any]]:
    """Query user info to convert openId to sapId.

    Returns user info dict with sapId, or None if query fails.
    This is a standalone method that reads config from environment variables.
    """
    user_query_url = EnvVarLoader.get_str(
        "SWE_ZHAOHU_USER_QUERY_URL",
        "",
    )

    if not user_query_url:
        logger.warning(
            "zhaohu user query skipped: user_query_url not configured",
        )
        return None

    if not open_id:
        return None

    query_payload = {
        "compareType": "EQ",
        "matchFields": ["openId"],
        "keyWord": open_id,
    }
    timeout = httpx.Timeout(_DEFAULT_TIMEOUT, connect=10.0)
    # 自定义SSL上下文
    context = ssl.create_default_context()
    context.options |= 0x4

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            verify=context,
        ) as client:
            response = await client.post(
                user_query_url,
                json=query_payload,
            )
            response.raise_for_status()
            data = response.json()

        if data.get("code") != "200":
            logger.warning(
                "zhaohu user query failed: code=%s message=%s",
                data.get("code"),
                data.get("message"),
            )
            return None

        user_list = data.get("data") or []
        if not user_list or not isinstance(user_list, list):
            logger.warning(
                "zhaohu user query: no user found for openId=%s",
                open_id,
            )
            return None

        user_info = user_list[0]
        logger.info(
            "request zhaohu user query: openId=%s -> sapId=%s",
            open_id,
            user_info.get("sapId"),
        )
        return user_info

    except Exception:
        logger.exception("zhaohu user query failed for openId=%s", open_id)
        return None


async def _resolve_user_scope(
    request: Request,
    from_id: str,
    to_id: str,
    source_id_override: str = "",
) -> str:
    """Query user info, set request.state for tenant/scope resolution.

    Returns sap_id (empty string if lookup failed).
    """
    user_info = await _query_user_info(from_id)
    sap_id = (user_info or {}).get("sapId") or ""
    if sap_id:
        request.state.tenant_id = sap_id
        request.state.user_id = sap_id

    source_id = None
    if source_id_override:
        source_id = source_id_override
    elif sap_id and to_id:
        from ..channels.zhaohu.binding_store import get_zhaohu_binding_store

        binding_store = get_zhaohu_binding_store()
        if binding_store:
            source_id = await binding_store.get_source_id_by_robot(
                sap_id,
                to_id,
            )
    if source_id:
        request.state.source_id = source_id
    if sap_id and source_id:
        from ...config.context import encode_scope_id

        request.state.scope_id = encode_scope_id(sap_id, source_id)
        request.state.effective_tenant_id = request.state.scope_id

    return sap_id


async def _get_zhaohu_channel(request: Request):
    """Retrieve the ZhaohuChannel from workspace, or None."""
    from ..agent_context import get_agent_for_request

    try:
        workspace = await get_agent_for_request(request)
    except Exception:
        return None

    if not workspace or not workspace.channel_manager:
        return None

    for ch in workspace.channel_manager.channels:
        if ch.channel == "zhaohu":
            return ch
    return None


async def _process_callback_background(
    channel,
    body: ZhaohuCallbackRequest,
) -> None:
    """Background task to process callback message.

    This runs after the response is returned to the caller.
    The channel.process_callback_message() method will:
    1. Set user context via set_request_user_id()
    2. Query user info (openId -> sapId)
    3. Load session state from file (conversation history)
    4. Call LLM with conversation context
    5. Save session state
    6. Send response via push_url
    """
    try:
        await channel.process_callback_message(body)
    except Exception:
        logger.exception(
            "zhaohu background processing failed: msgId=%s",
            body.msg_id,
        )


async def _handle_custom_card(
    request: Request,
    body: ZhaohuCallbackRequest,
) -> Response:
    """Handle CustomCard callback: parse addition and submit approval decision."""
    try:
        msg_data = json.loads(body.msg_content)
    except (json.JSONDecodeError, TypeError):
        logger.warning("zhaohu CustomCard: invalid msgContent")
        return _json_response("ok", "received")

    addition = msg_data.get("addition") or {}
    request_id = addition.get("request_id", "")
    action_type = addition.get("type", "")

    if not request_id or action_type not in ("approve", "reject"):
        logger.warning(
            "zhaohu CustomCard: missing request_id or invalid type, addition=%s",
            addition,
        )
        return _json_response("ok", "received")

    agent_id = addition.get("agent_id") or addition.get("agentId", "")
    if agent_id:
        request.state.agent_id = agent_id

    source_id_override = addition.get("source_id", "")
    user_id = await _resolve_user_scope(
        request,
        body.from_id,
        body.to_id,
        source_id_override=source_id_override,
    )
    state_tenant_id = getattr(request.state, "tenant_id", None)
    state_source_id = getattr(request.state, "source_id", None)
    state_scope_id = getattr(request.state, "scope_id", None)

    from ..tenant_context import bind_tenant_context
    from ..routers.approvals import ExternalApprovalRequest, _submit_decision
    from ..approvals.external import ExternalApprovalDecision

    decision = (
        ExternalApprovalDecision.APPROVE
        if action_type == "approve"
        else ExternalApprovalDecision.DENY
    )
    approval_body = ExternalApprovalRequest(
        source_channel="zhaohu",
        source_user_id=user_id,
        source_message_id=request_id,
    )
    try:
        with bind_tenant_context(
            tenant_id=state_tenant_id,
            user_id=user_id,
            source_id=state_source_id,
            scope_id=state_scope_id,
        ):
            result = await _submit_decision(
                request_id,
                decision,
                approval_body,
                request,
            )
        return Response(
            content=result.model_dump_json(),
            media_type="application/json",
        )
    except Exception:
        logger.exception(
            "zhaohu CustomCard approval failed: request_id=%s type=%s",
            request_id,
            action_type,
        )
        return _json_response("error", "approval failed", status_code=500)


async def _handle_text_message(
    zhaohu_ch,
    body: ZhaohuCallbackRequest,
    background_tasks: BackgroundTasks,
) -> Response:
    """Handle text callback: dedup check, then process in background."""
    if not zhaohu_ch.try_accept_message(body.msg_id):
        logger.info(
            "zhaohu duplicate ignored: msgId=%s from=%s",
            body.msg_id,
            body.from_id,
        )
        return _json_response("ok", "duplicate ignored")

    background_tasks.add_task(_process_callback_background, zhaohu_ch, body)
    return _json_response("ok", "received")


@zhaohu_router.post("/zhaohu/callback")
async def zhaohu_callback(
    request: Request,
    body: ZhaohuCallbackRequest,
    background_tasks: BackgroundTasks,
) -> Response:
    """Zhaohu message callback: receive inbound messages."""
    # text 分支：通用前置
    user_id = await _resolve_user_scope(request, body.from_id, body.to_id)
    source_id = getattr(request.state, "source_id", None)
    if source_id:
        body.source_id = source_id
    logger.info(
        "zhaohu callback: fromId=%s userId=%s sourceId=%s msgType=%s",
        body.from_id,
        user_id,
        source_id,
        body.msg_type,
    )
    if not source_id:
        return _json_response("error", "source_id not found", status_code=401)

    zhaohu_ch = await _get_zhaohu_channel(request)
    if not zhaohu_ch:
        logger.warning("zhaohu callback received but channel not available")
        return _json_response(
            "error",
            "channel not available",
            status_code=503,
        )
    if not zhaohu_ch.enabled:
        logger.debug("zhaohu callback received but channel disabled")
        return _json_response("error", "channel disabled", status_code=503)

    # 按类型分发 回执处理
    if body.msg_type == "CustomCard":
        return await _handle_custom_card(request, body)
    # text
    if body.msg_type == "text":
        return await _handle_text_message(zhaohu_ch, body, background_tasks)
    return _json_response("error", "type not allowed", status_code=401)
