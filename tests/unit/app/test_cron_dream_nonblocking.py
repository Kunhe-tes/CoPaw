# -*- coding: utf-8 -*-
"""验证 dream cron 文件处理不会直接阻塞事件循环。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import swe.app.crons.manager as manager_module
from swe.app.crons.manager import CronManager


def _manager(*, workspace_dir: Path | None = None, service: Any = None):
    async def fake_dream_memory(**_kwargs: Any) -> None:
        return None

    return CronManager(
        repo=object(),
        runner=SimpleNamespace(
            workspace_dir=workspace_dir,
            _workspace=None,
            memory_manager=SimpleNamespace(dream_memory=fake_dream_memory),
        ),
        channel_manager=object(),
        agent_id="default",
        tenant_id="tenant-a",
        continuous_governance_service=service,
    )


def _write_dream_logs(workspace_dir: Path, records: list[dict[str, Any]]):
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "dream_logs.json").write_text(
        json.dumps({"records": records}),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_load_dream_record_ids_reads_logs_through_thread(
    tmp_path,
    monkeypatch,
) -> None:
    workspace_dir = tmp_path / "workspace"
    _write_dream_logs(workspace_dir, [{"id": "existing-record"}])
    manager = _manager(workspace_dir=workspace_dir)
    calls: list[str] = []

    async def fake_to_thread(func, /, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(manager_module.asyncio, "to_thread", fake_to_thread)

    record_ids = await manager._load_dream_record_ids(workspace_dir)

    assert record_ids == {"existing-record"}
    assert calls == ["_load_dream_logs_sync"]


@pytest.mark.asyncio
async def test_dual_write_dream_records_reads_logs_through_thread(
    tmp_path,
    monkeypatch,
) -> None:
    workspace_dir = tmp_path / "workspace"
    _write_dream_logs(workspace_dir, [{"id": "new-record"}])
    observed: dict[str, Any] = {}
    calls: list[str] = []

    class FakeGovernanceService:
        async def upsert_workspace_governance_record_with_health(
            self,
            **kwargs,
        ) -> None:
            observed["record"] = kwargs["record"]

    async def fake_to_thread(func, /, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(manager_module.asyncio, "to_thread", fake_to_thread)
    manager = _manager(
        workspace_dir=workspace_dir,
        service=FakeGovernanceService(),
    )

    await manager._dual_write_dream_records(
        workspace_dir=workspace_dir,
        source_id="source-a",
        tenant_id="tenant-a",
        agent_id="default",
        before_record_ids=set(),
    )

    assert observed["record"]["id"] == "new-record"
    assert calls == ["_load_dream_logs_sync"]


@pytest.mark.asyncio
async def test_run_dream_offloads_archive_maintenance(
    tmp_path,
    monkeypatch,
) -> None:
    workspace_dir = tmp_path / "workspace"
    _write_dream_logs(workspace_dir, [])
    calls: list[str] = []

    def fake_maintenance(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def fake_to_thread(func, /, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(manager_module.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(
        "swe.app.routers.dream_logs.run_dream_archive_maintenance",
        fake_maintenance,
    )
    manager = _manager(workspace_dir=workspace_dir)

    await manager.run_dream()

    assert "fake_maintenance" in calls
