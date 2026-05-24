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
    DelegationSpec,
    Metrics,
    PermissionPolicy,
    SubAgentDefinition,
    SubAgentRunRecord,
)
from .run_store import InMemorySubAgentRunStore

SWEAgent: Any = None


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
            agent_cls = SWEAgent
            if agent_cls is None:
                from ...agents.react_agent import SWEAgent as ImportedSWEAgent

                agent_cls = ImportedSWEAgent

            agent = agent_cls(
                agent_config=self._subagent_config(
                    parent_agent_config,
                    definition,
                ),
                env_context=None,
                enable_memory_manager=False,
                mcp_clients=[],
                memory_manager=None,
                request_context=self._request_context(
                    request_context or {},
                    run,
                    effective_policy,
                ),
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
            reply = await asyncio.wait_for(
                agent.reply(message, structured_model=AgentResult),
                timeout=definition.budget.timeout_ms / 1000,
            )
            result = self._coerce_result(
                reply,
                spec=spec,
                run_id=run.run_id,
                definition=definition,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            if result is None:
                repair = await agent.reply(
                    Msg(
                        "user",
                        "Return the previous answer as valid AgentResult JSON.",
                        "user",
                    ),
                    structured_model=AgentResult,
                )
                result = self._coerce_result(
                    repair,
                    spec=spec,
                    run_id=run.run_id,
                    definition=definition,
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                )
            if result is None:
                result = self._failure_result(
                    spec,
                    run.run_id,
                    "invalid_output",
                    "SubAgent output was not valid AgentResult JSON.",
                    "partial",
                )
            await self._store.finish(run.run_id, result)
            return result
        except Exception as exc:
            result = self._failure_result(
                spec,
                run.run_id,
                "runtime_error",
                str(exc),
                "failed",
            )
            await self._store.fail(run.run_id, str(exc))
            return result

    def _subagent_config(
        self,
        parent_agent_config: AgentProfileConfig,
        definition: SubAgentDefinition,
    ) -> AgentProfileConfig:
        allowed = set(definition.tools.allow)
        config = parent_agent_config.model_copy(deep=True)
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
                "channel": "subagent",
            },
        )
        return subagent_context

    def _system_prompt(
        self,
        definition: SubAgentDefinition,
        spec: DelegationSpec,
        policy: PermissionPolicy,
        workspace_dir: Path,
    ) -> str:
        return "\n\n".join(
            [
                definition.prompt.system,
                "Runtime safety: operate as a fresh-context readonly SubAgent. "
                "Do not mutate files, run tests, use MCP, load skills, or "
                "delegate to another SubAgent.",
                f"Workspace: {workspace_dir}",
                f"Effective allowed tools: {', '.join(policy.tools.allow)}",
                definition.prompt.output_contract,
                f"Task id: {spec.task_id}",
            ],
        )

    def _delegated_task_message(self, spec: DelegationSpec) -> str:
        return json.dumps(spec.model_dump(mode="json"), ensure_ascii=False)

    def _coerce_result(
        self,
        reply: Msg,
        *,
        spec: DelegationSpec,
        run_id: str,
        definition: SubAgentDefinition,
        elapsed_ms: int,
    ) -> AgentResult | None:
        text = reply.get_text_content()
        try:
            data = json.loads(text)
            result = AgentResult.model_validate(data)
        except (TypeError, json.JSONDecodeError, ValidationError):
            return None
        return result.model_copy(
            update={
                "task_id": spec.task_id,
                "agent_run_id": run_id,
                "agent_name": definition.name,
                "metrics": result.metrics.model_copy(
                    update={"elapsed_ms": elapsed_ms},
                ),
            },
        )

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
            agent_name=spec.agent_name,
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
