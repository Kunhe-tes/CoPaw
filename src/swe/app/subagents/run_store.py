# -*- coding: utf-8 -*-
"""Replaceable SubAgent run-store implementations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .models import (
    AgentError,
    AgentResult,
    PermissionPolicy,
    SubAgentDefinition,
    SubAgentRunRecord,
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

    async def fail(self, run_id: str, message: str) -> SubAgentRunRecord:
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

    async def fail(self, run_id: str, message: str) -> SubAgentRunRecord:
        """Store terminal failure with structured error."""
        error = AgentError(
            code="runtime_error",
            message=message,
            recoverable=False,
        )
        record = self.records[run_id].model_copy(
            update={
                "status": "failed",
                "errors": [*self.records[run_id].errors, error],
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

    async def fail(self, run_id: str, message: str) -> SubAgentRunRecord:
        record = await super().fail(run_id, message)
        self._save()
        return record

    async def cancel(self, run_id: str) -> SubAgentRunRecord:
        record = await super().cancel(run_id)
        self._save()
        return record
