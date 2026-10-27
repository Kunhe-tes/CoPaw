# -*- coding: utf-8 -*-
"""Server-owned leases for one bounded expert main message."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import time
from typing import Any
from uuid import uuid4

from ...config.config import MCPConfig, ToolsConfig, _default_builtin_tools
from ...runtime_workers import run_runtime_state_work

EXPERT_MAIN_TOKEN_KEY = "_expert_main_execution_token"
_DELEGATION_TOOLS = frozenset(
    {"start_subagent", "wait_subagent", "get_subagent", "cancel_subagent"},
)


@dataclass
class ExpertMainLease:
    prepared: Any
    chat_id: str
    user_id: str
    source_id: str
    turn_id: str
    approval_id: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    started_at: float | None = None
    agent: Any = None
    counted_calls: dict[str, str] = field(default_factory=dict)

    def context(self) -> dict[str, Any]:
        prepared = self.prepared
        return {
            "agent_role": "main",
            "expert_main_execution": True,
            "enable_subagents": False,
            "expert_main_instruction": prepared.instruction,
            "expert_main_policy": prepared.permission.model_dump(mode="json"),
            "expert_main_budget": prepared.budget.model_dump(mode="json"),
            "_expert_main_usage": self.usage,
            "_expert_main_counted_calls": self.counted_calls,
            "_expert_main_lease": self,
            "subagent_allowed_mcp_servers": list(prepared.mcp_configs),
            "subagent_mcp_server_keys": {
                cfg.name: key for key, cfg in prepared.mcp_configs.items()
            },
            "execution_identity": {
                "kind": "expert_main",
                "expert_id": prepared.expert_id,
                "expert_name": prepared.expert_name,
                "binding_revision": prepared.binding_revision,
            },
        }


class ExpertMainRegistry:
    def __init__(self) -> None:
        self.leases: dict[str, ExpertMainLease] = {}

    def register(
        self,
        prepared: Any,
        *,
        chat_id: str,
        user_id: str,
        source_id: str,
        turn_id: str,
    ) -> str:
        token = uuid4().hex
        self.leases[token] = ExpertMainLease(
            prepared,
            chat_id=chat_id,
            user_id=user_id,
            source_id=source_id,
            turn_id=turn_id,
        )
        return token

    def get(self, request: Any) -> ExpertMainLease | None:
        meta = getattr(request, "channel_meta", None) or {}
        token = meta.get(EXPERT_MAIN_TOKEN_KEY)
        if token is None:
            return None
        lease = self.leases.get(token) if isinstance(token, str) else None
        identity = meta.get("answer_turn_identity")
        msgid = (
            identity.get("msgid")
            if isinstance(identity, dict)
            else getattr(identity, "msgid", None)
        ) or meta.get("msgid")
        scope = (
            meta.get("chat_id"),
            getattr(request, "user_id", None),
            meta.get("source_id"),
            msgid,
        )
        if lease is None or scope != (
            lease.chat_id,
            lease.user_id,
            lease.source_id,
            lease.turn_id,
        ):
            raise ValueError("invalid expert main execution scope")
        if (
            meta.get("plan_mode_enabled")
            or meta.get("goal_mode_enabled")
            or meta.get("goal_id")
        ):
            raise ValueError("expert main execution requires ordinary chat")
        return lease

    def resume(
        self,
        *,
        approval_id: str,
        turn_id: str,
        **scope: str,
    ) -> str | None:
        for token, lease in self.leases.items():
            if lease.approval_id == approval_id and all(
                getattr(lease, key) == value for key, value in scope.items()
            ):
                lease.turn_id = turn_id
                lease.approval_id = None
                lease.agent = None
                return token
        return None

    def discard(self, token: str) -> ExpertMainLease | None:
        """Remove state immediately; the caller owns snapshot cleanup."""
        return self.leases.pop(token, None)

    async def discard_async(self, token: str) -> None:
        lease = self.discard(token)
        await _cleanup_leases([lease] if lease is not None else [])

    async def discard_approval(
        self,
        approval_id: str,
        *,
        keep_token: str | None = None,
    ) -> None:
        tokens = [
            token
            for token, lease in self.leases.items()
            if token != keep_token and lease.approval_id == approval_id
        ]
        leases = [
            lease
            for token in tokens
            if (lease := self.discard(token)) is not None
        ]
        await _cleanup_leases(leases)

    async def discard_pending(self, **scope: str) -> None:
        tokens = [
            token
            for token, lease in self.leases.items()
            if lease.approval_id is not None
            and all(
                getattr(lease, key) == value for key, value in scope.items()
            )
        ]
        leases = [
            lease
            for token in tokens
            if (lease := self.discard(token)) is not None
        ]
        await _cleanup_leases(leases)


async def _cleanup_leases(leases: list[ExpertMainLease]) -> None:
    if not leases:
        return

    def cleanup() -> None:
        for lease in leases:
            lease.prepared.cleanup()

    task = asyncio.create_task(run_runtime_state_work(cleanup))
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    task.result()
    if cancelled:
        raise asyncio.CancelledError


def restricted_expert_config(config: Any, lease: ExpertMainLease) -> Any:
    config = config.model_copy(deep=True)
    prepared = lease.prepared
    allowed = set(prepared.permission.tools.allow) - set(
        prepared.permission.tools.deny,
    )
    original_tools = config.tools.builtin_tools if config.tools else {}
    config.tools = ToolsConfig(
        builtin_tools={
            name: original_tools.get(name, default).model_copy(
                update={
                    "enabled": name in allowed
                    and original_tools.get(name, default).enabled,
                },
            )
            for name, default in _default_builtin_tools().items()
        },
    )
    config.running.max_iters = min(
        config.running.max_iters,
        prepared.budget.max_turns,
    )
    config.system_prompt_files = []
    config.mcp = MCPConfig(
        clients={
            key: value.model_copy(deep=True)
            for key, value in prepared.mcp_configs.items()
        },
    )
    return config


def expert_main_policy_reason(
    agent: Any,
    tool_name: str,
    tool_input: dict,
    *,
    include_budget: bool,
    tool_call_id: str = "",
) -> str | None:
    from ..subagents.models import PermissionPolicy
    from ..subagents.permissions import validate_tool_call

    context = agent._request_context
    if tool_name in _DELEGATION_TOOLS or tool_name.endswith(
        tuple("_" + name for name in _DELEGATION_TOOLS),
    ):
        return "expert main execution cannot delegate"
    try:
        policy = PermissionPolicy.model_validate(
            context.get("expert_main_policy"),
        )
        mcp_name = agent._resolve_mcp_server(tool_name)
        mcp_key = (context.get("subagent_mcp_server_keys") or {}).get(
            mcp_name,
            mcp_name,
        )
        decision = validate_tool_call(
            policy,
            tool_name,
            tool_input,
            mcp_server=mcp_key,
            allowed_mcp_servers=set(
                context.get("subagent_allowed_mcp_servers") or [],
            ),
        )
    except (ValueError, TypeError):
        return "invalid expert main effective policy"
    if not decision.allowed:
        return decision.reason
    if include_budget:
        _consume_tool_budget(agent, tool_name, tool_input, tool_call_id)
    elif tool_call_id in context.get("_expert_main_counted_calls", {}):
        context["_expert_main_counted_calls"][tool_call_id] = json.dumps(
            [tool_name, tool_input],
            sort_keys=True,
            ensure_ascii=False,
        )
    return None


async def expert_main_approval_action(
    agent: Any,
    tool_name: str,
    tool_input: dict,
) -> Any:
    from ...agents.tool_guard_mixin import _GuardAction

    context = agent._request_context
    policy = context.get("expert_main_policy") or {}
    asks = (policy.get("tools") or {}).get("ask") or []
    engine = agent._tool_guard_engine
    if tool_name not in asks or (
        engine.enabled and engine.is_denied(tool_name)
    ):
        return None
    if await agent._consume_preapproval(tool_name, tool_input):
        agent._tool_guard_pending_info = None
        cleanup = getattr(agent, "_cleanup_tool_guard_denied_messages", None)
        if callable(cleanup):
            await cleanup(include_denial_response=False)
        return _GuardAction("preapproved", tool_name, tool_input)
    return _GuardAction(
        "needs_approval",
        tool_name,
        tool_input,
        guard_result=agent._hook_guard_result(
            tool_name,
            tool_input,
            "Expert effective policy requires approval.",
        ),
    )


def _consume_tool_budget(
    agent: Any,
    tool_name: str,
    tool_input: dict,
    tool_call_id: str,
) -> None:
    from ...agents.tool_guard_mixin import PreToolUseTerminalStop

    context = agent._request_context
    fingerprint = json.dumps(
        [tool_name, tool_input],
        sort_keys=True,
        ensure_ascii=False,
    )
    counted = context.setdefault("_expert_main_counted_calls", {})
    approved = context.get("_expert_main_approved_tool_call") or {}
    replay_matches = (
        approved.get("id") == tool_call_id
        and approved.get("name") == tool_name
        and approved.get("input", {}) == tool_input
        and counted.get(tool_call_id) == fingerprint
    )
    if replay_matches:
        context.pop("_expert_main_approved_tool_call", None)
        return
    usage = context["_expert_main_usage"]
    if (
        usage.get("tool_calls", 0)
        >= context["expert_main_budget"]["max_tool_calls"]
    ):
        context["expert_main_terminal_reason"] = "tool_call_budget_exceeded"
        reason = "Expert main tool-call budget exceeded"
        stop = getattr(agent, "_request_pre_tool_terminal_stop", None)
        if callable(stop):
            stop(reason)
        raise PreToolUseTerminalStop(reason)
    usage["tool_calls"] = usage.get("tool_calls", 0) + 1
    counted[tool_call_id] = fingerprint


def restrict_expert_hook_overlay(overlay: Any) -> Any:
    """Keep platform hook overrides without inheriting Profile Skill state."""
    from ...agents.hook_runtime.models import HookSessionOverlay

    return HookSessionOverlay(
        entries=[
            entry.model_copy(deep=True)
            for entry in overlay.entries
            if not entry.hook_id.startswith("skill:")
        ],
        once_executed={
            key: value
            for key, value in overlay.once_executed.items()
            if not key.startswith("skill:")
        },
    )


def consume_expert_reasoning(context: dict[str, Any]) -> None:
    from ...agents.tool_guard_mixin import PreToolUseTerminalStop

    if not context.get("expert_main_execution"):
        return
    usage = context["_expert_main_usage"]
    used = usage.get("turns", 0)
    if used >= context["expert_main_budget"]["max_turns"]:
        context["expert_main_terminal_reason"] = "turn_budget_exceeded"
        raise PreToolUseTerminalStop("Expert main reasoning budget exceeded")
    usage["turns"] = used + 1


def tag_expert_message(message: Any, context: dict[str, Any]) -> None:
    if getattr(message, "role", None) != "assistant" or not context.get(
        "expert_main_execution",
    ):
        return
    message.metadata = {
        **(getattr(message, "metadata", None) or {}),
        "execution_identity": context["execution_identity"],
    }
    if context.get("expert_main_terminal_reason"):
        message.metadata["termination_reason"] = context[
            "expert_main_terminal_reason"
        ]


async def stream_expert_with_timeout(
    stream: Any,
    agent: Any,
    maximum_seconds: float,
):
    import asyncio
    from agentscope.message import Msg

    context = agent._request_context
    lease = context["_expert_main_lease"]
    if lease.started_at is None:
        lease.started_at = time.monotonic()
    deadline = lease.started_at + min(
        maximum_seconds,
        lease.prepared.budget.timeout_ms / 1000,
    )
    iterator = stream.__aiter__()
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError
            try:
                item = await asyncio.wait_for(iterator.__anext__(), remaining)
            except StopAsyncIteration:
                return
            yield item
    except asyncio.TimeoutError:
        context["expert_main_terminal_reason"] = "timeout"
        await agent.interrupt()
        message = Msg(
            lease.prepared.expert_name,
            "专家本轮执行超时，已终止。",
            "assistant",
        )
        tag_expert_message(message, context)
        memory = getattr(agent, "memory", None)
        if memory is not None:
            await memory.add(message)
        yield message, True
    finally:
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()
