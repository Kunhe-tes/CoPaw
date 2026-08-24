# -*- coding: utf-8 -*-
# flake8: noqa: E704
# pylint: disable=too-many-statements
"""Agent-turn, Stop-gate, and Goal-continuation lifecycle orchestration."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Protocol

from agentscope.message import Msg
from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest

from ...agents.tool_guard_mixin import PreToolUseTerminalStop
from ...agents.hook_runtime.models import HookDecision, MergedHookResult


class TurnLifecycleOwner(Protocol):
    """Narrow runner surface used by the query turn lifecycle."""

    tenant_id: str | None
    agent_id: str

    def _stream_printing_messages(self, **kwargs: Any) -> Any: ...

    async def _enforce_query_timeout(
        self,
        stream: Any,
        **kwargs: Any,
    ) -> AsyncGenerator[tuple[Msg, bool], None]: ...

    def _resolve_max_stop_turns(self, agent_config: Any) -> int: ...

    def _resolve_max_automatic_follow_up_turns(
        self,
        agent_config: Any,
        stop_turns: int,
    ) -> int: ...

    def _extract_assistant_response(
        self,
        agent: Any,
        *,
        memory_start: int = 0,
    ) -> str: ...

    def _request_goal_id(self, request: AgentRequest) -> str | None: ...

    def _goal_matches_runtime_scope(self, goal: Any, runtime: Any) -> bool: ...

    def _build_goal_contract_context(self, goal: Any) -> str: ...

    def _append_goal_tool_observations(
        self,
        observations: list[dict[str, str]],
        msg: Msg,
    ) -> None: ...

    def _build_goal_follow_up_msg(
        self,
        next_focus: str | None,
        steering: list[str] | None = None,
        contract_context: str | None = None,
    ) -> Msg: ...

    async def _stream_agent_turns(
        self,
        **kwargs: Any,
    ) -> AsyncGenerator[tuple[Msg, bool], None]: ...

    async def _stream_goal_finalization_turn(
        self,
        **kwargs: Any,
    ) -> AsyncGenerator[tuple[Msg, bool], None]: ...

    def _create_goal_completion_reviewer(self, **kwargs: Any) -> Any: ...

    async def _emit_stop_hook_if_needed(
        self,
        **kwargs: Any,
    ) -> MergedHookResult | None: ...

    def _should_stop_follow_up(self, outcome: Any) -> bool: ...

    def _build_stop_follow_up_msg(self, reason: str) -> Msg: ...

    def _build_stop_incomplete_msg(self, reason: str) -> Msg: ...


async def stream_agent_turns(
    owner: TurnLifecycleOwner,
    *,
    runtime: Any,
    plan: Any,
    outcome: Any,
    plan_interaction_card_metadata_key: str,
) -> AsyncGenerator[tuple[Msg, bool], None]:
    """Stream one agent turn while retaining its existing terminal semantics."""
    turn_msgs = plan.turn_msgs
    outcome.assistant_response = ""
    memory_start = len(getattr(runtime.agent.memory, "content", []))
    stop_turns = owner._resolve_max_stop_turns(runtime.agent_config)
    outcome.max_stop_turns = stop_turns
    outcome.max_automatic_follow_up_turns = (
        owner._resolve_max_automatic_follow_up_turns(
            runtime.agent_config,
            stop_turns,
        )
    )
    reset_terminal_stop = getattr(
        runtime.agent,
        "reset_pre_tool_terminal_stop",
        None,
    )
    if callable(reset_terminal_stop):
        reset_terminal_stop()
    try:
        async for msg, last in owner._enforce_query_timeout(
            owner._stream_printing_messages(
                agents=[runtime.agent],
                coroutine_task=runtime.agent(turn_msgs),
            ),
            session_id=runtime.session_id,
            agent=runtime.agent,
            run_key=(runtime.chat.id if runtime.chat is not None else None),
        ):
            metadata = getattr(msg, "metadata", None)
            if isinstance(metadata, dict) and isinstance(
                metadata.get(plan_interaction_card_metadata_key),
                dict,
            ):
                outcome.plan_interaction_turn_boundary = True
            yield msg, last
    except PreToolUseTerminalStop as exc:
        consume_terminal_stop = getattr(
            runtime.agent,
            "consume_pre_tool_terminal_stop",
            None,
        )
        reason = (
            consume_terminal_stop()
            if callable(consume_terminal_stop)
            else None
        )
        reason = (reason or exc.reason or "Hook requested stop").strip()
        outcome.task_completed = False
        outcome.completion_blocked = True
        outcome.completion_block_reason = reason
        outcome.pre_tool_terminal_stop = True
        terminal_msg = Msg(name="Friday", role="assistant", content=reason)
        await runtime.agent.memory.add(terminal_msg)
        yield terminal_msg, True
        return
    outcome.assistant_response = owner._extract_assistant_response(
        runtime.agent,
        memory_start=memory_start,
    )
    outcome.task_completed = True


async def stream_completion_lifecycle(
    owner: TurnLifecycleOwner,
    *,
    request: AgentRequest,
    runtime: Any,
    plan: Any,
    outcome: Any,
) -> AsyncGenerator[tuple[Msg, bool], None]:
    """Continue turns through Goal settlement or the Stop completion gate."""
    goal_id = owner._request_goal_id(request)
    if not goal_id:
        from ..goals.registry import get_goal_service

        service = get_goal_service()
        chat_id = str(getattr(getattr(runtime, "chat", None), "id", ""))
        active_goal = (
            await service.recent_for_chat(chat_id)
            if service is not None and chat_id
            else None
        )
        if active_goal is not None and active_goal.state.value in {
            "ACTIVE",
            "WAITING",
        }:
            if not owner._goal_matches_runtime_scope(active_goal, runtime):
                yield Msg(
                    name="Friday",
                    role="assistant",
                    content="The active Goal is not available in this chat.",
                ), True
                return
            steering_message = plan.original_user_message.strip()
            if steering_message:
                await service.enqueue_steering(
                    active_goal.goal_id,
                    steering_message,
                )
            yield Msg(
                name="Friday",
                role="assistant",
                content=(
                    "Your message was added as Goal steering. "
                    "The active Goal will continue under its confirmed Contract."
                ),
            ), True
            return
    while True:
        if goal_id:
            from ..goals.registry import get_goal_service

            service = get_goal_service()
            if service is None:
                return
            current_goal = None
            try:
                current_goal = await service.get(goal_id)
                if not owner._goal_matches_runtime_scope(
                    current_goal,
                    runtime,
                ):
                    yield Msg(
                        name="Friday",
                        role="assistant",
                        content="The requested Goal is not available in this chat.",
                    ), True
                    return
                goal = await service.begin_turn(goal_id)
            except ValueError:
                state = getattr(
                    getattr(current_goal, "state", None),
                    "value",
                    None,
                )
                yield Msg(
                    name="Friday",
                    role="assistant",
                    content=(
                        f"Goal is currently {state or 'unavailable'} and cannot start a new turn. "
                        "Use the Goal Monitor to resume, edit, or cancel it."
                    ),
                ), True
                return
            getattr(runtime.agent, "_request_context", {})[
                "goal_contract_context"
            ] = owner._build_goal_contract_context(goal)
            request_context = getattr(runtime.agent, "_request_context", {})
            request_context.pop("goal_turn_resolution", None)
            request_context.pop("_goal_turn_environment_changed", None)
            request_context["_goal_turn_tool_observations"] = []
        outcome.stop_hook_active = False
        async for msg, last in owner._stream_agent_turns(
            runtime=runtime,
            plan=plan,
            outcome=outcome,
        ):
            if goal_id:
                observations = getattr(
                    runtime.agent,
                    "_request_context",
                    {},
                ).get("_goal_turn_tool_observations")
                if isinstance(observations, list):
                    owner._append_goal_tool_observations(observations, msg)
            yield msg, False if goal_id else last
        if outcome.pre_tool_terminal_stop:
            if goal_id:
                await service.abandon_turn(
                    goal_id,
                    "Goal turn stopped before settlement",
                )
            return
        if goal_id:
            from ..goals.registry import get_goal_service
            from ..goals.runtime import GoalRuntime, GoalTurnResolution

            service = get_goal_service()
            raw = getattr(runtime.agent, "_request_context", {}).get(
                "goal_turn_resolution",
            )
            if service is None or not isinstance(raw, dict):
                if service is not None:
                    await service.abandon_turn(
                        goal_id,
                        "Main Agent did not submit a Goal turn resolution",
                    )
                return
            try:
                had_pending_steering = await service.has_pending_steering(
                    goal_id,
                )
                resolution = GoalTurnResolution.model_validate(raw)
                reviewer = owner._create_goal_completion_reviewer(
                    runtime=runtime,
                    resolution=resolution,
                )
                settled = await GoalRuntime(service, reviewer=reviewer).settle(
                    goal_id,
                    resolution,
                    wake_from_steering=had_pending_steering,
                    environment_changed=bool(
                        getattr(runtime.agent, "_request_context", {}).get(
                            "_goal_turn_environment_changed",
                        ),
                    ),
                )
            except (TypeError, ValueError):
                await service.abandon_turn(
                    goal_id,
                    "Goal turn settlement failed",
                )
                return
            if settled.state.value == "ACTIVE":
                _, steering = await service.consume_steering(goal_id)
                plan.turn_msgs = [
                    owner._build_goal_follow_up_msg(
                        settled.next_focus,
                        steering,
                        owner._build_goal_contract_context(settled),
                    ),
                ]
                continue
            if settled.state.value == "WAITING":
                from ..goals.wakeup import wait_for_goal_wake

                while settled.state.value == "WAITING":
                    await wait_for_goal_wake(goal_id)
                    woken = await service.get(goal_id)
                    if woken.state.value != "ACTIVE":
                        settled = woken
                        break
                    retried = await GoalRuntime(
                        service,
                        reviewer=reviewer,
                    ).retry_pending_completion_review(goal_id)
                    if retried.state.value == "COMPLETE":
                        async for (
                            finalization_msg,
                            last,
                        ) in owner._stream_goal_finalization_turn(
                            runtime=runtime,
                            goal=retried,
                        ):
                            yield finalization_msg, last
                        return
                    settled = retried
                    if settled.state.value != "ACTIVE":
                        continue
                    _, steering = await service.consume_steering(goal_id)
                    plan.turn_msgs = [
                        owner._build_goal_follow_up_msg(
                            retried.next_focus,
                            steering,
                            owner._build_goal_contract_context(retried),
                        ),
                    ]
                    break
                if settled.state.value == "ACTIVE":
                    continue
            if settled.state.value == "INTERRUPTED":
                return
            async for (
                finalization_msg,
                last,
            ) in owner._stream_goal_finalization_turn(
                runtime=runtime,
                goal=settled,
            ):
                yield finalization_msg, last
            return
        stop_result = await owner._emit_stop_hook_if_needed(
            request=request,
            runtime=runtime,
            plan=plan,
            outcome=outcome,
        )
        if (
            stop_result is not None
            and stop_result.decision == HookDecision.BLOCK
        ):
            reason = (
                stop_result.blocking_failure_reason
                if stop_result.has_blocking_failure
                else stop_result.reason
            ) or "Stop blocked completion"
            if (
                not stop_result.has_blocking_failure
                and owner._should_stop_follow_up(outcome)
            ):
                outcome.stop_follow_up_turns += 1
                outcome.automatic_follow_up_turns += 1
                plan.turn_msgs = [owner._build_stop_follow_up_msg(reason)]
                outcome.stop_hook_active = False
                continue
            outcome.task_completed = False
            outcome.completion_blocked = True
            outcome.completion_block_reason = reason
            outcome.completion_marked_incomplete = True
            outcome.stop_hook_active = False
            incomplete_msg = owner._build_stop_incomplete_msg(reason)
            await runtime.agent.memory.add(incomplete_msg)
            yield incomplete_msg, True
            return
        outcome.stop_hook_active = False
        return
