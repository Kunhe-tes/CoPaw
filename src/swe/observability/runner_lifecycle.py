# -*- coding: utf-8 -*-
"""Bind independent observation state to admitted Runner questions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..config.context import (
    get_current_effective_tenant_id,
    get_current_source_id,
    resolve_runtime_tenant_id,
)
from .config import capture_enabled
from .context import bind_context, current_context
from .instrumentation import Observability
from .models import ObservabilityContext, Scope

_OBSERVABILITY = Observability()
_TERMINAL_RUN_STATUS = {
    "completed": "succeeded",
    "failed": "failed",
    "stopped": "cancelled",
    "cancelled": "cancelled",
    "timed_out": "timed_out",
    "rejected": "rejected",
}


def prepare_query_run(
    owner: Any,
    request: Any,
    messages: list[Any],
    *,
    chat_id: str | None = None,
) -> ObservabilityContext | None:
    """Create a metadata-only context before business admission commits."""
    if not capture_enabled() or not messages:
        return None
    question = messages[-1]
    question_id = str(getattr(question, "id", "") or "")
    if getattr(question, "role", None) != "user" or not question_id:
        return None
    try:
        source_id = get_current_source_id()
        tenant_id = get_current_effective_tenant_id()
    except Exception:
        return None
    meta = getattr(request, "channel_meta", None) or {}
    source_id = (
        source_id
        or getattr(request, "source_id", None)
        or meta.get("source_id")
        or "default"
    )
    if not tenant_id:
        tenant_id = getattr(
            owner,
            "tenant_id",
            None,
        ) or resolve_runtime_tenant_id(
            "default",
            str(source_id),
        )
    if chat_id is None:
        candidate = meta.get("chat_id")
        chat_id = (
            candidate if isinstance(candidate, str) and candidate else None
        )
    business_ref = {"root_question_msgid": question_id}
    if chat_id:
        business_ref["chat_id"] = chat_id
    session_id = getattr(request, "session_id", None)
    if isinstance(session_id, str) and session_id:
        business_ref["session_id"] = session_id
    try:
        return _OBSERVABILITY.prepare_run(
            scope=Scope(
                service_unit_id="swe",
                source_id=str(source_id),
                tenant_id=str(tenant_id or "default"),
                agent_id=str(
                    getattr(owner, "agent_id", "default") or "default",
                ),
            ),
            business_ref=business_ref,
        )
    except Exception:
        return None


def approval_context_carrier() -> dict[str, Any] | None:
    context = current_context()
    if context is None or not context.capture_enabled:
        return None
    try:
        return context.to_carrier()
    except Exception:
        return None


def restore_approval_context(
    owner: Any,
    request: Any,
    pending: Any,
) -> ObservabilityContext | None:
    extra = getattr(pending, "extra", None)
    if not isinstance(extra, dict):
        return None
    carrier = extra.get("agent_observability_context")
    if not isinstance(carrier, dict):
        return None
    try:
        context = ObservabilityContext.from_carrier(carrier)
        meta = getattr(request, "channel_meta", None) or {}
        source_id = (
            get_current_source_id()
            or getattr(request, "source_id", None)
            or meta.get("source_id")
        )
        tenant_id = get_current_effective_tenant_id()
        expected_source = str(source_id or "")
        expected_tenant = str(tenant_id or extra.get("tenant_id") or "default")
        expected_agent = str(
            getattr(owner, "agent_id", "default") or "default",
        )
        scope = context.scope
        business = context.business_ref
        actual_scope = (
            pending.session_id,
            pending.user_id,
            extra.get("source_id"),
            extra.get("tenant_id"),
            extra.get("agent_id"),
            expected_source,
            expected_tenant,
            expected_agent,
            extra.get("chat_id"),
            extra.get("msgid"),
        )
        carrier_scope = (
            getattr(request, "session_id", None),
            getattr(request, "user_id", None),
            scope.source_id,
            scope.tenant_id,
            scope.agent_id,
            scope.source_id,
            scope.tenant_id,
            scope.agent_id,
            business.get("chat_id"),
            business.get("root_question_msgid"),
        )
        if actual_scope != carrier_scope:
            return None
        return context
    except Exception:
        return None


def record_approval_requested(
    context: ObservabilityContext | None,
    approval_request_id: str,
    *,
    started_at: float | None = None,
) -> None:
    if context is None:
        return
    try:
        started = (
            datetime.fromtimestamp(started_at, timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
            if started_at is not None
            else None
        )
        _OBSERVABILITY.approval_requested(
            context,
            approval_request_id,
            started_at=started,
        )
    except Exception:
        return


def record_approval_resolved(
    approval_request_id: str,
    decision: str,
    *,
    started_at: float | None = None,
) -> ObservabilityContext | None:
    context = current_context()
    if context is None:
        return None
    try:
        started = (
            datetime.fromtimestamp(started_at, timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
            if started_at is not None
            else None
        )
        _OBSERVABILITY.approval_resolved(
            context,
            approval_request_id,
            decision=decision,
            started_at=started,
        )
        return context
    except Exception:
        return None


def record_approval_superseded(pending: Any) -> None:
    extra = getattr(pending, "extra", None)
    carrier = (
        extra.get("agent_observability_context")
        if isinstance(extra, dict)
        else None
    )
    if not isinstance(carrier, dict):
        return
    try:
        context = ObservabilityContext.from_carrier(carrier)
        scope = context.scope
        business = context.business_ref
        carrier_scope = (
            scope.source_id,
            scope.tenant_id,
            scope.agent_id,
            business.get("chat_id"),
            business.get("root_question_msgid"),
            business.get("session_id"),
        )
        approval_scope = (
            str(extra.get("source_id") or ""),
            str(extra.get("tenant_id") or ""),
            str(extra.get("agent_id") or ""),
            str(extra.get("chat_id") or ""),
            str(extra.get("msgid") or ""),
            str(getattr(pending, "session_id", "")),
        )
        if not context.capture_enabled or carrier_scope != approval_scope:
            return
        started_at = getattr(pending, "created_at", None)
        started = (
            datetime.fromtimestamp(started_at, timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
            if isinstance(started_at, (int, float))
            else None
        )
        _OBSERVABILITY.approval_resolved(
            context,
            str(pending.request_id),
            decision="superseded",
            started_at=started,
        )
    except Exception:
        return


def accept_query_run(context: ObservabilityContext | None) -> None:
    if context is None:
        return
    try:
        _OBSERVABILITY.accept_run(context)
    except Exception:
        return


def admit_query_run(
    owner: Any,
    request: Any,
    messages: list[Any],
    *,
    chat_id: str | None = None,
) -> ObservabilityContext | None:
    context = prepare_query_run(owner, request, messages, chat_id=chat_id)
    accept_query_run(context)
    return context


def start_query_attempt(
    context: ObservabilityContext | None,
) -> ObservabilityContext | None:
    if context is None:
        return None
    try:
        _OBSERVABILITY.run_state(context, status="running")
        return _OBSERVABILITY.start_attempt(context)
    except Exception:
        return None


def start_query_retry_attempt(
    previous: ObservabilityContext | None,
) -> ObservabilityContext | None:
    if previous is None:
        return None
    try:
        return _OBSERVABILITY.start_attempt(previous)
    except Exception:
        return None


def end_query_attempt(
    context: ObservabilityContext | None,
    *,
    status: str,
) -> None:
    if context is None:
        return
    try:
        _OBSERVABILITY.end_attempt(context, status=status)
    except Exception:
        return


def bind_query_context(context: ObservabilityContext | None):
    return bind_context(context)


def finish_query_run(
    context: ObservabilityContext | None,
    attempt: ObservabilityContext | None,
    business_status: str | None,
    *,
    waiting_for_approval: bool = False,
) -> None:
    if context is None or business_status is None:
        return
    try:
        if waiting_for_approval:
            _OBSERVABILITY.run_state(context, status="waiting_approval")
            if attempt is not None:
                _OBSERVABILITY.end_attempt(attempt, status="waiting_approval")
            return
        status = _TERMINAL_RUN_STATUS.get(business_status)
        if status is None:
            return
        if attempt is not None:
            _OBSERVABILITY.end_attempt(attempt, status=status)
        _OBSERVABILITY.end_run(context, status=status)
    except Exception:
        return


def terminal_turn_status(execution: Any, turn_id: str | None) -> str | None:
    if not turn_id:
        return None
    state = getattr(execution, "state", None)
    turn_states = state.get("turn_states") if isinstance(state, dict) else None
    turn = turn_states.get(turn_id) if isinstance(turn_states, dict) else None
    status = turn.get("status") if isinstance(turn, dict) else None
    return status if isinstance(status, str) else None


def defer_query_run_settlement(
    owner: Any,
    identity: Any,
    context: ObservabilityContext | None,
    attempt: ObservabilityContext | None,
    *,
    waiting_for_approval: bool,
) -> None:
    pending = getattr(owner, "_agent_observability_contexts", None)
    if context is not None and isinstance(pending, dict):
        pending[identity] = (context, attempt, waiting_for_approval)


def update_deferred_query_run_approval(
    owner: Any,
    identity: Any,
    *,
    waiting_for_approval: bool,
    attempt: ObservabilityContext | None = None,
    clear_attempt: bool = False,
) -> None:
    pending = getattr(owner, "_agent_observability_contexts", None)
    current = pending.get(identity) if isinstance(pending, dict) else None
    if current is not None:
        context, current_attempt, _ = current
        if isinstance(pending, dict):
            pending[identity] = (
                context,
                (
                    None
                    if clear_attempt
                    else (attempt if attempt is not None else current_attempt)
                ),
                waiting_for_approval,
            )


def take_query_run_settlement(owner: Any, identity: Any):
    pending = getattr(owner, "_agent_observability_contexts", None)
    if not isinstance(pending, dict):
        return None
    return pending.pop(identity, None)


def finish_deferred_query_run(
    owner: Any,
    identity: Any,
    business_status: str,
) -> None:
    observation = take_query_run_settlement(owner, identity)
    if observation is None:
        return
    context, attempt, waiting_for_approval = observation
    finish_query_run(
        context,
        attempt,
        business_status,
        waiting_for_approval=waiting_for_approval,
    )


def query_waiting_for_approval(
    owner: Any,
    request: Any,
    execution: Any,
) -> bool:
    runtime = getattr(execution, "runtime", None)
    if runtime is None:
        identity_getter = getattr(owner, "_answer_turn_identity", None)
        identity = (
            identity_getter(request) if callable(identity_getter) else None
        )
        entries = getattr(owner, "_answer_turn_runtimes", {})
        entry = entries.get(identity) if identity is not None else None
        runtime = entry[0] if isinstance(entry, tuple) and entry else None
    agent = getattr(runtime, "agent", None)
    pending = getattr(agent, "_tool_guard_pending_info", None)
    if isinstance(pending, dict) and pending.get("request_id"):
        return True
    lease_getter = getattr(owner, "_get_expert_main_execution", None)
    lease = lease_getter(request) if callable(lease_getter) else None
    pending = getattr(
        getattr(lease, "agent", None),
        "_tool_guard_pending_info",
        None,
    )
    return bool(isinstance(pending, dict) and pending.get("request_id"))
