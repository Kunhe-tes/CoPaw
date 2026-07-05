# -*- coding: utf-8 -*-
"""Replaceable SubAgent run-store implementations."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .models import (
    AgentError,
    AgentResult,
    BackgroundSubAgentRunRecord,
    BudgetConfig,
    PermissionPolicy,
    SubAgentDefinition,
    SubAgentRunRecord,
    TERMINAL_BACKGROUND_RUN_STATUSES,
    WorkerProcessInfo,
    _now_utc,
)
from .models import DelegationSpec


class SubAgentRunStore(Protocol):
    """Replaceable lifecycle store interface for SubAgent runs."""

    async def create(
        self,
        spec: DelegationSpec,
        definition: SubAgentDefinition,
        effective_policy: PermissionPolicy,
    ) -> SubAgentRunRecord:
        """Create a queued run record."""

    async def mark_running(self, run_id: str) -> SubAgentRunRecord:
        """Mark a run as running."""

    async def finish(
        self,
        run_id: str,
        result: AgentResult,
    ) -> SubAgentRunRecord:
        """Persist a terminal result."""

    async def fail(
        self,
        run_id: str,
        message: str,
        *,
        result: AgentResult | None = None,
    ) -> SubAgentRunRecord:
        """Persist a terminal failure."""

    async def cancel(self, run_id: str) -> SubAgentRunRecord:
        """Persist cancellation."""

    async def get(self, run_id: str) -> SubAgentRunRecord | None:
        """Return a run by id."""


class InMemorySubAgentRunStore:
    """Test-friendly in-memory run store."""

    def __init__(self):
        self.records: dict[str, SubAgentRunRecord] = {}

    async def create(
        self,
        spec: DelegationSpec,
        definition: SubAgentDefinition,
        effective_policy: PermissionPolicy,
    ) -> SubAgentRunRecord:
        """Create a queued run record."""
        record = SubAgentRunRecord(
            spec=spec,
            definition_name=definition.name,
            definition_version=definition.version,
            definition_source=definition.source,
            owner_scope=definition.owner_scope,
            effective_policy=effective_policy,
        )
        self.records[record.run_id] = record
        return record

    async def mark_running(self, run_id: str) -> SubAgentRunRecord:
        """Mark a run as running."""
        record = self.records[run_id].model_copy(
            update={"status": "running", "started_at": _now_utc()},
        )
        self.records[run_id] = record
        return record

    async def finish(
        self,
        run_id: str,
        result: AgentResult,
    ) -> SubAgentRunRecord:
        """Store terminal successful or partial result."""
        record = self.records[run_id].model_copy(
            update={
                "status": result.status,
                "result": result,
                "finished_at": _now_utc(),
            },
        )
        self.records[run_id] = record
        return record

    async def fail(
        self,
        run_id: str,
        message: str,
        *,
        result: AgentResult | None = None,
    ) -> SubAgentRunRecord:
        """Store terminal failure with structured error."""
        errors = (
            list(result.errors)
            if result and result.errors
            else [
                AgentError(
                    code="runtime_error",
                    message=message,
                    recoverable=False,
                ),
            ]
        )
        record = self.records[run_id].model_copy(
            update={
                "status": "failed",
                "result": result,
                "errors": [*self.records[run_id].errors, *errors],
                "finished_at": _now_utc(),
            },
        )
        self.records[run_id] = record
        return record

    async def cancel(self, run_id: str) -> SubAgentRunRecord:
        """Mark a run cancelled."""
        record = self.records[run_id].model_copy(
            update={"status": "cancelled", "finished_at": _now_utc()},
        )
        self.records[run_id] = record
        return record

    async def get(self, run_id: str) -> SubAgentRunRecord | None:
        """Return a run by id."""
        return self.records.get(run_id)


class LocalJsonSubAgentRunStore(InMemorySubAgentRunStore):
    """Workspace-local JSON run store under app state, not repository checkout."""

    def __init__(self, state_dir: Path):
        super().__init__()
        self._path = Path(state_dir) / "subagent_runs.json"
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        data = json.loads(self._path.read_text(encoding="utf-8"))
        self.records = {
            item["run_id"]: SubAgentRunRecord.model_validate(item)
            for item in data.get("runs", [])
        }

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "runs": [
                record.model_dump(mode="json")
                for record in self.records.values()
            ],
        }
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def create(
        self,
        spec: DelegationSpec,
        definition: SubAgentDefinition,
        effective_policy: PermissionPolicy,
    ) -> SubAgentRunRecord:
        record = await super().create(spec, definition, effective_policy)
        self._save()
        return record

    async def mark_running(self, run_id: str) -> SubAgentRunRecord:
        record = await super().mark_running(run_id)
        self._save()
        return record

    async def finish(
        self,
        run_id: str,
        result: AgentResult,
    ) -> SubAgentRunRecord:
        record = await super().finish(run_id, result)
        self._save()
        return record

    async def fail(
        self,
        run_id: str,
        message: str,
        *,
        result: AgentResult | None = None,
    ) -> SubAgentRunRecord:
        record = await super().fail(run_id, message, result=result)
        self._save()
        return record

    async def cancel(self, run_id: str) -> SubAgentRunRecord:
        record = await super().cancel(run_id)
        self._save()
        return record


class PerRunSubAgentRunStore:
    """Per-run JSON store for Background SubAgent Runs."""

    def __init__(self, run_store_dir: Path):
        self._dir = Path(run_store_dir)

    async def create(
        self,
        spec: DelegationSpec,
        definition: SubAgentDefinition,
        effective_policy: PermissionPolicy,
        effective_budget: BudgetConfig | None = None,
    ) -> BackgroundSubAgentRunRecord:
        """Create a pending background run record."""
        record = BackgroundSubAgentRunRecord(
            spec=spec,
            definition_name=definition.name,
            definition_version=definition.version,
            definition_source=definition.source,
            owner_scope=definition.owner_scope,
            effective_policy=effective_policy,
            effective_budget=effective_budget or BudgetConfig(),
        )
        self._write(record)
        return record

    async def mark_running(
        self,
        run_id: str,
        *,
        worker_pid: int | None = None,
        stderr_log_path: str | None = None,
    ) -> BackgroundSubAgentRunRecord:
        """Mark a background run as running with worker metadata."""
        record = self._require(run_id)
        if record.status in TERMINAL_BACKGROUND_RUN_STATUSES:
            return record
        now = _now_utc()
        pid = worker_pid
        if pid is None and record.worker is not None:
            pid = record.worker.pid
        if pid is None:
            pid = os.getpid()
        stderr_path = stderr_log_path
        if stderr_path is None and record.worker is not None:
            stderr_path = record.worker.stderr_log_path
        running = record.model_copy(
            update={
                "status": "running",
                "worker": WorkerProcessInfo(
                    pid=pid,
                    started_at=now,
                    stderr_log_path=stderr_path,
                ),
                "started_at": record.started_at or now,
                "updated_at": now,
            },
        )
        self._write(running)
        return running

    async def finish(
        self,
        run_id: str,
        result: AgentResult,
    ) -> BackgroundSubAgentRunRecord:
        """Store a terminal result under lifecycle status completed."""
        record = self._require(run_id)
        if record.status in TERMINAL_BACKGROUND_RUN_STATUSES:
            return record
        now = _now_utc()
        finished = record.model_copy(
            update={
                "status": "completed",
                "result": result,
                "finished_at": now,
                "updated_at": now,
            },
        )
        self._write(finished)
        return finished

    async def fail(
        self,
        run_id: str,
        message: str,
        *,
        result: AgentResult | None = None,
        error_code: str = "runtime_error",
    ) -> BackgroundSubAgentRunRecord:
        """Store a terminal background failure."""
        record = self._require(run_id)
        if record.status in TERMINAL_BACKGROUND_RUN_STATUSES:
            return record
        now = _now_utc()
        errors = (
            list(result.errors)
            if result and result.errors
            else [
                AgentError(
                    code=error_code,
                    message=message,
                    recoverable=False,
                ),
            ]
        )
        failed = record.model_copy(
            update={
                "status": "failed",
                "result": result,
                "errors": [*record.errors, *errors],
                "finished_at": now,
                "updated_at": now,
            },
        )
        self._write(failed)
        return failed

    async def mark_worker_exited(
        self,
        run_id: str,
        *,
        exit_code: int | None,
    ) -> BackgroundSubAgentRunRecord:
        """Persist worker exit summary without changing terminal status."""
        record = self._require(run_id)
        if record.worker is None:
            return record
        now = _now_utc()
        updated = record.model_copy(
            update={
                "worker": record.worker.model_copy(
                    update={
                        "exit_code": exit_code,
                        "exited_at": now,
                    },
                ),
                "updated_at": now,
            },
        )
        self._write(updated)
        return updated

    async def cancel(self, run_id: str) -> BackgroundSubAgentRunRecord:
        """Mark a background run cancelled if still non-terminal."""
        record = self._require(run_id)
        if record.status in TERMINAL_BACKGROUND_RUN_STATUSES:
            return record
        now = _now_utc()
        cancelled = record.model_copy(
            update={
                "status": "cancelled",
                "finished_at": now,
                "updated_at": now,
            },
        )
        self._write(cancelled)
        return cancelled

    async def get(self, run_id: str) -> BackgroundSubAgentRunRecord | None:
        """Return a background run by id from its individual JSON file."""
        path = self._path(run_id)
        if not path.exists():
            return None
        return BackgroundSubAgentRunRecord.model_validate(
            json.loads(path.read_text(encoding="utf-8")),
        )

    def _require(self, run_id: str) -> BackgroundSubAgentRunRecord:
        path = self._path(run_id)
        if not path.exists():
            raise KeyError(run_id)
        return BackgroundSubAgentRunRecord.model_validate(
            json.loads(path.read_text(encoding="utf-8")),
        )

    def _path(self, run_id: str) -> Path:
        if Path(run_id).name != run_id:
            raise ValueError("run_id must not contain path separators")
        return self._dir / f"{run_id}.json"

    def _write(self, record: BackgroundSubAgentRunRecord) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._path(record.run_id)
        tmp_path = self._dir / f".{record.run_id}.{uuid4().hex}.tmp"
        tmp_path.write_text(
            json.dumps(
                record.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        tmp_path.replace(path)
