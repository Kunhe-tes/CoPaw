# -*- coding: utf-8 -*-
"""Built-in readonly SubAgent definitions."""

from __future__ import annotations

from .models import PermissionPolicy, SubAgentDefinition
from .registry import InMemoryDefinitionProvider


def _builtin(
    *,
    name: str,
    description: str,
    system_prompt: str,
    task_types: list[str],
) -> SubAgentDefinition:
    return SubAgentDefinition.model_validate(
        {
            "name": name,
            "version": "1.0.0",
            "source": "builtin",
            "owner_scope": "builtin",
            "description": description,
            "role": "researcher",
            "prompt": {
                "system": system_prompt,
                "output_contract": "Return only valid AgentResult JSON.",
            },
            "tools": {
                "allow": [
                    "execute_shell_command",
                    "read_file",
                    "grep_search",
                    "glob_search",
                    "get_current_time",
                ],
            },
            "permission": PermissionPolicy.readonly().model_dump(
                mode="json",
            ),
            "isolation": {
                "context": "fresh",
                "workspace": "shared",
                "memory": "none",
                "skills_enabled": False,
                "mcp_enabled": False,
            },
            "lifecycle": {
                "resumable": False,
                "cancellable": True,
                "allow_nested_delegation": False,
            },
            "routing": {"task_types": task_types, "priority": 100},
        },
    )


def builtin_definition_provider() -> InMemoryDefinitionProvider:
    """Return the immutable MVP built-in SubAgent definition provider."""
    return InMemoryDefinitionProvider(
        [
            _builtin(
                name="plan-researcher",
                description="Readonly repository researcher for planning.",
                system_prompt=(
                    "You are a readonly planning researcher. Gather facts, "
                    "cite files or commands, and do not modify workspace state."
                ),
                task_types=["planning", "research"],
            ),
            _builtin(
                name="risk-reviewer",
                description="Readonly reviewer for implementation risk.",
                system_prompt=(
                    "You are a readonly risk reviewer. Identify regressions, "
                    "security concerns, and missing safeguards with evidence."
                ),
                task_types=["risk", "review"],
            ),
            _builtin(
                name="test-surface-analyzer",
                description="Readonly analyzer for relevant test coverage.",
                system_prompt=(
                    "You are a readonly test-surface analyzer. Identify tests "
                    "to run or add, but do not execute test commands."
                ),
                task_types=["tests", "verification"],
            ),
        ],
    )
