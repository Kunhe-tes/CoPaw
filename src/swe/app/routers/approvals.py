"""Approval APIs."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..agent_context import get_agent_for_request
from ..approvals import get_approval_service
from ..approvals.external import (
    ExternalApprovalDecision,
    ExternalApprovalSubmission,
    submit_external_approval_decision,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])
logger = logging.getLogger(__name__)


class ExternalApprovalRequest(BaseModel):
    """Metadata supplied by the channel that submits the decision."""

    source_channel: str = Field(default="zhaohu")
    source_user_id: str | None = None
    source_message_id: str | None = None


class ExternalApprovalResponse(BaseModel):
    """Response returned after a decision has been submitted."""

    request_id: str
    decision: str
    status: str
    session_id: str
    chat_id: str | None = None
    submitted: bool
    reconnect: bool
    is_new_run: bool

    @classmethod
    def from_submission(
        cls,
        submission: ExternalApprovalSubmission,
    ) -> "ExternalApprovalResponse":
        return cls(
            request_id=submission.request_id,
            decision=submission.decision.value,
            status=submission.status,
            session_id=submission.session_id,
            chat_id=submission.chat_id,
            submitted=submission.submitted,
            reconnect=submission.reconnect,
            is_new_run=submission.is_new_run,
        )


def _request_state_snapshot(request: Request) -> dict[str, str | None]:
    return {
        "tenant_id": getattr(request.state, "tenant_id", None),
        "source_id": getattr(request.state, "source_id", None),
        "scope_id": getattr(request.state, "scope_id", None),
        "effective_tenant_id": getattr(
            request.state,
            "effective_tenant_id",
            None,
        ),
        "user_id": getattr(request.state, "user_id", None),
        "agent_id": getattr(request.state, "agent_id", None),
        "bbk_id": getattr(request.state, "bbk_id", None),
        "user_name": getattr(request.state, "user_name", None),
    }


def _request_header_snapshot(request: Request) -> dict[str, str | None]:
    return {
        "x_tenant_id": request.headers.get("X-Tenant-Id"),
        "x_source_id": request.headers.get("X-Source-Id"),
        "x_agent_id": request.headers.get("X-Agent-Id"),
    }


def _pending_snapshot(pending: object) -> dict[str, object]:
    extra = getattr(pending, "extra", None)
    if not isinstance(extra, dict):
        extra = {}
    tool_call = extra.get("tool_call")
    if not isinstance(tool_call, dict):
        tool_call = {}
    return {
        "request_id": getattr(pending, "request_id", None),
        "scope_id": getattr(pending, "scope_id", None),
        "session_id": getattr(pending, "session_id", None),
        "user_id": getattr(pending, "user_id", None),
        "channel": getattr(pending, "channel", None),
        "tool_name": getattr(pending, "tool_name", None),
        "status": getattr(pending, "status", None),
        "consumed": getattr(pending, "consumed", None),
        "extra_tenant_id": extra.get("tenant_id"),
        "extra_source_id": extra.get("source_id"),
        "extra_agent_id": extra.get("agent_id"),
        "approval_kind": extra.get("approval_kind"),
        "tool_call_id": tool_call.get("id"),
        "extra_keys": sorted(extra.keys()),
    }


async def _submit_decision(
    request_id: str,
    decision: ExternalApprovalDecision,
    body: ExternalApprovalRequest | None,
    request: Request,
) -> ExternalApprovalResponse:
    workspace = await get_agent_for_request(request)
    body = body or ExternalApprovalRequest()
    service = get_approval_service()
    state_snapshot = _request_state_snapshot(request)
    header_snapshot = _request_header_snapshot(request)
    logger.info(
        "External approval submit begin: request_id=%s decision=%s "
        "source_channel=%s source_user_id=%s source_message_id=%s "
        "state=%s headers=%s",
        request_id,
        decision.value,
        body.source_channel,
        body.source_user_id,
        body.source_message_id,
        state_snapshot,
        header_snapshot,
    )

    pending = await service.get_request(request_id)
    if pending is None:
        diagnostics: dict[str, object] | None = None
        debug_lookup = getattr(service, "debug_request_lookup", None)
        if callable(debug_lookup):
            try:
                diagnostics = await debug_lookup(request_id)
            except Exception:
                logger.warning(
                    "External approval debug lookup failed: request_id=%s",
                    request_id,
                    exc_info=True,
                )
        logger.warning(
            "External approval not found: request_id=%s decision=%s "
            "source_channel=%s state=%s headers=%s diagnostics=%s",
            request_id,
            decision.value,
            body.source_channel,
            state_snapshot,
            header_snapshot,
            diagnostics,
        )
        raise HTTPException(status_code=404, detail="approval not found")
    logger.info(
        "External approval matched: request_id=%s decision=%s pending=%s",
        request_id,
        decision.value,
        _pending_snapshot(pending),
    )

    try:
        submission = await submit_external_approval_decision(
            workspace=workspace,
            pending=pending,
            decision=decision,
            source_channel=body.source_channel,
            source_user_id=body.source_user_id,
            source_message_id=body.source_message_id,
            source_id=getattr(request.state, "source_id", None)
            or request.headers.get("X-Source-Id"),
            user_name=getattr(request.state, "user_name", None),
            bbk_id=getattr(request.state, "bbk_id", None),
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    logger.info(
        "External approval submitted: request_id=%s decision=%s status=%s "
        "session_id=%s chat_id=%s submitted=%s reconnect=%s is_new_run=%s",
        submission.request_id,
        submission.decision.value,
        submission.status,
        submission.session_id,
        submission.chat_id,
        submission.submitted,
        submission.reconnect,
        submission.is_new_run,
    )
    return ExternalApprovalResponse.from_submission(submission)


@router.post("/{request_id}/approve", response_model=ExternalApprovalResponse)
async def approve_from_external_channel(
    request_id: str,
    request: Request,
    body: ExternalApprovalRequest | None = None,
) -> ExternalApprovalResponse:
    """Approve a pending request from another channel."""
    return await _submit_decision(
        request_id,
        ExternalApprovalDecision.APPROVE,
        body,
        request,
    )


@router.post("/{request_id}/deny", response_model=ExternalApprovalResponse)
async def deny_from_external_channel(
    request_id: str,
    request: Request,
    body: ExternalApprovalRequest | None = None,
) -> ExternalApprovalResponse:
    """Deny a pending request from another channel."""
    return await _submit_decision(
        request_id,
        ExternalApprovalDecision.DENY,
        body,
        request,
    )
