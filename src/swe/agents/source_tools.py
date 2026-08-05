# -*- coding: utf-8 -*-
"""Tenant-executed adapters for source-owned built-in tool versions."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import signal
import sys
import tempfile
from typing import Any, Awaitable, Callable

from agentscope.tool import ToolResponse

from swe.app.source_tools.models import SourceToolVersion
from swe.envs.runtime import load_tenant_runtime_env
from swe.security.process_limits import resolve_current_process_limit_policy
from swe.tracing.sanitizer import (
    register_sensitive_values,
    sanitize_dict,
    sanitize_string,
)

from .tools.shell import _tenant_shell_execution_slot

from .tool_failure import build_failed_tool_response

logger = logging.getLogger(__name__)

SOURCE_TOOL_TIMEOUT_SECONDS = 60
SOURCE_TOOL_TERMINATION_GRACE_SECONDS = 1
_MAX_RESULT_BYTES = 50 * 1024
_SAFE_INHERITED_ENV_KEYS = ("PATH", "HOME", "SHELL")

_WORKER = r"""
import asyncio
import contextlib
import io
import json
import runpy
import sys

payload = json.loads(sys.stdin.read())
namespace = runpy.run_path(payload["script_path"])
entry = namespace.get("execute")
if entry is None:
    raise RuntimeError("source tool entrypoint is unavailable")
captured_stdout = io.StringIO()
with contextlib.redirect_stdout(captured_stdout):
    result = asyncio.run(entry(payload["arguments"], payload["context"]))
