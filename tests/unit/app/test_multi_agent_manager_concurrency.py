# -*- coding: utf-8 -*-
"""验证 MultiAgentManager 按 cache key 去重并发启动。"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from types import SimpleNamespace
from typing import Any

import pytest

import swe.app.multi_agent_manager as manager_module
from swe.app.multi_agent_manager import MultiAgentManager


def _config(*agent_ids: str) -> SimpleNamespace:
    return SimpleNamespace(
        agents=SimpleNamespace(
            profiles={
                agent_id: SimpleNamespace(workspace_dir=f"/tmp/{agent_id}")
                for agent_id in agent_ids
            },
        ),
    )


class _Workspace:
    def __init__(
        self,
        *,
        agent_id: str,
        workspace_dir: str,
        tenant_id: str | None = None,
        **_kwargs: Any,
    ) -> None:
        self.agent_id = agent_id
        self.workspace_dir = workspace_dir
        self.tenant_id = tenant_id
        self.started = False
        self.stopped = False
        self.manager = None

    async def start(self) -> None:
        self.started = True

    async def stop(self, *_args: Any, **_kwargs: Any) -> None:
        self.stopped = True

    def set_manager(self, manager: MultiAgentManager) -> None:
        self.manager = manager


class _TaskTracker:
    def __init__(self, *, has_active_tasks: bool = False) -> None:
        self._has_active_tasks = has_active_tasks

    async def has_active_tasks(self) -> bool:
        return self._has_active_tasks


@pytest.mark.asyncio
async def test_same_cache_key_concurrent_get_agent_starts_once(
    monkeypatch,
) -> None:
    manager = MultiAgentManager()
    created: list[_Workspace] = []

    class SlowWorkspace(_Workspace):
        async def start(self) -> None:
            await asyncio.sleep(0.01)
            await super().start()

    def workspace_factory(**kwargs: Any) -> SlowWorkspace:
        workspace = SlowWorkspace(**kwargs)
        created.append(workspace)
        return workspace

    monkeypatch.setattr(manager_module, "Workspace", workspace_factory)
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    results = await asyncio.gather(
        manager.get_agent("default", tenant_id="tenant-a"),
        manager.get_agent("default", tenant_id="tenant-a"),
        manager.get_agent("default", tenant_id="tenant-a"),
    )

    assert len(created) == 1
    assert results == [created[0], created[0], created[0]]
    assert manager.agents["tenant-a:default"] is created[0]


@pytest.mark.asyncio
async def test_different_cache_keys_start_without_global_lock_blocking(
    monkeypatch,
) -> None:
    manager = MultiAgentManager()
    slow_started = asyncio.Event()
    slow_release = asyncio.Event()

    class ControlledWorkspace(_Workspace):
        async def start(self) -> None:
            if self.agent_id == "slow":
                slow_started.set()
                await slow_release.wait()
            await super().start()

    monkeypatch.setattr(manager_module, "Workspace", ControlledWorkspace)
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("slow", "fast"),
    )

    slow_task = asyncio.create_task(
        manager.get_agent("slow", tenant_id="tenant-a"),
    )
    await slow_started.wait()
    try:
        fast_workspace = await asyncio.wait_for(
            manager.get_agent("fast", tenant_id="tenant-a"),
            timeout=0.05,
        )
    finally:
        slow_release.set()
        with suppress(Exception):
            await slow_task

    assert fast_workspace.agent_id == "fast"
    assert fast_workspace.started is True


@pytest.mark.asyncio
async def test_cache_hit_does_not_create_inflight_startup(monkeypatch) -> None:
    manager = MultiAgentManager()
    cached = _Workspace(
        agent_id="default",
        workspace_dir="/tmp/default",
        tenant_id="tenant-a",
    )
    manager.agents["tenant-a:default"] = cached

    def fail_workspace_factory(**_kwargs: Any) -> _Workspace:
        raise AssertionError("cache hit must not create workspace")

    monkeypatch.setattr(manager_module, "Workspace", fail_workspace_factory)

    result = await manager.get_agent("default", tenant_id="tenant-a")

    assert result is cached
    assert getattr(manager, "_agent_start_tasks", {}) == {}


@pytest.mark.asyncio
async def test_startup_failure_is_shared_and_later_retryable(
    monkeypatch,
) -> None:
    manager = MultiAgentManager()
    attempts = 0
    should_fail = True

    class FailingWorkspace(_Workspace):
        async def start(self) -> None:
            nonlocal attempts, should_fail
            attempts += 1
            await asyncio.sleep(0.01)
            if should_fail:
                raise RuntimeError("startup failed")
            await super().start()

    monkeypatch.setattr(manager_module, "Workspace", FailingWorkspace)
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    results = await asyncio.gather(
        manager.get_agent("default", tenant_id="tenant-a"),
        manager.get_agent("default", tenant_id="tenant-a"),
        return_exceptions=True,
    )

    assert attempts == 1
    assert all(isinstance(result, RuntimeError) for result in results)
    assert [str(result) for result in results] == [
        "startup failed",
        "startup failed",
    ]
    assert manager.agents == {}
    assert getattr(manager, "_agent_start_tasks", {}) == {}

    should_fail = False
    workspace = await manager.get_agent("default", tenant_id="tenant-a")

    assert attempts == 2
    assert workspace.started is True
    assert manager.agents["tenant-a:default"] is workspace


@pytest.mark.asyncio
async def test_duplicate_workspace_lost_race_is_stopped(monkeypatch) -> None:
    manager = MultiAgentManager()
    existing = _Workspace(
        agent_id="default",
        workspace_dir="/tmp/existing",
        tenant_id="tenant-a",
    )
    created: list[_Workspace] = []

    class RacingWorkspace(_Workspace):
        async def start(self) -> None:
            created.append(self)
            manager.agents["tenant-a:default"] = existing
            await super().start()

    monkeypatch.setattr(manager_module, "Workspace", RacingWorkspace)
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    result = await manager.get_agent("default", tenant_id="tenant-a")

    assert result is existing
    assert manager.agents["tenant-a:default"] is existing
    assert created[0].stopped is True


def test_workspace_cache_defaults_are_bounded() -> None:
    manager = MultiAgentManager()

    assert manager.workspace_cache_max_size == 64
    assert manager.workspace_start_max_concurrent == 4
    assert manager.workspace_idle_ttl_seconds == 6 * 60 * 60


def test_workspace_cache_settings_read_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SWE_WORKSPACE_CACHE_MAX_SIZE", "12")
    monkeypatch.setenv("SWE_WORKSPACE_START_MAX_CONCURRENT", "3")
    monkeypatch.setenv("SWE_WORKSPACE_IDLE_TTL_SECONDS", "90")

    manager = MultiAgentManager()

    assert manager.workspace_cache_max_size == 12
    assert manager.workspace_start_max_concurrent == 3
    assert manager.workspace_idle_ttl_seconds == 90


@pytest.mark.asyncio
async def test_workspace_cache_evicts_lru_after_capacity(
    monkeypatch,
) -> None:
    clock = 1000.0
    manager = MultiAgentManager(
        workspace_cache_max_size=2,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=4,
        monotonic_time=lambda: clock,
    )
    created: list[_Workspace] = []

    def workspace_factory(**kwargs: Any) -> _Workspace:
        workspace = _Workspace(**kwargs)
        created.append(workspace)
        return workspace

    monkeypatch.setattr(manager_module, "Workspace", workspace_factory)
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    workspace_a = await manager.get_agent("default", tenant_id="tenant-a")
    clock += 1
    workspace_b = await manager.get_agent("default", tenant_id="tenant-b")
    clock += 1
    assert await manager.get_agent("default", tenant_id="tenant-a") is (
        workspace_a
    )
    clock += 1
    workspace_c = await manager.get_agent("default", tenant_id="tenant-c")

    assert manager.list_loaded_agents() == [
        "tenant-a:default",
        "tenant-c:default",
    ]
    assert workspace_b.stopped is True
    assert workspace_a.stopped is False
    assert workspace_c.stopped is False


@pytest.mark.asyncio
async def test_workspace_cache_evicts_idle_entries(monkeypatch) -> None:
    clock = 1000.0
    manager = MultiAgentManager(
        workspace_cache_max_size=10,
        workspace_idle_ttl_seconds=10,
        workspace_start_max_concurrent=4,
        monotonic_time=lambda: clock,
    )
    created: list[_Workspace] = []

    def workspace_factory(**kwargs: Any) -> _Workspace:
        workspace = _Workspace(**kwargs)
        created.append(workspace)
        return workspace

    monkeypatch.setattr(manager_module, "Workspace", workspace_factory)
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    workspace_a = await manager.get_agent("default", tenant_id="tenant-a")
    clock += 5
    workspace_b = await manager.get_agent("default", tenant_id="tenant-b")
    clock += 6
    workspace_c = await manager.get_agent("default", tenant_id="tenant-c")

    assert manager.list_loaded_agents() == [
        "tenant-b:default",
        "tenant-c:default",
    ]
    assert workspace_a.stopped is True
    assert workspace_b.stopped is False
    assert workspace_c.stopped is False


@pytest.mark.asyncio
async def test_workspace_cache_defers_idle_eviction_with_active_tasks(
    monkeypatch,
) -> None:
    clock = 1000.0
    manager = MultiAgentManager(
        workspace_cache_max_size=10,
        workspace_idle_ttl_seconds=10,
        workspace_start_max_concurrent=4,
        monotonic_time=lambda: clock,
    )

    class ActiveWorkspace(_Workspace):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.task_tracker = _TaskTracker(has_active_tasks=True)

    monkeypatch.setattr(manager_module, "Workspace", ActiveWorkspace)
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    workspace_a = await manager.get_agent("default", tenant_id="tenant-a")
    clock += 11
    workspace_b = await manager.get_agent("default", tenant_id="tenant-b")

    assert manager.list_loaded_agents() == [
        "tenant-a:default",
        "tenant-b:default",
    ]
    assert workspace_a.stopped is False
    assert workspace_b.stopped is False


@pytest.mark.asyncio
async def test_workspace_cache_overflow_revalidates_recently_reused_lru(
    monkeypatch,
) -> None:
    clock = 1000.0
    manager = MultiAgentManager(
        workspace_cache_max_size=2,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=4,
        monotonic_time=lambda: clock,
    )
    eviction_check_started = asyncio.Event()
    allow_eviction_check = asyncio.Event()

    class CoordinatedWorkspace(_Workspace):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            if self.tenant_id == "tenant-a":
                self.task_tracker = SimpleNamespace(
                    has_active_tasks=self._has_active_tasks,
                )

        async def _has_active_tasks(self) -> bool:
            eviction_check_started.set()
            await allow_eviction_check.wait()
            return False

    monkeypatch.setattr(manager_module, "Workspace", CoordinatedWorkspace)
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    workspace_a = await manager.get_agent("default", tenant_id="tenant-a")
    clock += 1
    workspace_b = await manager.get_agent("default", tenant_id="tenant-b")
    clock += 1

    workspace_c_task = asyncio.create_task(
        manager.get_agent("default", tenant_id="tenant-c"),
    )
    await eviction_check_started.wait()

    clock += 1
    assert await manager.get_agent("default", tenant_id="tenant-a") is (
        workspace_a
    )

    allow_eviction_check.set()
    workspace_c = await workspace_c_task

    assert manager.list_loaded_agents() == [
        "tenant-a:default",
        "tenant-c:default",
    ]
    assert workspace_a.stopped is False
    assert workspace_b.stopped is True
    assert workspace_c.stopped is False


@pytest.mark.asyncio
async def test_workspace_cache_overflow_revalidation_handles_coarse_timer_reuse(
    monkeypatch,
) -> None:
    clock = 1000.0
    manager = MultiAgentManager(
        workspace_cache_max_size=2,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=4,
        monotonic_time=lambda: clock,
    )
    eviction_check_started = asyncio.Event()
    allow_eviction_check = asyncio.Event()

    class CoordinatedWorkspace(_Workspace):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            if self.tenant_id == "tenant-a":
                self.task_tracker = SimpleNamespace(
                    has_active_tasks=self._has_active_tasks,
                )

        async def _has_active_tasks(self) -> bool:
            eviction_check_started.set()
            await allow_eviction_check.wait()
            return False

    monkeypatch.setattr(manager_module, "Workspace", CoordinatedWorkspace)
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    workspace_a = await manager.get_agent("default", tenant_id="tenant-a")
    workspace_b = await manager.get_agent("default", tenant_id="tenant-b")

    workspace_c_task = asyncio.create_task(
        manager.get_agent("default", tenant_id="tenant-c"),
    )
    await eviction_check_started.wait()

    assert await manager.get_agent("default", tenant_id="tenant-a") is (
        workspace_a
    )

    allow_eviction_check.set()
    workspace_c = await workspace_c_task

    assert manager.list_loaded_agents() == [
        "tenant-a:default",
        "tenant-c:default",
    ]
    assert workspace_a.stopped is False
    assert workspace_b.stopped is True
    assert workspace_c.stopped is False


@pytest.mark.asyncio
async def test_workspace_cache_protects_completed_start_waiters(
    monkeypatch,
) -> None:
    manager = MultiAgentManager(
        workspace_cache_max_size=1,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=4,
    )
    tenant_a_started = asyncio.Event()
    tenant_a_may_return = asyncio.Event()
    tenant_b_waiting_after_start = asyncio.Event()
    tenant_b_may_return = asyncio.Event()
    original_evict_workspace_cache = manager._evict_workspace_cache

    class ControlledWorkspace(_Workspace):
        async def start(self) -> None:
            await super().start()
            if self.tenant_id == "tenant-a":
                tenant_a_started.set()
                await tenant_a_may_return.wait()

    async def controlled_evict_workspace_cache(
        *,
        protected_keys: set[str] | None = None,
    ) -> None:
        if protected_keys == {"tenant-b:default"}:
            tenant_b_waiting_after_start.set()
            await tenant_b_may_return.wait()
        await original_evict_workspace_cache(protected_keys=protected_keys)

    monkeypatch.setattr(manager_module, "Workspace", ControlledWorkspace)
    monkeypatch.setattr(
        manager,
        "_evict_workspace_cache",
        controlled_evict_workspace_cache,
    )
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    tenant_a_task = asyncio.create_task(
        manager.get_agent("default", tenant_id="tenant-a"),
    )
    await tenant_a_started.wait()
    tenant_b_task = asyncio.create_task(
        manager.get_agent("default", tenant_id="tenant-b"),
    )
    await tenant_b_waiting_after_start.wait()
    tenant_a_may_return.set()
    workspace_a = await tenant_a_task
    workspace_b = manager.agents["tenant-b:default"]

    assert workspace_a.started is True
    assert workspace_a.stopped is False
    assert workspace_b.stopped is False

    tenant_b_may_return.set()
    assert await tenant_b_task is workspace_b
    assert workspace_b.stopped is False
    assert manager.agents["tenant-b:default"] is workspace_b


@pytest.mark.asyncio
async def test_workspace_cache_releases_returned_cold_start_after_return(
    monkeypatch,
) -> None:
    manager = MultiAgentManager(
        workspace_cache_max_size=1,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=4,
    )
    tenant_b_start_blocked = asyncio.Event()
    allow_tenant_b_start = asyncio.Event()
    original_evict_workspace_cache = manager._evict_workspace_cache
    tenant_b_normal_eviction_protected_snapshots: list[set[str]] = []

    class ControlledWorkspace(_Workspace):
        async def start(self) -> None:
            if self.tenant_id == "tenant-b":
                tenant_b_start_blocked.set()
                await allow_tenant_b_start.wait()
            await super().start()

    async def controlled_evict_workspace_cache(
        *,
        protected_keys: set[str] | None = None,
    ) -> None:
        if protected_keys == {"tenant-b:default"}:
            tenant_b_normal_eviction_protected_snapshots.append(
                manager._workspace_eviction_protected_keys(protected_keys),
            )
        await original_evict_workspace_cache(protected_keys=protected_keys)

    monkeypatch.setattr(manager_module, "Workspace", ControlledWorkspace)
    monkeypatch.setattr(
        manager,
        "_evict_workspace_cache",
        controlled_evict_workspace_cache,
    )
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    tenant_b_task = asyncio.create_task(
        manager.get_agent("default", tenant_id="tenant-b"),
    )
    await tenant_b_start_blocked.wait()
    workspace_a = await manager.get_agent("default", tenant_id="tenant-a")

    assert workspace_a.stopped is False

    allow_tenant_b_start.set()
    workspace_b = await tenant_b_task

    assert tenant_b_normal_eviction_protected_snapshots[0] == {
        "tenant-b:default",
    }
    assert workspace_a.stopped is True
    assert workspace_b.stopped is False
    assert len(manager.agents) == manager.workspace_cache_max_size


@pytest.mark.asyncio
async def test_workspace_cache_completed_starts_are_evictable_during_hung_start(
    monkeypatch,
) -> None:
    manager = MultiAgentManager(
        workspace_cache_max_size=1,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=4,
    )
    tenant_a_start_blocked = asyncio.Event()
    allow_tenant_a_start = asyncio.Event()

    class ControlledWorkspace(_Workspace):
        async def start(self) -> None:
            if self.tenant_id == "tenant-a":
                tenant_a_start_blocked.set()
                await allow_tenant_a_start.wait()
            await super().start()

    monkeypatch.setattr(manager_module, "Workspace", ControlledWorkspace)
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    tenant_a_task = asyncio.create_task(
        manager.get_agent("default", tenant_id="tenant-a"),
    )
    await tenant_a_start_blocked.wait()

    workspace_b = await manager.get_agent("default", tenant_id="tenant-b")
    workspace_c = await manager.get_agent("default", tenant_id="tenant-c")

    assert workspace_b.stopped is True
    assert workspace_c.stopped is False
    assert len(manager.agents) == manager.workspace_cache_max_size
    assert manager._agent_start_eviction_protected_keys == {
        "tenant-a:default",
    }

    allow_tenant_a_start.set()
    workspace_a = await tenant_a_task

    assert workspace_a.started is True


@pytest.mark.asyncio
async def test_workspace_cache_retry_keeps_returned_workspace_alive(
    monkeypatch,
) -> None:
    manager = MultiAgentManager(
        workspace_cache_max_size=1,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=4,
    )
    tenant_a_eviction_started = asyncio.Event()
    allow_tenant_a_eviction = asyncio.Event()
    original_evict_workspace_cache = manager._evict_workspace_cache
    start_eviction_calls = 0

    async def controlled_evict_workspace_cache(
        *,
        protected_keys: set[str] | None = None,
    ) -> None:
        nonlocal start_eviction_calls
        if protected_keys in (
            {"tenant-a:default"},
            {"tenant-b:default"},
        ):
            start_eviction_calls += 1
            if (
                protected_keys == {"tenant-a:default"}
                and start_eviction_calls == 1
            ):
                tenant_a_eviction_started.set()
                await allow_tenant_a_eviction.wait()
            if start_eviction_calls <= 2:
                protected_keys = {
                    "tenant-a:default",
                    "tenant-b:default",
                }
        await original_evict_workspace_cache(protected_keys=protected_keys)

    monkeypatch.setattr(manager_module, "Workspace", _Workspace)
    monkeypatch.setattr(
        manager,
        "_evict_workspace_cache",
        controlled_evict_workspace_cache,
    )
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    tenant_a_task = asyncio.create_task(
        manager.get_agent("default", tenant_id="tenant-a"),
    )
    await tenant_a_eviction_started.wait()
    workspace_b = await manager.get_agent(
        "default",
        tenant_id="tenant-b",
    )
    allow_tenant_a_eviction.set()
    workspace_a = await tenant_a_task

    assert start_eviction_calls >= 2
    assert workspace_a.started is True
    assert workspace_a.stopped is False
    assert workspace_b.started is True
    assert len(manager.agents) == manager.workspace_cache_max_size
    assert manager.agents["tenant-a:default"] is workspace_a


@pytest.mark.asyncio
async def test_workspace_cache_retry_restores_capacity_after_cold_start_burst(
    monkeypatch,
) -> None:
    manager = MultiAgentManager(
        workspace_cache_max_size=1,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=4,
    )
    tenant_a_eviction_started = asyncio.Event()
    allow_tenant_a_eviction = asyncio.Event()
    original_evict_workspace_cache = manager._evict_workspace_cache
    start_eviction_calls = 0

    async def controlled_evict_workspace_cache(
        *,
        protected_keys: set[str] | None = None,
    ) -> None:
        nonlocal start_eviction_calls
        if protected_keys in (
            {"tenant-a:default"},
            {"tenant-b:default"},
        ):
            start_eviction_calls += 1
            if (
                protected_keys == {"tenant-a:default"}
                and start_eviction_calls == 1
            ):
                tenant_a_eviction_started.set()
                await allow_tenant_a_eviction.wait()
            if start_eviction_calls <= 2:
                protected_keys = {
                    "tenant-a:default",
                    "tenant-b:default",
                }
        await original_evict_workspace_cache(protected_keys=protected_keys)

    monkeypatch.setattr(manager_module, "Workspace", _Workspace)
    monkeypatch.setattr(
        manager,
        "_evict_workspace_cache",
        controlled_evict_workspace_cache,
    )
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    tenant_a_task = asyncio.create_task(
        manager.get_agent("default", tenant_id="tenant-a"),
    )
    await tenant_a_eviction_started.wait()
    workspace_b = await manager.get_agent(
        "default",
        tenant_id="tenant-b",
    )
    allow_tenant_a_eviction.set()
    workspace_a = await tenant_a_task

    assert workspace_a.started is True
    assert workspace_b.started is True
    assert len(manager.agents) == manager.workspace_cache_max_size
    assert manager.workspace_cache_metrics()["workspace_evictions_total"] == 1


@pytest.mark.asyncio
async def test_workspace_start_concurrency_is_limited(monkeypatch) -> None:
    manager = MultiAgentManager(
        workspace_cache_max_size=10,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=2,
    )
    in_flight = 0
    max_in_flight = 0

    class CountingWorkspace(_Workspace):
        async def start(self) -> None:
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            await super().start()

    monkeypatch.setattr(manager_module, "Workspace", CountingWorkspace)
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    await asyncio.gather(
        *[
            manager.get_agent("default", tenant_id=f"tenant-{index}")
            for index in range(8)
        ],
    )

    assert max_in_flight == 2
