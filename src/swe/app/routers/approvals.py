"""Approval APIs."""

from __future__ import annotations

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


async def _submit_decision(
    request_id: str,
    decision: ExternalApprovalDecision,
    body: ExternalApprovalRequest | None,
    request: Request,
) -> ExternalApprovalResponse:
    workspace = await get_agent_for_request(request)
    pending = await get_approval_service().get_request(request_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="approval not found")

    body = body or ExternalApprovalRequest()
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
