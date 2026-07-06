# -*- coding: utf-8 -*-
"""Main-process supervisor for Background SubAgent subprocess runs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from ...config.config import AgentProfileConfig
from .builtins import builtin_definition_provider
from .models import (
    BackgroundSubAgentRunRecord,
    BudgetConfig,
    DelegationSpec,
    DefinitionMatchMetadata,
    PermissionPolicy,
    SubAgentDefinition,
    SubAgentStartRequest,
    TERMINAL_BACKGROUND_RUN_STATUSES,
    WorkerLaunchSpec,
)
from .nicknames import assign_subagent_nickname
from .permissions import compose_effective_policy
from .registry import AgentRegistry
from .run_store import PerRunSubAgentRunStore

_CONCURRENCY_LIMIT_REASON = "background_subagent_concurrency_limit"
_WORKER_EXITED_WITHOUT_RESULT = "worker_exited_without_result"


def _effective_budget(
    definition_budget: BudgetConfig,
    spec_budget: BudgetConfig,
) -> BudgetConfig:
    return BudgetConfig(
        max_turns=min(definition_budget.max_turns, spec_budget.max_turns),
        max_tool_calls=min(
            definition_budget.max_tool_calls,
            spec_budget.max_tool_calls,
        ),
        timeout_ms=min(definition_budget.timeout_ms, spec_budget.timeout_ms),
    )


class BackgroundSubAgentScope(BaseModel):
    """Current tenant-and-agent scope for Background SubAgent operations."""

    tenant_id: str
    agent_id: str
    run_store_dir: Path


class BackgroundSubAgentStartBlocked(BaseModel):
    """Response returned when per-scope concurrency is exhausted."""

    status: Literal["blocked"] = "blocked"
    reason: str = _CONCURRENCY_LIMIT_REASON
    limit: int
    active_run_ids: list[str] = Field(default_factory=list)


class BackgroundSubAgentNotManageable(BaseModel):
    """Response for a known run without an active supervisor handle."""

    status: Literal["not_manageable"] = "not_manageable"
    run_id: str
    reason: str = "background_subagent_run_not_manageable"


class BackgroundSubAgentWaitSnapshot(BaseModel):
    """Bounded wait result for currently manageable background runs."""

    active_runs: list[BackgroundSubAgentRunRecord] = Field(
        default_factory=list,
    )
    terminal_runs: list[BackgroundSubAgentRunRecord] = Field(
        default_factory=list,
    )
    timed_out: bool = False


@dataclass
class _ActiveRun:
    scope: BackgroundSubAgentScope
    process: Any
    stderr_log_path: Path


class BackgroundSubAgentSupervisor:
    """Supervise active Background SubAgent worker subprocesses."""

    def __init__(
        self,
        *,
        max_running_per_scope: int = 2,
        registry: AgentRegistry | None = None,
        popen_factory: Any | None = None,
        cancel_grace_seconds: float = 1.0,
    ):
        self._max_running_per_scope = max_running_per_scope
        self._registry = registry or AgentRegistry(
            [builtin_definition_provider()],
        )
        self._popen_factory = popen_factory or subprocess.Popen
        self._cancel_grace_seconds = cancel_grace_seconds
        self._active: dict[tuple[str, str], dict[str, _ActiveRun]] = {}

    async def start(
        self,
        *,
        scope: BackgroundSubAgentScope,
        spec: DelegationSpec,
        parent_agent_config: AgentProfileConfig,
        workspace_dir: Path,
        parent_policy: PermissionPolicy | None = None,
        workspace_policy: PermissionPolicy | None = None,
        runtime_policy: PermissionPolicy | None = None,
        request_context: dict[str, Any] | None = None,
        definition: SubAgentDefinition | None = None,
        start_request: SubAgentStartRequest | None = None,
        definition_match: DefinitionMatchMetadata | None = None,
    ) -> BackgroundSubAgentRunRecord | BackgroundSubAgentStartBlocked:
        """Create a run file and launch a worker unless the scope is full."""
        await self._reap_scope(scope)
        active = self._active_for_scope(scope)
        if len(active) >= self._max_running_per_scope:
            return BackgroundSubAgentStartBlocked(
                limit=self._max_running_per_scope,
                active_run_ids=sorted(active),
            )
        definition = definition or self._registry.resolve(spec.name)
        effective_policy = compose_effective_policy(
            parent_policy or PermissionPolicy.readonly(),
            definition.permission,
            runtime_policy or PermissionPolicy.readonly(),
            workspace_policy or PermissionPolicy.readonly(),
        )
        store = PerRunSubAgentRunStore(scope.run_store_dir)
        effective_budget = _effective_budget(definition.budget, spec.budget)
        nickname = assign_subagent_nickname(definition.nickname)
        record = await store.create(
            spec,
            definition,
            effective_policy,
            effective_budget=effective_budget,
            start_request=start_request,
            definition_match=definition_match,
            nickname=nickname,
        )
        launch_path = scope.run_store_dir / f"{record.run_id}.launch.json"
        stderr_log_path = scope.run_store_dir / f"{record.run_id}.stderr.log"
        launch_spec = WorkerLaunchSpec(
            run_id=record.run_id,
            run_store_dir=str(scope.run_store_dir),
            workspace_dir=str(workspace_dir),
            parent_agent_config=parent_agent_config.model_dump(mode="json"),
            definition=definition,
            delegation_spec=spec,
            effective_policy=effective_policy,
            start_request=record.start_request,
            definition_match=record.definition_match,
            nickname=record.nickname,
            request_context=request_context or {},
            stderr_log_path=str(stderr_log_path),
        )
        self._write_launch_spec(launch_path, launch_spec)
        command = [
            sys.executable,
            "-m",
            "swe.app.subagents.worker",
            "--launch-spec",
            str(launch_path),
        ]
        try:
            process = self._start_process(command, stderr_log_path)
        except Exception as exc:
            return await store.fail(
                record.run_id,
                str(exc),
                error_code="worker_start_failed",
            )
        running = await store.mark_running(
            record.run_id,
            worker_pid=process.pid,
            stderr_log_path=str(stderr_log_path),
        )
        active[record.run_id] = _ActiveRun(
            scope=scope,
            process=process,
            stderr_log_path=stderr_log_path,
        )
        return running

    async def wait(
        self,
        scope: BackgroundSubAgentScope,
        *,
        timeout_ms: int = 3000,
    ) -> BackgroundSubAgentWaitSnapshot:
        """Bounded wait over current active handles in one scope."""
        deadline = time.monotonic() + max(timeout_ms, 0) / 1000
        terminal_runs: list[BackgroundSubAgentRunRecord] = []
        while True:
            terminal_runs.extend(await self._reap_scope(scope))
            if terminal_runs or time.monotonic() >= deadline:
                break
            await asyncio.sleep(min(0.05, max(deadline - time.monotonic(), 0)))
        active_runs = await self._active_records(scope)
        return BackgroundSubAgentWaitSnapshot(
            active_runs=active_runs,
            terminal_runs=terminal_runs,
            timed_out=bool(active_runs and not terminal_runs),
        )

    async def get(
        self,
        scope: BackgroundSubAgentScope,
        run_id: str,
    ) -> BackgroundSubAgentRunRecord | None:
        """Read a run record in scope and lazy-reap active workers first."""
        await self._reap_scope(scope)
        return await PerRunSubAgentRunStore(scope.run_store_dir).get(run_id)

    async def cancel(
        self,
        scope: BackgroundSubAgentScope,
        run_id: str,
    ) -> BackgroundSubAgentRunRecord | BackgroundSubAgentNotManageable | None:
        """Cancel an active worker process group for a run in scope."""
        await self._reap_scope(scope)
        store = PerRunSubAgentRunStore(scope.run_store_dir)
        record = await store.get(run_id)
        if record is None:
            return None
        if record.status in TERMINAL_BACKGROUND_RUN_STATUSES:
            return record
        active = self._active_for_scope(scope)
        handle = active.get(run_id)
        if handle is None:
            return BackgroundSubAgentNotManageable(run_id=run_id)
        self._terminate_process_group(handle.process)
        active.pop(run_id, None)
        return await store.cancel(run_id)

    def has_active_runs(self, scope: BackgroundSubAgentScope) -> bool:
        """Return whether this process currently manages runs in scope."""
        return bool(self._active_for_scope(scope))

    def is_manageable(
        self,
        scope: BackgroundSubAgentScope,
        run_id: str,
    ) -> bool:
        """Return whether this process has an active handle for a run."""
        return run_id in self._active_for_scope(scope)

    async def _active_records(
        self,
        scope: BackgroundSubAgentScope,
    ) -> list[BackgroundSubAgentRunRecord]:
        store = PerRunSubAgentRunStore(scope.run_store_dir)
        records: list[BackgroundSubAgentRunRecord] = []
        for run_id in sorted(self._active_for_scope(scope)):
            record = await store.get(run_id)
            if (
                record is not None
                and record.status not in TERMINAL_BACKGROUND_RUN_STATUSES
            ):
                records.append(record)
        return records

    async def _reap_scope(
        self,
        scope: BackgroundSubAgentScope,
    ) -> list[BackgroundSubAgentRunRecord]:
        active = self._active_for_scope(scope)
        terminal_runs: list[BackgroundSubAgentRunRecord] = []
        store = PerRunSubAgentRunStore(scope.run_store_dir)
        for run_id, handle in list(active.items()):
            if handle.process.poll() is None:
                continue
            try:
                record = await store.mark_worker_exited(
                    run_id,
                    exit_code=handle.process.returncode,
                )
            except KeyError:
                active.pop(run_id, None)
                continue
            if record.status in TERMINAL_BACKGROUND_RUN_STATUSES:
                terminal_runs.append(record)
            else:
                message = (
                    f"{_WORKER_EXITED_WITHOUT_RESULT}: "
                    f"exit_code={handle.process.returncode}"
                )
                terminal_runs.append(
                    await store.fail(
                        run_id,
                        message,
                        error_code=_WORKER_EXITED_WITHOUT_RESULT,
                    ),
                )
            active.pop(run_id, None)
        return terminal_runs

    def _active_for_scope(
        self,
        scope: BackgroundSubAgentScope,
    ) -> dict[str, _ActiveRun]:
        return self._active.setdefault(
            (scope.tenant_id, scope.agent_id),
            {},
        )

    def _start_process(self, command: list[str], stderr_log_path: Path) -> Any:
        stderr_log_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_handle = stderr_log_path.open("ab")
        try:
            process = self._popen_factory(
                command,
                stdout=subprocess.DEVNULL,
                stderr=stderr_handle,
                stdin=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
        finally:
            stderr_handle.close()
        return process

    def _terminate_process_group(self, process: Any) -> None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except Exception:
            if hasattr(process, "terminate"):
                process.terminate()
        try:
            process.wait(timeout=self._cancel_grace_seconds)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception:
            if hasattr(process, "kill"):
                process.kill()
        process.wait(timeout=self._cancel_grace_seconds)

    def _write_launch_spec(
        self,
        launch_path: Path,
        launch_spec: WorkerLaunchSpec,
    ) -> None:
        launch_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = (
            launch_path.parent / f".{launch_path.name}.{uuid4().hex}.tmp"
        )
        tmp_path.write_text(
            json.dumps(
                launch_spec.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        tmp_path.replace(launch_path)
