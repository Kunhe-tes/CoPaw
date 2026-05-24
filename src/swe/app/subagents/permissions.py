# -*- coding: utf-8 -*-
"""SubAgent effective permission composition and tool authorization."""

from __future__ import annotations

import re

from .models import (
    MVP_READONLY_TOOLS,
    PermissionPolicy,
    PermissionTools,
    ShellPolicy,
    ToolAuthorizationDecision,
)


def compose_effective_policy(
    parent: PermissionPolicy,
    subagent: PermissionPolicy,
    runtime: PermissionPolicy,
    workspace: PermissionPolicy,
) -> PermissionPolicy:
    """Intersect policies with deny precedence."""
    policies = [parent, subagent, runtime, workspace]
    allow = set(policies[0].tools.allow)
    for policy in policies[1:]:
        allow &= set(policy.tools.allow)
    deny = set().union(*(set(policy.tools.deny) for policy in policies))
    allow -= deny
    allowed_commands = set(policies[0].shell.allowed_commands)
    denied_patterns = set()
    for policy in policies:
        allowed_commands &= set(policy.shell.allowed_commands)
        denied_patterns.update(policy.shell.denied_patterns)
    return PermissionPolicy(
        tools=PermissionTools(allow=sorted(allow), deny=sorted(deny)),
        shell=ShellPolicy(
            enabled=all(policy.shell.enabled for policy in policies),
            strategy="allowlist",
            allowed_commands=sorted(allowed_commands),
            denied_patterns=sorted(denied_patterns),
        ),
    )


def validate_tool_call(
    policy: PermissionPolicy,
    tool_name: str,
    tool_input: dict,
) -> ToolAuthorizationDecision:
    """Authorize one tool call against an effective SubAgent policy."""
    if tool_name not in set(policy.tools.allow):
        return ToolAuthorizationDecision(
            allowed=False,
            reason=f"tool `{tool_name}` is not allowed",
        )
    if tool_name in set(policy.tools.deny):
        return ToolAuthorizationDecision(
            allowed=False,
            reason=f"tool `{tool_name}` is explicitly denied",
        )
    if tool_name == "execute_shell_command":
        return _validate_shell(policy, tool_input)
    if tool_name not in MVP_READONLY_TOOLS:
        return ToolAuthorizationDecision(
            allowed=False,
            reason=f"tool `{tool_name}` is outside readonly MVP allowlist",
        )
    return ToolAuthorizationDecision(allowed=True)


def _extract_command(tool_input: dict) -> str:
    command = tool_input.get("command")
    if command is None:
        command = tool_input.get("cmd")
    return str(command or "").strip()


def _validate_shell(
    policy: PermissionPolicy,
    tool_input: dict,
) -> ToolAuthorizationDecision:
    command = _extract_command(tool_input)
    if not policy.shell.enabled:
        return ToolAuthorizationDecision(
            allowed=False,
            reason="shell is disabled",
        )
    if not command:
        return ToolAuthorizationDecision(
            allowed=False,
            reason="missing shell command",
        )
    normalized = f" {command.lower()} "
    for pattern in policy.shell.denied_patterns:
        if pattern in command or pattern.lower() in normalized:
            return ToolAuthorizationDecision(
                allowed=False,
                reason=f"shell command denied by pattern `{pattern}`",
            )
    if re.search(r"(^|\\s)(pytest|npm\\s+test|coverage)(\\s|$)", normalized):
        return ToolAuthorizationDecision(
            allowed=False,
            reason="test execution is deferred for readonly SubAgents",
        )
    for prefix in policy.shell.allowed_commands:
        prefix = prefix.lower()
        if normalized.strip() == prefix or normalized.strip().startswith(
            prefix + " ",
        ):
            return ToolAuthorizationDecision(allowed=True)
    return ToolAuthorizationDecision(
        allowed=False,
        reason="shell command is not in the readonly allowlist",
    )
