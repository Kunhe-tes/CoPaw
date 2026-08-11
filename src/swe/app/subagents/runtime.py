# -*- coding: utf-8 -*-
"""SubAgent runtime that executes a fresh SWEAgent worker."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from agentscope.message import Msg
from pydantic import ValidationError

from ...config.config import AgentProfileConfig, ToolsConfig
from .models import (
    AgentError,
    AgentResult,
    BudgetConfig,
    DelegationSpec,
    Metrics,
    PermissionPolicy,
    SubAgentDefinition,
    SubAgentResponse,
    SubAgentRunRecord,
)
from .run_store import InMemorySubAgentRunStore

SWEAgent: Any = None
_TURN_LIMIT_RECORD_MAX_CHARS = 32_000
_RESEARCH_SYNTHESIS_FALLBACK = "Research phase ended without text output."
_RESEARCH_TURN_LIMIT_MESSAGE = (
    "SubAgent research reached its turn limit before a natural-language "
    "research synthesis was produced."
)
_STRUCTURED_FINALIZATION_MESSAGE = (
    "SubAgent structured finalization did not produce a valid response."
)


class SubAgentRuntime:
    """Run one fresh-context SubAgent and validate its compact result."""

    def __init__(self, store: InMemorySubAgentRunStore | None = None):
        self._store = store or InMemorySubAgentRunStore()

    async def run(
        self,
        *,
        run: SubAgentRunRecord,
        definition: SubAgentDefinition,
        spec: DelegationSpec,
        parent_agent_config: AgentProfileConfig,
        workspace_dir: Path,
        effective_policy: PermissionPolicy,
        request_context: dict[str, Any] | None = None,
    ) -> AgentResult:
        """Execute the SubAgent and persist terminal state."""
        started = time.monotonic()
        await self._store.mark_running(run.run_id)
        try:
            budget = self._effective_budget(definition.budget, spec.budget)
            subagent_context = self._request_context(
                request_context or {},
                run,
                effective_policy,
                budget,
            )
            agent_cls = SWEAgent
            if agent_cls is None:
                from ...agents.react_agent import SWEAgent as ImportedSWEAgent

                agent_cls = ImportedSWEAgent

            agent = agent_cls(
                agent_config=self._subagent_config(
                    parent_agent_config,
                    definition,
                    effective_policy,
                    budget,
                ),
                env_context=None,
                enable_memory_manager=False,
                mcp_clients=[],
                memory_manager=None,
                request_context=subagent_context,
                workspace_dir=workspace_dir,
                task_tracker=None,
                enable_workspace_skills=False,
                system_prompt_override=self._system_prompt(
                    definition,
                    spec,
                    effective_policy,
                    workspace_dir,
                ),
            )
            message = Msg(
                "user",
                self._delegated_task_message(spec),
                "user",
            )
            deadline = started + (budget.timeout_ms / 1000)
            research = await self._research_with_remaining_timeout(
                agent,
                message,
                deadline,
            )
            result = await self._finalize_research(
                agent=agent,
                research=research,
                spec=spec,
                run_id=run.run_id,
                definition=definition,
                deadline=deadline,
                started=started,
                request_context=subagent_context,
            )
            await self._store.finish(run.run_id, result)
            return result
        except asyncio.TimeoutError:
            result = self._failure_result(
                spec,
                run.run_id,
                "timeout",
                "SubAgent execution exceeded its timeout budget.",
                "failed",
            )
            await self._store.fail(run.run_id, result.summary, result=result)
            return result
        except Exception as exc:
            result = self._failure_result(
                spec,
                run.run_id,
                "runtime_error",
                str(exc),
                "failed",
            )
            await self._store.fail(run.run_id, str(exc), result=result)
            return result

    def _subagent_config(
        self,
        parent_agent_config: AgentProfileConfig,
        definition: SubAgentDefinition,
        effective_policy: PermissionPolicy,
        budget: BudgetConfig,
    ) -> AgentProfileConfig:
        allowed = set(definition.tools.allow) & set(
            effective_policy.tools.allow,
        )
        config = parent_agent_config.model_copy(deep=True)
        config.running.max_iters = min(
            config.running.max_iters,
            budget.max_turns,
        )
        if config.tools is None:
            config.tools = ToolsConfig()
        if config.tools is not None:
            builtin_tools = {
                name: tool.model_copy(update={"enabled": name in allowed})
                for name, tool in config.tools.builtin_tools.items()
            }
            config.tools.builtin_tools = builtin_tools
        return config

    def _request_context(
        self,
        context: dict[str, Any],
        run: SubAgentRunRecord,
        policy: PermissionPolicy,
        budget: BudgetConfig,
    ) -> dict[str, Any]:
        subagent_context = dict(context)
        for key in (
            "_skill_invocation_detector",
            "_hook_overlay_model",
            "hook_overlay",
        ):
            subagent_context.pop(key, None)
        subagent_context.update(
            {
                "agent_role": "subagent",
                "subagent_run_id": run.run_id,
                "subagent_policy": policy.model_dump(mode="json"),
                "subagent_budget": budget.model_dump(mode="json"),
                "channel": "subagent",
            },
        )
        return subagent_context

    async def _research_with_remaining_timeout(
        self,
        agent: Any,
        message: Msg,
        deadline: float,
    ) -> Any:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise asyncio.TimeoutError
        return await asyncio.wait_for(
            agent.run_research_phase(message),
            timeout=remaining,
        )

    def _effective_budget(
        self,
        definition_budget: BudgetConfig,
        spec_budget: BudgetConfig,
    ) -> BudgetConfig:
        return BudgetConfig(
            max_turns=min(
                definition_budget.max_turns,
                spec_budget.max_turns,
            ),
            max_tool_calls=min(
                definition_budget.max_tool_calls,
                spec_budget.max_tool_calls,
            ),
            timeout_ms=min(
                definition_budget.timeout_ms,
                spec_budget.timeout_ms,
            ),
        )

    def _system_prompt(
        self,
        definition: SubAgentDefinition,
        spec: DelegationSpec,
        policy: PermissionPolicy,
        workspace_dir: Path,
    ) -> str:
        return "\n\n".join(
            [
                definition.instruction,
                "Runtime safety: operate as a fresh-context readonly SubAgent. "
                "Do not mutate files, run tests, use MCP, load skills, or "
                "delegate to another SubAgent.",
                f"Workspace: {workspace_dir}",
                f"Effective allowed tools: {', '.join(policy.tools.allow)}",
                "When research is complete, reply without a tool call using "
                "a concise natural-language research synthesis. Preserve "
                "conclusions, evidence, relevant files, risks, and open "
                "questions for a later structured finalization step.",
                f"Task id: {spec.task_id}",
            ],
        )

    def _delegated_task_message(self, spec: DelegationSpec) -> str:
        return json.dumps(spec.model_dump(mode="json"), ensure_ascii=False)

    async def _finalize_research(
        self,
        *,
        agent: Any,
        research: Any,
        spec: DelegationSpec,
        run_id: str,
        definition: SubAgentDefinition,
        deadline: float,
        started: float,
        request_context: dict[str, Any],
    ) -> AgentResult:
        is_turn_limit = research.status == "turn_limit_reached"
        synthesis = self._research_synthesis(research.reply)
        context = (
            self._turn_limit_finalization_context(research, spec)
            if is_turn_limit
            else self._normal_finalization_context(spec, synthesis)
        )
        finalization_attempted = False
        try:
            if deadline <= time.monotonic():
                raise asyncio.TimeoutError
            finalization_attempted = True
            payload = await self._finalization_with_remaining_timeout(
                agent,
                context,
                definition.output_contract,
                deadline,
            )
            if payload is None:
                raise ValueError(
                    "Structured finalization metadata is missing.",
                )
        except (asyncio.TimeoutError, ValidationError, ValueError) as exc:
            return self._partial_result(
                spec=spec,
                run_id=run_id,
                definition=definition,
                summary=synthesis,
                code="structured_finalization_failed",
                message=f"{_STRUCTURED_FINALIZATION_MESSAGE} {exc}",
                turns_used=research.turns_used + int(finalization_attempted),
                tool_calls_used=self._tool_calls_used(request_context),
                elapsed_ms=self._elapsed_ms(started),
            )
        except Exception as exc:
            return self._partial_result(
                spec=spec,
                run_id=run_id,
                definition=definition,
                summary=synthesis,
                code="structured_finalization_failed",
                message=f"{_STRUCTURED_FINALIZATION_MESSAGE} {exc}",
                turns_used=research.turns_used + int(finalization_attempted),
                tool_calls_used=self._tool_calls_used(request_context),
                elapsed_ms=self._elapsed_ms(started),
            )

        errors: list[AgentError] = []
        status = "completed"
        if is_turn_limit:
            status = "partial"
            errors.append(
                AgentError(
                    code="research_turn_limit_reached",
                    message=_RESEARCH_TURN_LIMIT_MESSAGE,
                    recoverable=True,
                ),
            )
        return AgentResult(
            **payload.model_dump(),
            task_id=spec.task_id,
            agent_run_id=run_id,
            agent_name=definition.name,
            status=status,
            metrics=self._metrics(
                turns_used=research.turns_used + 1,
                tool_calls_used=self._tool_calls_used(request_context),
                elapsed_ms=self._elapsed_ms(started),
            ),
            errors=errors,
        )

    async def _finalization_with_remaining_timeout(
        self,
        agent: Any,
        context: str,
        output_contract: str,
        deadline: float,
    ) -> SubAgentResponse | None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise asyncio.TimeoutError
        return await asyncio.wait_for(
            self._finalize_once(agent, context, output_contract),
            timeout=remaining,
        )

    async def _finalize_once(
        self,
        agent: Any,
        context: str,
        output_contract: str,
    ) -> SubAgentResponse | None:
        prompt = await agent.formatter.format(
            [
                Msg(
                    "system",
                    "You are performing the terminal structured finalization "
                    "for a SubAgent. Use only the supplied research context. "
                    "Do not use tools, perform more research, or generate "
                    "runtime identity, metrics, status, or errors.\n\n"
                    f"Output contract: {output_contract}",
                    "system",
                ),
                Msg("user", context, "user"),
            ],
        )
        response = await agent.model(
            prompt,
            structured_model=SubAgentResponse,
        )
        if hasattr(response, "__aiter__"):
            last_response = None
            async for chunk in response:
                last_response = chunk
            response = last_response
        metadata = getattr(response, "metadata", None)
        if not isinstance(metadata, dict):
            return None
        payload = metadata.get("structured_output", metadata)
        return SubAgentResponse.model_validate(payload)

    def _normal_finalization_context(
        self,
        spec: DelegationSpec,
        synthesis: str,
    ) -> str:
        return json.dumps(
            {
                "delegation_spec": spec.model_dump(mode="json"),
                "research_synthesis": synthesis,
            },
            ensure_ascii=False,
        )

    def _turn_limit_finalization_context(
        self,
        research: Any,
        spec: DelegationSpec,
    ) -> str:
        return json.dumps(
            {
                "delegation_spec": spec.model_dump(mode="json"),
                "research_record": self._bounded_research_record(research),
            },
            ensure_ascii=False,
        )

    def _bounded_research_record(self, research: Any) -> str:
        messages = list(getattr(research, "messages", ()) or ())
        records: list[str] = []
        remaining = _TURN_LIMIT_RECORD_MAX_CHARS
        for message in reversed(messages):
            rendered = json.dumps(
                {
                    "name": getattr(message, "name", ""),
                    "role": getattr(message, "role", ""),
                    "content": getattr(message, "content", ""),
                },
                ensure_ascii=False,
                default=str,
            )
            if len(rendered) > remaining:
                continue
            records.append(rendered)
            remaining -= len(rendered) + 1
        return "\n".join(reversed(records))

    def _research_synthesis(self, reply: Msg | None) -> str:
        if reply is None:
            return _RESEARCH_SYNTHESIS_FALLBACK
        text = (reply.get_text_content() or "").strip()
        return text or _RESEARCH_SYNTHESIS_FALLBACK

    def _partial_result(
        self,
        *,
        spec: DelegationSpec,
        run_id: str,
        definition: SubAgentDefinition,
        summary: str,
        code: str,
        message: str,
        turns_used: int,
        tool_calls_used: int,
        elapsed_ms: int,
    ) -> AgentResult:
        return AgentResult(
            task_id=spec.task_id,
            agent_run_id=run_id,
            agent_name=definition.name,
            status="partial",
            summary=summary,
            metrics=self._metrics(
                turns_used=turns_used,
                tool_calls_used=tool_calls_used,
                elapsed_ms=elapsed_ms,
            ),
            errors=[
                AgentError(
                    code=code,
                    message=message,
                    recoverable=True,
                ),
            ],
        )

    def _metrics(
        self,
        *,
        turns_used: int,
        tool_calls_used: int,
        elapsed_ms: int,
    ) -> Metrics:
        return Metrics(
            turns_used=turns_used,
            tool_calls_used=tool_calls_used,
            elapsed_ms=elapsed_ms,
        )

    def _elapsed_ms(self, started: float) -> int:
        return int((time.monotonic() - started) * 1000)

    def _tool_calls_used(self, request_context: dict[str, Any]) -> int:
        try:
            return int(request_context.get("_subagent_tool_calls_used") or 0)
        except (TypeError, ValueError):
            return 0

    def _failure_result(
        self,
        spec: DelegationSpec,
        run_id: str,
        code: str,
        message: str,
        status: str,
    ) -> AgentResult:
        return AgentResult(
            task_id=spec.task_id,
            agent_run_id=run_id,
            agent_name=spec.name,
            status=status,
            summary=message,
            metrics=Metrics(),
            errors=[
                AgentError(
                    code=code,
                    message=message,
                    recoverable=status == "partial",
                ),
            ],
        )
