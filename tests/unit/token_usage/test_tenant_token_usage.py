# -*- coding: utf-8 -*-
"""Token usage tenant isolation regression tests."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from swe.config.context import tenant_context
from swe.token_usage import manager as token_usage_manager_module
from swe.token_usage.manager import TokenUsageManager


class _SaveCancellationProbe:
    """Instrument token usage saves for cancellation-order assertions."""

    def __init__(self) -> None:
        self.first_save_started = asyncio.Event()
        self.first_save_can_finish = asyncio.Event()
        self.first_save_finished = asyncio.Event()
        self.second_save_started = asyncio.Event()
        self.pending_save_tasks: list[asyncio.Task] = []
        self.save_calls = 0
        self.second_save_started_before_first_finished = False
        self.save_events: list[str] = []

    async def run_runtime_state_work(self, func, /, *args, **kwargs):
        if func.__name__ != "_save_data_sync":
            return func(*args, **kwargs)

        self.save_calls += 1
        save_call = self.save_calls
        save_task = asyncio.create_task(
            self._save_worker(save_call, func, *args, **kwargs),
        )
        self.pending_save_tasks.append(save_task)
        return await asyncio.shield(save_task)

    async def _save_worker(self, save_call, func, /, *args, **kwargs):
        self.save_events.append(f"save-{save_call}-started")
        if save_call == 1:
            self.first_save_started.set()
            await self.first_save_can_finish.wait()
        if save_call == 2:
            if not self.first_save_finished.is_set():
                self.second_save_started_before_first_finished = True
            self.second_save_started.set()

        result = func(*args, **kwargs)
        if save_call == 1:
            self.first_save_finished.set()
        self.save_events.append(f"save-{save_call}-finished")
        return result

    async def repeatedly_cancel_after_first_save_starts(
        self,
        record_task: asyncio.Task,
    ) -> None:
        await self.first_save_started.wait()
        record_task.cancel()
        await asyncio.sleep(0)
        record_task.cancel()
        await asyncio.sleep(0)

    async def finish_saves(
        self,
        first_record: asyncio.Task,
        second_record: asyncio.Task,
    ) -> tuple[bool, list[object]]:
        for _ in range(5):
            await asyncio.sleep(0)

        second_started_before_release = self.second_save_started.is_set()
        self.first_save_can_finish.set()
        results = await asyncio.gather(
            first_record,
            second_record,
            return_exceptions=True,
        )
        if self.pending_save_tasks:
            await asyncio.gather(*self.pending_save_tasks)
        return second_started_before_release, results


def test_token_usage_manager_uses_tenant_workspace_path(tmp_path):
    TokenUsageManager._instance = None

    tenant_workspace = tmp_path / "tenant-a"
    tenant_workspace.mkdir()

    with tenant_context(tenant_id="tenant-a", workspace_dir=tenant_workspace):
        scoped_manager = TokenUsageManager.get_instance()
        asyncio.run(
            scoped_manager.record(
                provider_id="openai",
                model_name="gpt-5",
                prompt_tokens=3,
                completion_tokens=4,
                at_date=date(2026, 4, 2),
            ),
        )

    assert scoped_manager._path == tenant_workspace / "token_usage.json"
    assert scoped_manager._path.exists()


def test_token_usage_manager_migrates_legacy_empty_list_file(tmp_path):
    TokenUsageManager._instance = None

    tenant_workspace = tmp_path / "tenant-b"
    tenant_workspace.mkdir()
    (tenant_workspace / "token_usage.json").write_text(
        "[]",
        encoding="utf-8",
    )

    with tenant_context(tenant_id="tenant-b", workspace_dir=tenant_workspace):
        scoped_manager = TokenUsageManager.get_instance()
        asyncio.run(
            scoped_manager.record(
                provider_id="openai",
                model_name="gpt-5",
                prompt_tokens=5,
                completion_tokens=7,
                at_date=date(2026, 4, 8),
            ),
        )

    stored = (tenant_workspace / "token_usage.json").read_text(
        encoding="utf-8",
    )
    assert '"2026-04-08"' in stored


def test_token_usage_record_uses_runtime_state_worker(
    tmp_path,
    monkeypatch,
):
    TokenUsageManager._instance = None

    tenant_workspace = tmp_path / "tenant-c"
    tenant_workspace.mkdir()
    (tenant_workspace / "token_usage.json").write_text(
        "{}",
        encoding="utf-8",
    )

    state: dict[str, object] = {
        "in_worker": False,
        "worker_calls": [],
        "loads_in_worker": False,
        "dumps_in_worker": False,
    }

    async def fake_run_runtime_state_work(func, /, *args, **kwargs):
        state["worker_calls"].append(func.__name__)
        assert state["in_worker"] is False
        state["in_worker"] = True
        try:
            return func(*args, **kwargs)
        finally:
            state["in_worker"] = False

    original_loads = token_usage_manager_module.json.loads
    original_dumps = token_usage_manager_module.json.dumps

    def fake_loads(*args, **kwargs):
        assert state["in_worker"] is True
        state["loads_in_worker"] = True
        return original_loads(*args, **kwargs)

    def fake_dumps(*args, **kwargs):
        assert state["in_worker"] is True
        state["dumps_in_worker"] = True
        return original_dumps(*args, **kwargs)

    monkeypatch.setattr(
        token_usage_manager_module,
        "run_runtime_state_work",
        fake_run_runtime_state_work,
        raising=False,
    )
    monkeypatch.setattr(token_usage_manager_module.json, "loads", fake_loads)
    monkeypatch.setattr(token_usage_manager_module.json, "dumps", fake_dumps)

    with tenant_context(tenant_id="tenant-c", workspace_dir=tenant_workspace):
        scoped_manager = TokenUsageManager.get_instance()
        asyncio.run(
            scoped_manager.record(
                provider_id="openai",
                model_name="gpt-5",
                prompt_tokens=11,
                completion_tokens=13,
                at_date=date(2026, 4, 10),
            ),
        )

    assert state["loads_in_worker"] is True
    assert state["dumps_in_worker"] is True
    assert state["worker_calls"] == ["_load_data_sync", "_save_data_sync"]


def test_cancelled_record_waits_for_inflight_save_before_releasing_lock(
    tmp_path,
    monkeypatch,
):
    TokenUsageManager._instance = None

    tenant_workspace = tmp_path / "tenant-d"
    tenant_workspace.mkdir()
    usage_path = tenant_workspace / "token_usage.json"
    usage_path.write_text("{}", encoding="utf-8")

    async def run_scenario():
        probe = _SaveCancellationProbe()

        monkeypatch.setattr(
            token_usage_manager_module,
            "run_runtime_state_work",
            probe.run_runtime_state_work,
            raising=False,
        )

        with tenant_context(
            tenant_id="tenant-d",
            workspace_dir=tenant_workspace,
        ):
            scoped_manager = TokenUsageManager.get_instance()
            first_record = asyncio.create_task(
                scoped_manager.record(
                    provider_id="openai",
                    model_name="gpt-5",
                    prompt_tokens=1,
                    completion_tokens=2,
                    at_date=date(2026, 4, 11),
                ),
            )
            await probe.repeatedly_cancel_after_first_save_starts(
                first_record,
            )

            second_record = asyncio.create_task(
                scoped_manager.record(
                    provider_id="openai",
                    model_name="gpt-5",
                    prompt_tokens=10,
                    completion_tokens=20,
                    at_date=date(2026, 4, 11),
                ),
            )

            second_started_before_release, results = await probe.finish_saves(
                first_record,
                second_record,
            )

            assert isinstance(results[0], asyncio.CancelledError)
            assert results[1] is None
            assert probe.first_save_finished.is_set()
            assert second_started_before_release is False
            assert probe.second_save_started_before_first_finished is False
            assert probe.save_events == [
                "save-1-started",
                "save-1-finished",
                "save-2-started",
                "save-2-finished",
            ]

    asyncio.run(run_scenario())

    stored = json.loads(usage_path.read_text(encoding="utf-8"))
    entry = stored["2026-04-11"]["openai:gpt-5"]
    assert entry["prompt_tokens"] == 11
    assert entry["completion_tokens"] == 22
    assert entry["call_count"] == 2
