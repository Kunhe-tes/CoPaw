# -*- coding: utf-8 -*-
"""Delegation manager for main-agent to SubAgent calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...config.config import AgentProfileConfig
from .builtins import builtin_definition_provider
from .models import AgentError, AgentResult, DelegationSpec, PermissionPolicy
from .permissions import compose_effective_policy
from .registry import AgentRegistry
from .run_store import InMemorySubAgentRunStore
from .runtime import SubAgentRuntime


class DelegationManager:
    """Validate caller context, record lifecycle, and invoke runtime."""

    def __init__(
        self,
        *,
        registry: AgentRegistry | None = None,
        store: InMemorySubAgentRunStore | None = None,
        runtime: SubAgentRuntime | Any | None = None,
    ):
        self._registry = registry or AgentRegistry(
            [builtin_definition_provider()],
        )
        self._store = store or InMemorySubAgentRunStore()
        self._runtime = runtime or SubAgentRuntime(store=self._store)

    async def delegate(
        self,
        *,
        spec: DelegationSpec,
        parent_agent_config: AgentProfileConfig,
        workspace_dir: Path,
        parent_policy: PermissionPolicy | None = None,
        workspace_policy: PermissionPolicy | None = None,
        runtime_policy: PermissionPolicy | None = None,
        request_context: dict[str, Any] | None = None,
    ) -> AgentResult:
        """Run a named SubAgent or return a structured failure."""
        if (request_context or {}).get("agent_role") == "subagent":
            return self._blocked(spec, "Nested delegation is not allowed.")
        try:
            definition = self._registry.resolve(spec.agent_name)
        except KeyError:
            return self._failed(spec, f"Unknown SubAgent: {spec.agent_name}")
        effective_policy = compose_effective_policy(
            parent_policy or PermissionPolicy.readonly(),
            definition.permission,
            runtime_policy or PermissionPolicy.readonly(),
            workspace_policy or PermissionPolicy.readonly(),
        )
        run = await self._store.create(spec, definition, effective_policy)
        return await self._runtime.run(
            run=run,
            definition=definition,
            spec=spec,
            parent_agent_config=parent_agent_config,
            workspace_dir=workspace_dir,
            effective_policy=effective_policy,
            request_context=request_context or {},
        )

    def _failed(self, spec: DelegationSpec, message: str) -> AgentResult:
        return AgentResult(
            task_id=spec.task_id,
            agent_run_id="",
            agent_name=spec.agent_name,
            status="failed",
            summary=message,
            errors=[
                AgentError(code="delegation_error", message=message),
            ],
        )

    def _blocked(self, spec: DelegationSpec, message: str) -> AgentResult:
        return AgentResult(
            task_id=spec.task_id,
            agent_run_id="",
            agent_name=spec.agent_name,
            status="blocked",
            summary=message,
            errors=[
                AgentError(code="nested_delegation", message=message),
            ],
        )
