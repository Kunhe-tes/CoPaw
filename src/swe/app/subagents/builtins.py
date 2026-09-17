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
            "trigger_keywords": trigger_keywords or [],
            "priority": 100,
        },
    )


def builtin_definition_provider() -> InMemoryDefinitionProvider:
    """Return the immutable MVP built-in SubAgent definition provider."""
    return InMemoryDefinitionProvider(
        [],
    )
