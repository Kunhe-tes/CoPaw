# -*- coding: utf-8 -*-
"""Stored and run-scoped SubAgent definition service."""

from __future__ import annotations

from typing import Any

from .definition_store import SubAgentDefinitionStore
from .matcher import DefinitionMatchResult, SubAgentDefinitionMatcher
from .models import (
    BudgetConfig,
    SubAgentDefinition,
    SubAgentRegistrationRequest,
    SubAgentStartRequest,
)
from .registry import AgentRegistry

DEFAULT_OUTPUT_CONTRACT = "Return only valid AgentResult JSON."
MIN_REGISTRATION_MAX_TURNS = 1
MIN_REGISTRATION_MAX_TOOL_CALLS = 0
MIN_REGISTRATION_TIMEOUT_MS = 1000
RUN_SCOPED_DESCRIPTION_MAX_BYTES = 1024


def _truncate_utf8(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


class SubAgentDefinitionService:
    """Normalize, validate, register, and build SubAgent definitions."""

    def __init__(
        self,
        *,
        store: SubAgentDefinitionStore,
        builtin_registry: AgentRegistry,
        owner_scope: str = "stored",
        matcher: SubAgentDefinitionMatcher | None = None,
    ):
        self._store = store
        self._builtin_registry = builtin_registry
        self._owner_scope = owner_scope
        self._matcher = matcher or SubAgentDefinitionMatcher()

    def register(self, request: SubAgentRegistrationRequest) -> dict[str, Any]:
        """Upsert a stored definition unless it conflicts with a builtin."""
        if self._builtin_name_exists(request.name):
            return {
                "status": "failed",
                "reason": "builtin_name_conflict",
                "name": request.name,
            }
        definition = self.build_stored_definition(request)
        result = self._store.upsert(definition)
        return {
            "status": "registered" if result.created else "updated",
            "name": definition.name,
        }

    def build_stored_definition(
        self,
        request: SubAgentRegistrationRequest,
    ) -> SubAgentDefinition:
        """Build a validated stored definition from registration input."""
        self._validate_budget(request.budget)
        return SubAgentDefinition.model_validate(
            {
                "name": request.name,
                "source": "stored",
                "owner_scope": self._owner_scope,
                "enabled": request.enabled,
                "nickname": request.nickname,
                "description": request.description,
                "instruction": request.instruction,
                "output_contract": (
                    request.output_contract or DEFAULT_OUTPUT_CONTRACT
                ),
                "trigger_keywords": request.trigger_keywords,
                "task_types": request.task_types,
                "priority": request.priority,
                "budget": request.budget.model_dump(mode="json"),
            },
        )

    def build_run_scoped_definition(
        self,
        request: SubAgentStartRequest,
        *,
        owner_scope: str,
    ) -> SubAgentDefinition:
        """Build a definition that is valid only for one SubAgent run."""
        return SubAgentDefinition.model_validate(
            {
                "name": request.name,
                "version": "run-scoped",
                "source": "run_scoped",
                "owner_scope": owner_scope,
                "description": _truncate_utf8(
                    request.objective,
                    RUN_SCOPED_DESCRIPTION_MAX_BYTES,
                ),
                "instruction": request.instruction,
                "output_contract": DEFAULT_OUTPUT_CONTRACT,
                "budget": BudgetConfig().model_dump(mode="json"),
            },
        )

    def list_available_definitions(self) -> list[SubAgentDefinition]:
        """Return enabled stored and built-in definitions."""
        return [
            definition
            for definition in (
                self._store.list_definitions() + self._builtin_registry.list()
            )
            if definition.enabled
        ]

    def match_start_request(
        self,
        request: SubAgentStartRequest,
    ) -> DefinitionMatchResult | None:
        """Match a compact start request against reusable definitions."""
        return self._matcher.match(request, self.list_available_definitions())

    def _builtin_name_exists(self, name: str) -> bool:
        return any(
            definition.name == name
            for definition in self._builtin_registry.list(source="builtin")
        )

    def _validate_budget(self, budget: BudgetConfig) -> None:
        defaults = BudgetConfig()
        if budget.max_turns < MIN_REGISTRATION_MAX_TURNS:
            raise ValueError("max_turns cannot be below minimum")
        if budget.max_turns > defaults.max_turns:
            raise ValueError("max_turns cannot exceed default")
        if budget.max_tool_calls < MIN_REGISTRATION_MAX_TOOL_CALLS:
            raise ValueError("max_tool_calls cannot be below minimum")
        if budget.max_tool_calls > defaults.max_tool_calls:
            raise ValueError("max_tool_calls cannot exceed default")
        if budget.timeout_ms < MIN_REGISTRATION_TIMEOUT_MS:
            raise ValueError("timeout_ms cannot be below minimum")
        if budget.timeout_ms > defaults.timeout_ms:
            raise ValueError("timeout_ms cannot exceed default")
