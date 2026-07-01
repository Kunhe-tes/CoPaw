# -*- coding: utf-8 -*-
"""Background SubAgent management tools."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Callable

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

from ...app.subagents import (
    BackgroundSubAgentNotManageable,
    BackgroundSubAgentScope,
    BackgroundSubAgentStartBlocked,
    BackgroundSubAgentSupervisor,
    BackgroundSubAgentWaitSnapshot,
    DelegationSpec,
)
from ...app.subagents.models import BudgetConfig, ScopeConfig
from ...config.config import AgentProfileConfig
from ...config.utils import get_tenant_working_dir

_SUBAGENT_INTENT_TERMS = (
    "subagent",
    "SubAgent",
    "subAgent",
    "子代理",
    "子 agent",
    "子Agent",
    "后台子代理",
)
_TEXT_CONTEXT_KEYS = (
    "current_user_text",
    "user_message",
    "query",
    "prompt",
    "message_text",
)
_RUN_ID_CONTEXT_KEYS = (
    "subagent_run_id",
    "requested_subagent_run_id",
)
_DEFAULT_SUPERVISOR = BackgroundSubAgentSupervisor()


def get_default_background_subagent_supervisor() -> (
    BackgroundSubAgentSupervisor
):
    """Return the process-local default Background SubAgent supervisor."""
    return _DEFAULT_SUPERVISOR


def has_subagent_intent(request_context: dict[str, Any]) -> bool:
    """Return whether the current turn explicitly asks for SubAgents."""
    if request_context.get("subagent_tools_requested") is True:
        return True
    text = "\n".join(
        str(request_context.get(key) or "") for key in _TEXT_CONTEXT_KEYS
    )
    return any(term in text for term in _SUBAGENT_INTENT_TERMS)


def has_explicit_subagent_run_id(request_context: dict[str, Any]) -> bool:
    """Return whether this request explicitly carries a Background Run id."""
    return any(
        str(request_context.get(key) or "").strip()
        for key in _RUN_ID_CONTEXT_KEYS
    )


def build_background_subagent_scope(
    *,
    parent_agent_config: AgentProfileConfig,
    request_context: dict[str, Any],
) -> BackgroundSubAgentScope:
    """Build the current tenant-and-agent Background SubAgent scope."""
    tenant_id = str(request_context.get("tenant_id") or "default")
    agent_id = str(
        request_context.get("agent_id") or parent_agent_config.id or "default",
    )
    explicit_run_store_dir = request_context.get("_subagent_run_store_dir")
    if explicit_run_store_dir:
        run_store_dir = Path(explicit_run_store_dir)
    else:
        run_store_dir = (
            get_tenant_working_dir(tenant_id)
            / "workspaces"
            / agent_id
            / "subagent_runs"
        )
    return BackgroundSubAgentScope(
        tenant_id=tenant_id,
        agent_id=agent_id,
        run_store_dir=run_store_dir,
    )


def create_background_subagent_tools(
    *,
    supervisor: BackgroundSubAgentSupervisor,
    parent_agent_config: AgentProfileConfig,
    workspace_dir: Path,
    request_context: dict[str, Any],
) -> dict[str, Callable[..., Any]]:
    """Create start/wait/get/cancel Background SubAgent tool callables."""
    tool_scope = build_background_subagent_scope(
        parent_agent_config=parent_agent_config,
        request_context=request_context,
    )

    async def start_subagent(
        agent_name: str,
        objective: str,
        background: str = "",
        scope: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
    ) -> ToolResponse:
        """Start a Background SubAgent Run and return its run identity."""
        spec = DelegationSpec(
            parent_thread_id=str(request_context.get("session_id") or ""),
            agent_name=agent_name,
            objective=objective,
            background=background,
            scope=ScopeConfig.model_validate(scope or {}),
            budget=BudgetConfig.model_validate(budget or {}),
        )
        try:
            result = await supervisor.start(
                scope=tool_scope,
                spec=spec,
                parent_agent_config=parent_agent_config,
                workspace_dir=workspace_dir,
                request_context=request_context,
            )
        except KeyError:
            return _json_response(
                {
                    "status": "failed",
                    "reason": "unknown_subagent",
                    "agent_name": agent_name,
                },
            )
        return _json_response(_serialize_start_result(result))

    async def wait_subagent(timeout_ms: int = 3000) -> ToolResponse:
        """Wait briefly and return current Background SubAgent statuses."""
        snapshot = await supervisor.wait(
            tool_scope,
            timeout_ms=timeout_ms,
        )
        return _json_response(_serialize_wait_snapshot(snapshot))

    async def get_subagent(
        run_id: str,
        include_details: bool = False,
    ) -> ToolResponse:
        """Fetch one Background SubAgent Run in the current scope."""
        record = await supervisor.get(
            tool_scope,
            run_id,
        )
        if record is None:
            return _json_response({"status": "not_found", "run_id": run_id})
        return _json_response(_compact_record(record, include_details))

    async def cancel_subagent(run_id: str) -> ToolResponse:
        """Cancel one active Background SubAgent Run in the current scope."""
        result = await supervisor.cancel(
            tool_scope,
            run_id,
        )
        if result is None:
            return _json_response({"status": "not_found", "run_id": run_id})
        if isinstance(result, BackgroundSubAgentNotManageable):
            return _json_response(result.model_dump(mode="json"))
        return _json_response(_compact_record(result, include_details=False))

    return {
        "start_subagent": start_subagent,
        "wait_subagent": wait_subagent,
        "get_subagent": get_subagent,
        "cancel_subagent": cancel_subagent,
    }


def _json_response(payload: dict[str, Any]) -> ToolResponse:
    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text=json.dumps(payload, ensure_ascii=False),
            ),
        ],
    )


def _serialize_start_result(
    result: Any,
) -> dict[str, Any]:
    if isinstance(result, BackgroundSubAgentStartBlocked):
        return result.model_dump(mode="json")
    return _compact_record(result, include_details=False)


def _serialize_wait_snapshot(
    snapshot: BackgroundSubAgentWaitSnapshot,
) -> dict[str, Any]:
    return {
        "timed_out": snapshot.timed_out,
        "active_runs": [
            _compact_record(record, include_details=False)
            for record in snapshot.active_runs
        ],
        "terminal_runs": [
            _compact_record(record, include_details=False)
            for record in snapshot.terminal_runs
        ],
    }


def _compact_record(
    record: Any,
    include_details: bool,
) -> dict[str, Any]:
    payload = {
        "run_id": record.run_id,
        "status": record.status,
        "agent_name": record.spec.agent_name,
        "objective": record.spec.objective,
        "created_at": _dump_json_value(getattr(record, "created_at", None)),
        "started_at": _dump_json_value(getattr(record, "started_at", None)),
        "finished_at": _dump_json_value(getattr(record, "finished_at", None)),
        "result": _dump_json_value(getattr(record, "result", None)),
        "errors": _dump_json_value(getattr(record, "errors", [])),
        "worker": _dump_json_value(getattr(record, "worker", None)),
    }
    if include_details:
        payload["delegation_spec"] = record.spec.model_dump(mode="json")
        payload["effective_policy"] = record.effective_policy.model_dump(
            mode="json",
        )
    return payload


def _dump_json_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_dump_json_value(item) for item in value]
    return value
