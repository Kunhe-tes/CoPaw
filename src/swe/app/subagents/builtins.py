# -*- coding: utf-8 -*-
"""Built-in readonly SubAgent definitions."""

from __future__ import annotations

from .models import PermissionPolicy, SubAgentDefinition
from .registry import InMemoryDefinitionProvider


def _builtin(
    *,
    name: str,
    description: str,
    instruction: str,
    task_types: list[str],
    trigger_keywords: list[str] | None = None,
) -> SubAgentDefinition:
    return SubAgentDefinition.model_validate(
        {
            "name": name,
            "version": "1.0.0",
            "source": "builtin",
            "owner_scope": "builtin",
            "description": description,
            "role": "researcher",
            "instruction": instruction,
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
            "task_types": task_types,
            "trigger_keywords": trigger_keywords or [],
            "priority": 100,
        },
    )


def builtin_definition_provider() -> InMemoryDefinitionProvider:
    """Return the immutable MVP built-in SubAgent definition provider."""
    return InMemoryDefinitionProvider(
        [
            _builtin(
                name="plan-researcher",
                description="Readonly repository researcher for planning.",
                instruction=(
                    "You are a readonly planning researcher. Gather facts, "
                    "cite files or commands, and do not modify workspace state."
                ),
                task_types=["planning", "research"],
                trigger_keywords=["plan", "planning", "research"],
            ),
            _builtin(
                name="research-analyst",
                description="Readonly analyst for research tasks.",
                instruction=(
                    "You are a readonly research analyst. Break down the "
                    "question, gather available context, and return a concise "
                    "evidence-based final summary."
                ),
                task_types=["research", "analysis"],
                trigger_keywords=["research", "analysis", "analyze"],
            ),
            _builtin(
                name="risk-reviewer",
                description="Readonly reviewer for implementation risk.",
                instruction=(
                    "You are a readonly risk reviewer. Identify regressions, "
                    "security concerns, and missing safeguards with evidence."
                ),
                task_types=["risk", "review"],
                trigger_keywords=["risk", "review", "regression"],
            ),
            _builtin(
                name="test-surface-analyzer",
                description="Readonly analyzer for relevant test coverage.",
                instruction=(
                    "You are a readonly test-surface analyzer. Identify tests "
                    "to run or add, but do not execute test commands."
                ),
                task_types=["tests", "verification"],
                trigger_keywords=["test", "tests", "verification"],
            ),
        ],
    )
