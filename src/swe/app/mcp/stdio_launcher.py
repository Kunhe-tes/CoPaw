# -*- coding: utf-8 -*-
"""Tenant-aware MCP stdio launcher with optional process limits."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
import sys
from typing import Sequence

from swe.envs.runtime import build_runtime_env
from swe.security.process_limits import resolve_current_process_limit_policy

try:
    import resource
except ImportError:  # pragma: no cover - non-Unix import guard
    resource = None  # type: ignore[assignment]


_WRAPPER_ONLY_DROP_ENV_KEYS = "SWE_STDIO_LAUNCHER_DROP_ENV_KEYS"
_WRAPPER_PRESERVED_BOUNDARY_KEYS = frozenset({"PYTHONPATH"})


@dataclass(frozen=True)
class TenantAwareStdioLaunchConfig:
    """Effective stdio launch config after tenant policy resolution."""

    command: str
    args: list[str]
    env: dict[str, str]
    cwd: str | None
    launch_command: str
    launch_args: list[str]
    diagnostic: str | None


def build_tenant_aware_stdio_launch_config(
    command: str,
    args: Sequence[str] | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> TenantAwareStdioLaunchConfig:
    """Build the effective stdio launch command for the current tenant."""
    original_args = list(args or [])
    launch_command = command
    launch_args = list(original_args)
    policy = resolve_current_process_limit_policy("mcp_stdio")

    if policy.should_enforce:
        launch_command = sys.executable
        launch_args = ["-m", "swe.app.mcp.stdio_launcher"]
        if policy.cpu_time_limit_seconds is not None:
            launch_args.extend(
                [
                    "--cpu-time-limit-seconds",
                    str(policy.cpu_time_limit_seconds),
                ],
            )
        if policy.memory_max_bytes is not None:
            launch_args.extend(
                ["--memory-max-bytes", str(policy.memory_max_bytes)],
            )
        launch_args.extend(["--", command, *original_args])

    runtime_env = build_runtime_env(
        call_env=env or {},
        preserve_boundary_env_keys=(
            _WRAPPER_PRESERVED_BOUNDARY_KEYS
            if policy.should_enforce
            else frozenset()
        ),
    )
    if policy.should_enforce:
        runtime_env[_WRAPPER_ONLY_DROP_ENV_KEYS] = os.pathsep.join(
            sorted(_WRAPPER_PRESERVED_BOUNDARY_KEYS),
        )

    return TenantAwareStdioLaunchConfig(
        command=command,
        args=original_args,
        env=runtime_env,
        cwd=cwd,
        launch_command=launch_command,
        launch_args=launch_args,
        diagnostic=policy.diagnostic,
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply tenant process limits before exec'ing an MCP server.",
    )
    parser.add_argument("--cpu-time-limit-seconds", type=int, default=None)
    parser.add_argument("--memory-max-bytes", type=int, default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args(list(argv or ()))


def main(argv: Sequence[str] | None = None) -> None:
    """Apply configured rlimits and exec the target MCP server command."""
    parsed = _parse_args(argv)
    command_parts = list(parsed.command)
    if command_parts and command_parts[0] == "--":
        command_parts = command_parts[1:]
    if not command_parts:
        raise SystemExit("missing MCP server command")

    if resource is not None:
        if parsed.cpu_time_limit_seconds is not None:
            resource.setrlimit(
                resource.RLIMIT_CPU,
                (
                    parsed.cpu_time_limit_seconds,
                    parsed.cpu_time_limit_seconds,
                ),
            )
        if parsed.memory_max_bytes is not None:
            resource.setrlimit(
                resource.RLIMIT_AS,
                (parsed.memory_max_bytes, parsed.memory_max_bytes),
            )

    command = command_parts[0]
    exec_env = os.environ.copy()
    drop_keys = exec_env.pop(_WRAPPER_ONLY_DROP_ENV_KEYS, "")
    for key in drop_keys.split(os.pathsep):
        if key:
            exec_env.pop(key, None)
    os.execvpe(command, command_parts, exec_env)


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
