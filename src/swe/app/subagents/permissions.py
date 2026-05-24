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
    shell_operator = _denied_shell_operator(command)
    if shell_operator is not None:
        return ToolAuthorizationDecision(
            allowed=False,
            reason=f"shell command denied by operator `{shell_operator}`",
        )
    normalized = f" {command.lower()} "
    if _uses_output_option(normalized):
        return ToolAuthorizationDecision(
            allowed=False,
            reason="shell command denied by output option",
        )
    if _uses_external_execution_option(normalized):
        return ToolAuthorizationDecision(
            allowed=False,
            reason="shell command denied by external execution option",
        )
    if _uses_sed_in_place(normalized):
        return ToolAuthorizationDecision(
            allowed=False,
            reason="sed write or execute expressions are denied",
        )
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


def _denied_shell_operator(command: str) -> str | None:
    """Return a shell operator that can sequence, pipe, or redirect work."""
    for operator in ("&&", "||", ";", "|", "&", "`", "$(", "\n", "\r", "<"):
        if operator in command:
            return operator
    return None


def _uses_output_option(normalized_command: str) -> bool:
    return re.search(r"(^|\s)--output(=|\s)", normalized_command) is not None


def _uses_external_execution_option(normalized_command: str) -> bool:
    return any(
        re.search(pattern, normalized_command) is not None
        for pattern in (
            r"(^|\s)--pre(=|\s)",
            r"(^|\s)--ext-diff(\s|$)",
            r"(^|\s)--textconv(\s|$)",
        )
    )


def _uses_sed_in_place(normalized_command: str) -> bool:
    parts = normalized_command.strip().split()
    return bool(
        parts
        and parts[0] == "sed"
        and (
            any(part.startswith("-i") for part in parts[1:])
            or "--in-place" in parts[1:]
            or re.search(
                r"(^|[\s,;{'])\d*(,\d*)?[we]\s",
                normalized_command,
            )
            is not None
            or re.search(
                r"(^|[\s,;{'])s(.+)[we](['\s]|$)",
                normalized_command,
            )
            is not None
        ),
    )