json.dumps(result)
sys.stdout.write(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
"""


@dataclass(frozen=True)
class SourceToolRuntime:
    """Tenant-bound invocation context captured while the Agent is created."""

    tenant_id: str | None
    source_id: str | None
    workspace_dir: Path
    agent_id: str | None = None


class SourceToolConfigurationError(RuntimeError):
    """Raised when a tool's declared tenant credential is unavailable."""


def source_tool_runtime_env(
    *,
    required_env: tuple[str, ...],
    tenant_id: str | None,
    source_id: str | None,
) -> dict[str, str]:
    """Build a subprocess env with safe process keys plus declared tenant values."""
    tenant_env = load_tenant_runtime_env(
        tenant_id=tenant_id,
        source_id=source_id,
        allow_missing_context=False,
    )
    missing = [key for key in required_env if not tenant_env.get(key)]
    if missing:
        raise SourceToolConfigurationError(
            "missing declared tenant environment values: "
            + ", ".join(missing),
        )
    env = {
        key: os.environ[key]
        for key in _SAFE_INHERITED_ENV_KEYS
        if key in os.environ
    }
    env.update({key: tenant_env[key] for key in required_env})
    register_sensitive_values(env[key] for key in required_env)
    return env


def build_source_tool_function(
    version: SourceToolVersion,
    runtime: SourceToolRuntime,
) -> Callable[..., Awaitable[ToolResponse]]:
    """Create the AgentScope-compatible async adapter for one catalog snapshot."""

    async def _source_tool(**arguments: Any) -> ToolResponse:
        try:
            result = await _run_source_tool(version, runtime, arguments)
        except SourceToolConfigurationError as exc:
            _record_source_tool_invocation(
                runtime,
                version,
                "configuration_error",
            )
            return build_failed_tool_response(
                error_type="source_tool_configuration_error",
                detail=str(exc),
            )
        except asyncio.TimeoutError:
            _record_source_tool_invocation(runtime, version, "timeout")
            return build_failed_tool_response(
                error_type="tool_timeout",
                detail="Source tool exceeded the 60 second execution limit.",
            )
        except Exception:  # noqa: BLE001
            _record_source_tool_invocation(runtime, version, "failed")
            return build_failed_tool_response(
                error_type="source_tool_runtime_error",
                detail="Source tool execution failed.",
            )
        _record_source_tool_invocation(runtime, version, "succeeded")
        return ToolResponse(content=_sanitize_source_tool_result(result))

    _source_tool.__name__ = version.name
    _source_tool.__doc__ = version.description
    return _source_tool


async def _run_source_tool(
    version: SourceToolVersion,
    runtime: SourceToolRuntime,
    arguments: dict[str, Any],
) -> Any:
    workspace_dir = runtime.workspace_dir.resolve()
    workspace_dir.mkdir(parents=True, exist_ok=True)
    env = source_tool_runtime_env(
        required_env=version.required_env,
        tenant_id=runtime.tenant_id,
        source_id=runtime.source_id,
    )
    context = {
        "tenant_id": runtime.tenant_id,
        "source_id": runtime.source_id,
        "workspace_dir": str(workspace_dir),
        "tool_name": version.name,
        "tool_version": version.version,
    }
    process_limit_policy = resolve_current_process_limit_policy("shell")
    with tempfile.TemporaryDirectory(
        dir=workspace_dir,
        prefix=".source-tool-",
    ) as stage:
        stage_dir = Path(stage)
        script_path = stage_dir / "tool.py"
        script_path.write_text(version.script, encoding="utf-8")
        payload = json.dumps(
            {
                "script_path": str(script_path),
                "arguments": arguments,
                "context": context,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        from swe.security.python_runtime_path_guard import (
            prepare_python_runtime_path_guard_env,
        )

        async with _tenant_shell_execution_slot(process_limit_policy):
            with ExitStack() as guards:
                path_guard = guards.enter_context(
                    prepare_python_runtime_path_guard_env(
                        env,
                        tenant_root=workspace_dir,
                        base_dir=workspace_dir,
                    ),
                )
                del path_guard
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-c",
                    _WORKER,
                    cwd=workspace_dir,
                    env=env,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    start_new_session=True,
                    preexec_fn=process_limit_policy.build_preexec_fn(),
                )
                try:
                    stdout, _ = await asyncio.wait_for(
                        process.communicate(payload),
                        timeout=SOURCE_TOOL_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    await _terminate_source_tool_process(process)
                    try:
                        await asyncio.wait_for(
                            process.communicate(),
                            timeout=SOURCE_TOOL_TERMINATION_GRACE_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        pass
                    raise
        if process.returncode != 0:
            raise RuntimeError("source tool process failed")
        if len(stdout) > _MAX_RESULT_BYTES:
            raise RuntimeError("source tool result exceeds output boundary")
        decoded = json.loads(stdout.decode("utf-8"))
        if not decoded.get("ok"):
            raise RuntimeError("source tool returned an invalid response")
        return decoded["result"]


async def _terminate_source_tool_process(
    process: asyncio.subprocess.Process,
) -> None:
    """Terminate then force-kill a timed-out dedicated subprocess group."""
    if process.returncode is not None:
        return
    sent_term = False
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
            sent_term = True
        except ProcessLookupError:
            return
    else:
        process.terminate()
        sent_term = True
    if not sent_term:
        return
    try:
        await asyncio.wait_for(
            process.wait(),
            timeout=SOURCE_TOOL_TERMINATION_GRACE_SECONDS,
        )
        return
    except asyncio.TimeoutError:
        pass
    if process.returncode is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(
            process.wait(),
            timeout=SOURCE_TOOL_TERMINATION_GRACE_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("source tool process did not exit after SIGKILL")


def _record_source_tool_invocation(
    runtime: SourceToolRuntime,
    version: SourceToolVersion,
    result: str,
) -> None:
    """Write non-sensitive source/version attribution without affecting calls."""
    if not runtime.source_id:
        return
    try:
        from swe.app.source_tools.service import get_source_tool_service

        service = get_source_tool_service()
        if service is not None:
            service.record_invocation(
                source_id=runtime.source_id,
                tool=version,
                tenant_id=runtime.tenant_id,
                agent_id=runtime.agent_id,
                result=result,
            )
    except Exception:  # noqa: BLE001
        # Observability must never change a tool call's execution result.
        return


def _sanitize_source_tool_result(value: Any) -> Any:
    """Apply Swe's ordinary redaction and bounded-output policy to JSON output."""
    if isinstance(value, dict):
        return sanitize_dict(value)
    if isinstance(value, list):
        return [_sanitize_source_tool_result(item) for item in value]
    if isinstance(value, str):
        return sanitize_string(value)
    return value
