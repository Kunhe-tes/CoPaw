# -*- coding: utf-8 -*-
"""验证 MultiAgentManager 按 cache key 去重并发启动。"""

from __future__ import annotations

import asyncio
import gc
import weakref
from contextlib import suppress
from types import SimpleNamespace
from typing import Any

import pytest

import swe.app.multi_agent_manager as manager_module
import swe.app.workspace.workspace as workspace_module
from swe.app.multi_agent_manager import MultiAgentManager
from swe.app.workspace.service_manager import ServiceDescriptor, ServiceManager
from swe.app.workspace.workspace import Workspace


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
        self.stop_calls: list[dict[str, Any]] = []
        self.manager = None

    async def start(self) -> None:
        self.started = True

    async def stop(self, *_args: Any, **_kwargs: Any) -> None:
        self.stop_calls.append({"args": _args, "kwargs": _kwargs})
        self.stopped = True

    def set_manager(self, manager: MultiAgentManager) -> None:
        self.manager = manager


class _TaskTracker:
    def __init__(self, *, has_active_tasks: bool = False) -> None:
        self._has_active_tasks = has_active_tasks

    async def has_active_tasks(self) -> bool:
        return self._has_active_tasks

    async def list_active_tasks(self) -> list[str]:
        return ["task-1"] if self._has_active_tasks else []

    async def wait_all_done(self, *, timeout: float) -> bool:
        return not self._has_active_tasks


@pytest.mark.asyncio
async def test_service_manager_final_stop_clears_stopped_service_references(
    tmp_path,
) -> None:
    workspace = SimpleNamespace(agent_id="default")
    service_manager = ServiceManager(workspace)
    stopped: list[str] = []

    class Service:
        def __init__(self, name: str) -> None:
            self.name = name

        async def stop(self) -> None:
            stopped.append(self.name)

    service_manager.register(
        ServiceDescriptor(
            name="runner",
            service_class=None,
            stop_method="stop",
            priority=10,
        ),
    )
    service_manager.register(
        ServiceDescriptor(
            name="memory_manager",
            service_class=None,
            stop_method="stop",
            reusable=True,
            priority=20,
        ),
    )
    service_manager.services["runner"] = Service("runner")
    service_manager.services["memory_manager"] = Service("memory_manager")

    await service_manager.stop_all(final=True)

    assert stopped == ["memory_manager", "runner"]
    assert service_manager.services == {}
    assert service_manager.reused_services == set()
    assert service_manager.workspace is None


@pytest.mark.asyncio
async def test_service_manager_final_stop_clears_service_refs_on_stop_error(
    tmp_path,
) -> None:
    workspace = SimpleNamespace(agent_id="default")
    service_manager = ServiceManager(workspace)

    class FailingService:
        async def stop(self) -> None:
            raise RuntimeError("stop failed")

    service_manager.register(
        ServiceDescriptor(
            name="memory_manager",
            service_class=None,
            stop_method="stop",
            reusable=True,
            priority=20,
        ),
    )
    service_manager.services["memory_manager"] = FailingService()
    service_manager.reused_services.add("memory_manager")

    await service_manager.stop_all(final=True)

    assert service_manager.services == {}
    assert service_manager.reused_services == set()
    assert service_manager.workspace is None


@pytest.mark.asyncio
async def test_service_manager_reload_stop_keeps_reusable_service_reference(
    tmp_path,
) -> None:
    workspace = SimpleNamespace(agent_id="default")
    service_manager = ServiceManager(workspace)
    stopped: list[str] = []

    class Service:
        def __init__(self, name: str) -> None:
            self.name = name

        async def stop(self) -> None:
            stopped.append(self.name)

    service_manager.register(
        ServiceDescriptor(
            name="runner",
            service_class=None,
            stop_method="stop",
            priority=10,
        ),
    )
    service_manager.register(
        ServiceDescriptor(
            name="memory_manager",
            service_class=None,
            stop_method="stop",
            reusable=True,
            priority=20,
        ),
    )
    service_manager.services["runner"] = Service("runner")
    service_manager.services["memory_manager"] = Service("memory_manager")

    await service_manager.stop_all(final=False)

    assert stopped == ["runner"]
    assert set(service_manager.services) == {"memory_manager"}
    assert service_manager.workspace is workspace


@pytest.mark.asyncio
async def test_workspace_final_stop_releases_reverse_service_references(
    tmp_path,
) -> None:
    class Runner:
        def __init__(self) -> None:
            self._workspace = None
            self._chat_manager = object()
            self._manager = object()
            self.memory_manager = object()

        def set_workspace(self, workspace) -> None:
            self._workspace = workspace

        def set_chat_manager(self, chat_manager) -> None:
            self._chat_manager = chat_manager

    class ChannelManager:
        def __init__(self) -> None:
            self._workspace = None

        def set_workspace(self, workspace) -> None:
            self._workspace = workspace

    class FakeServiceManager:
        def __init__(self, services) -> None:
            self.services = services

        async def stop_all(self, *, final: bool, stop_reused: bool) -> None:
            assert final is True
            assert stop_reused is True

    async def build_and_stop_workspace():
        workspace = Workspace.__new__(Workspace)
        workspace.agent_id = "default"
        workspace.workspace_dir = tmp_path
        workspace.tenant_id = "tenant-a"
        workspace._config = object()
        workspace._manager = object()
        workspace._started = True
        workspace._starting = False
        runner = Runner()
        channel_manager = ChannelManager()
        runner.set_workspace(workspace)
        channel_manager.set_workspace(workspace)
        workspace._service_manager = FakeServiceManager(
            {
                "runner": runner,
                "channel_manager": channel_manager,
            },
        )

        workspace_ref = weakref.ref(workspace)
        await Workspace.stop(workspace, final=True)
        return workspace_ref, runner, channel_manager

    workspace_ref, runner, channel_manager = await build_and_stop_workspace()
    gc.collect()

    assert workspace_ref() is None
    assert runner._workspace is None
    assert runner._chat_manager is None
    assert runner._manager is None
    assert runner.memory_manager is None
    assert channel_manager._workspace is None


@pytest.mark.asyncio
async def test_workspace_ttl_cleanup_loop_evicts_idle_workspaces() -> None:
    manager = MultiAgentManager(
        workspace_cache_max_size=10,
        workspace_idle_ttl_seconds=10,
        monotonic_time=lambda: 100.0,
    )
    workspace = _Workspace(
        agent_id="default",
        workspace_dir="/tmp/default",
        tenant_id="tenant-a",
    )
    workspace.task_tracker = _TaskTracker(has_active_tasks=False)
    manager.agents["tenant-a:default"] = workspace
    manager._touch_cache_entry("tenant-a:default", workspace)
    manager._monotonic_time = lambda: 111.0

    await manager.start_workspace_cleanup_loop(interval_seconds=0.01)
    try:
        for _ in range(50):
            if workspace.stopped:
                break
            await asyncio.sleep(0.01)
    finally:
        await manager.stop_workspace_cleanup_loop()

    assert workspace.stopped is True
    assert "tenant-a:default" not in manager.agents


@pytest.mark.asyncio
async def test_stop_all_cancels_workspace_ttl_cleanup_loop() -> None:
    manager = MultiAgentManager()

    await manager.start_workspace_cleanup_loop(interval_seconds=60.0)
    cleanup_task = manager._workspace_cleanup_task
    assert cleanup_task is not None

    await manager.stop_all()

    assert cleanup_task.cancelled() is True
    assert manager._workspace_cleanup_task is None


@pytest.mark.asyncio
async def test_workspace_ttl_cleanup_loop_continues_after_eviction_error(
    monkeypatch,
) -> None:
    manager = MultiAgentManager()
    calls = 0
    second_call = asyncio.Event()

    async def fake_evict_workspace_cache() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient eviction failure")
        second_call.set()

    monkeypatch.setattr(
        manager,
        "_evict_workspace_cache",
        fake_evict_workspace_cache,
    )

    await manager.start_workspace_cleanup_loop(interval_seconds=0.01)
    try:
        await asyncio.wait_for(second_call.wait(), timeout=1.0)
    finally:
        await manager.stop_workspace_cleanup_loop()

    assert calls >= 2


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

    assert manager.workspace_cache_max_size == 16
    assert manager.workspace_start_max_concurrent == 4
    assert manager.workspace_idle_ttl_seconds == 60 * 60


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
async def test_workspace_cache_retry_keeps_returning_workspace_globally_protected(
    monkeypatch,
) -> None:
    manager = MultiAgentManager(
        workspace_cache_max_size=1,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=4,
    )
    tenant_a_first_eviction_started = asyncio.Event()
    allow_tenant_a_first_eviction = asyncio.Event()
    tenant_a_retry_eviction_started = asyncio.Event()
    allow_tenant_a_retry_eviction = asyncio.Event()
    original_evict_workspace_cache = manager._evict_workspace_cache
    tenant_a_eviction_calls = 0
    created: dict[str, _Workspace] = {}

    class TrackingWorkspace(_Workspace):
        async def start(self) -> None:
            await super().start()
            if self.tenant_id is not None:
                created[self.tenant_id] = self

    async def controlled_evict_workspace_cache(
        *,
        protected_keys: set[str] | None = None,
    ) -> None:
        nonlocal tenant_a_eviction_calls
        if protected_keys == {"tenant-a:default"}:
            tenant_a_eviction_calls += 1
            if tenant_a_eviction_calls == 1:
                tenant_a_first_eviction_started.set()
                await allow_tenant_a_first_eviction.wait()
                protected_keys = {
                    "tenant-a:default",
                    "tenant-b:default",
                }
            elif tenant_a_eviction_calls == 2:
                tenant_a_retry_eviction_started.set()
                await allow_tenant_a_retry_eviction.wait()
        await original_evict_workspace_cache(protected_keys=protected_keys)

    monkeypatch.setattr(manager_module, "Workspace", TrackingWorkspace)
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
    await tenant_a_first_eviction_started.wait()
    workspace_b = await manager.get_agent("default", tenant_id="tenant-b")
    allow_tenant_a_first_eviction.set()
    await tenant_a_retry_eviction_started.wait()

    workspace_c = await manager.get_agent("default", tenant_id="tenant-c")

    assert created["tenant-a"].stopped is False
    assert workspace_b.stopped is True
    assert workspace_c.stopped is False

    allow_tenant_a_retry_eviction.set()
    workspace_a = await tenant_a_task

    assert workspace_a is created["tenant-a"]
    assert workspace_a.stopped is False
    assert manager.agents["tenant-a:default"] is workspace_a
    assert len(manager.agents) == manager.workspace_cache_max_size


@pytest.mark.asyncio
async def test_workspace_cache_retry_cancellation_releases_start_protection(
    monkeypatch,
) -> None:
    manager = MultiAgentManager(
        workspace_cache_max_size=1,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=4,
    )
    tenant_x = _Workspace(
        agent_id="default",
        workspace_dir="/tmp/default",
        tenant_id="tenant-x",
    )
    manager.agents["tenant-x:default"] = tenant_x
    manager._touch_cache_entry("tenant-x:default", tenant_x)
    manager._agent_start_eviction_protected_keys.add("tenant-x:default")
    original_evict_workspace_cache = manager._evict_workspace_cache
    tenant_a_eviction_calls = 0
    retry_eviction_started = asyncio.Event()
    retry_eviction_may_cancel = asyncio.Event()

    async def controlled_evict_workspace_cache(
        *,
        protected_keys: set[str] | None = None,
    ) -> None:
        nonlocal tenant_a_eviction_calls
        if protected_keys == {"tenant-a:default"}:
            tenant_a_eviction_calls += 1
            if tenant_a_eviction_calls == 2:
                retry_eviction_started.set()
                await retry_eviction_may_cancel.wait()
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
    await retry_eviction_started.wait()
    tenant_a_task.cancel()
    retry_eviction_may_cancel.set()

    with pytest.raises(asyncio.CancelledError):
        await tenant_a_task

    assert "tenant-a:default" not in (
        manager._agent_start_eviction_protected_keys
    )


@pytest.mark.asyncio
async def test_eviction_stop_failure_keeps_workspace_managed() -> None:
    manager = MultiAgentManager(
        workspace_cache_max_size=1,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=4,
    )

    class StopFailingWorkspace(_Workspace):
        async def stop(self, *_args: Any, **_kwargs: Any) -> None:
            await super().stop(*_args, **_kwargs)
            raise RuntimeError("stop failed")

    workspace = StopFailingWorkspace(
        agent_id="default",
        workspace_dir="/tmp/default",
        tenant_id="tenant-a",
    )
    manager.agents["tenant-a:default"] = workspace
    manager._touch_cache_entry("tenant-a:default", workspace)

    removals = await manager._evict_workspace_candidates(
        [("tenant-a:default", workspace, 1000.0, 1)],
        protected_keys=None,
    )

    assert removals == 0
    assert manager.agents["tenant-a:default"] is workspace
    assert manager._agent_cache_entries["tenant-a:default"].workspace is (
        workspace
    )
    assert (
        manager.workspace_cache_metrics()[
            "workspace_eviction_stop_failures_total"
        ]
        == 1
    )


@pytest.mark.asyncio
async def test_eviction_stop_runs_outside_manager_lock() -> None:
    manager = MultiAgentManager(
        workspace_cache_max_size=1,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=4,
    )
    stop_entered = asyncio.Event()
    release_stop = asyncio.Event()

    class SlowStoppingWorkspace(_Workspace):
        async def stop(self, *_args: Any, **_kwargs: Any) -> None:
            stop_entered.set()
            await release_stop.wait()
            await super().stop(*_args, **_kwargs)

    evicted = SlowStoppingWorkspace(
        agent_id="default",
        workspace_dir="/tmp/default",
        tenant_id="tenant-a",
    )
    cached = _Workspace(
        agent_id="default",
        workspace_dir="/tmp/default",
        tenant_id="tenant-b",
    )
    manager.agents["tenant-a:default"] = evicted
    manager._touch_cache_entry("tenant-a:default", evicted)
    manager.agents["tenant-b:default"] = cached
    manager._touch_cache_entry("tenant-b:default", cached)

    eviction_task = asyncio.create_task(
        manager._evict_workspace_candidates(
            [("tenant-a:default", evicted, 1000.0, 1)],
            protected_keys=None,
        ),
    )
    await stop_entered.wait()

    try:
        result = await asyncio.wait_for(
            manager.get_agent("default", tenant_id="tenant-b"),
            timeout=0.05,
        )
    finally:
        release_stop.set()

    removals = await eviction_task

    assert result is cached
    assert removals == 1
    assert "tenant-a:default" not in manager.agents
    assert cached.stopped is False


@pytest.mark.asyncio
async def test_eviction_stop_failure_does_not_restore_over_replacement(
    monkeypatch,
) -> None:
    manager = MultiAgentManager(
        workspace_cache_max_size=10,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=4,
    )
    stop_entered = asyncio.Event()
    release_stop = asyncio.Event()

    class StopFailingWorkspace(_Workspace):
        async def stop(self, *_args: Any, **_kwargs: Any) -> None:
            stop_entered.set()
            await release_stop.wait()
            raise RuntimeError("stop failed")

    replacement = _Workspace(
        agent_id="default",
        workspace_dir="/tmp/default",
        tenant_id="tenant-a",
    )

    def workspace_factory(**_kwargs: Any) -> _Workspace:
        return replacement

    evicted = StopFailingWorkspace(
        agent_id="default",
        workspace_dir="/tmp/default",
        tenant_id="tenant-a",
    )
    manager.agents["tenant-a:default"] = evicted
    manager._touch_cache_entry("tenant-a:default", evicted)
    monkeypatch.setattr(manager_module, "Workspace", workspace_factory)
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    eviction_task = asyncio.create_task(
        manager._evict_workspace_candidates(
            [("tenant-a:default", evicted, 1000.0, 1)],
            protected_keys=None,
        ),
    )
    await stop_entered.wait()

    assert await manager.get_agent("default", tenant_id="tenant-a") is (
        replacement
    )
    release_stop.set()
    removals = await eviction_task

    assert removals == 0
    assert manager.agents["tenant-a:default"] is replacement
    assert manager._agent_cache_entries["tenant-a:default"].workspace is (
        replacement
    )


@pytest.mark.asyncio
async def test_workspace_stop_cleans_starting_services_before_started(
    tmp_path,
) -> None:
    workspace = Workspace("default", tmp_path)
    stop_calls: list[dict[str, Any]] = []

    class FakeServiceManager:
        services = {"runner": object()}

        async def stop_all(
            self,
            *,
            final: bool = False,
            stop_reused: bool = True,
        ) -> None:
            stop_calls.append(
                {"final": final, "stop_reused": stop_reused},
            )

    workspace._service_manager = FakeServiceManager()
    workspace._starting = True
    workspace._started = False

    await workspace.stop()

    assert stop_calls == [{"final": True, "stop_reused": True}]
    assert workspace._started is False
    assert workspace._starting is False


@pytest.mark.asyncio
async def test_workspace_start_cancellation_stops_partially_started_services(
    tmp_path,
) -> None:
    workspace = Workspace("default", tmp_path)
    start_entered = asyncio.Event()
    cancel_may_finish = asyncio.Event()
    stop_calls: list[dict[str, Any]] = []

    class FakeServiceManager:
        services = {"runner": object()}

        async def start_all(self) -> None:
            start_entered.set()
            await cancel_may_finish.wait()

        async def stop_all(
            self,
            *,
            final: bool = False,
            stop_reused: bool = True,
        ) -> None:
            stop_calls.append(
                {"final": final, "stop_reused": stop_reused},
            )

    workspace._service_manager = FakeServiceManager()
    workspace._config = object()

    start_task = asyncio.create_task(workspace.start())
    await start_entered.wait()
    start_task.cancel()
    cancel_may_finish.set()

    with pytest.raises(asyncio.CancelledError):
        await start_task

    assert stop_calls == [{"final": True, "stop_reused": False}]
    assert workspace._started is False
    assert workspace._starting is False


@pytest.mark.asyncio
async def test_workspace_start_cancellation_preserves_reused_services(
    tmp_path,
) -> None:
    workspace = Workspace("default", tmp_path)
    start_entered = asyncio.Event()
    cancel_may_finish = asyncio.Event()
    stop_calls: list[dict[str, Any]] = []

    class FakeServiceManager:
        reused_services = {"memory_manager"}

        async def start_all(self) -> None:
            start_entered.set()
            await cancel_may_finish.wait()

        async def stop_all(
            self,
            *,
            final: bool = False,
            stop_reused: bool = True,
        ) -> None:
            stop_calls.append(
                {"final": final, "stop_reused": stop_reused},
            )

    workspace._service_manager = FakeServiceManager()
    workspace._config = object()

    start_task = asyncio.create_task(workspace.start())
    await start_entered.wait()
    start_task.cancel()
    cancel_may_finish.set()

    with pytest.raises(asyncio.CancelledError):
        await start_task

    assert stop_calls == [{"final": True, "stop_reused": False}]
    assert workspace._started is False
    assert workspace._starting is False


@pytest.mark.asyncio
async def test_reload_cancellation_preserves_old_reused_services(
    monkeypatch,
    tmp_path,
) -> None:
    manager = MultiAgentManager()
    cache_key = "tenant-a:default"
    start_entered = asyncio.Event()
    cancel_may_finish = asyncio.Event()
    cleanup_stop_calls: list[dict[str, Any]] = []

    class ReusedService:
        def __init__(self) -> None:
            self.stopped = False

        async def close(self) -> None:
            self.stopped = True

    reused_service = ReusedService()

    class OldServiceManager:
        def get_reusable_services(self) -> dict[str, Any]:
            return {"memory_manager": reused_service}

    old_workspace = SimpleNamespace(_service_manager=OldServiceManager())
    manager.agents[cache_key] = old_workspace
    manager._touch_cache_entry(cache_key, old_workspace)

    class FakeNewServiceManager:
        def __init__(self) -> None:
            self.services: dict[str, Any] = {}
            self.reused_services: set[str] = set()

        async def set_reusable(self, name: str, instance: Any) -> None:
            self.services[name] = instance
            self.reused_services.add(name)

        async def start_all(self) -> None:
            start_entered.set()
            await cancel_may_finish.wait()

        async def stop_all(
            self,
            *,
            final: bool = False,
            stop_reused: bool = True,
        ) -> None:
            cleanup_stop_calls.append(
                {"final": final, "stop_reused": stop_reused},
            )
            if final and stop_reused:
                service = self.services.get("memory_manager")
                if service is not None:
                    await service.close()

    class ReloadWorkspace(Workspace):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._service_manager = FakeNewServiceManager()

    monkeypatch.setattr(manager_module, "Workspace", ReloadWorkspace)
    monkeypatch.setattr(
        workspace_module,
        "load_agent_config",
        lambda _agent_id, tenant_id=None: object(),
    )
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    reload_task = asyncio.create_task(
        manager.reload_agent("default", tenant_id="tenant-a"),
    )
    await start_entered.wait()
    reload_task.cancel()
    cancel_may_finish.set()

    with pytest.raises(asyncio.CancelledError):
        await reload_task

    assert cleanup_stop_calls == [{"final": True, "stop_reused": False}]
    assert reused_service.stopped is False
    assert manager.agents[cache_key] is old_workspace


@pytest.mark.asyncio
async def test_reload_cancellation_after_new_start_stops_uncached_workspace(
    monkeypatch,
) -> None:
    manager = MultiAgentManager()
    cache_key = "tenant-a:default"
    new_set_manager_called = asyncio.Event()
    release_swap_lock = asyncio.Event()
    old_workspace = _Workspace(
        agent_id="default",
        workspace_dir="/tmp/default",
        tenant_id="tenant-a",
    )
    created: list[_Workspace] = []

    old_workspace._service_manager = SimpleNamespace(
        get_reusable_services=lambda: {},
    )

    class ReloadWorkspace(_Workspace):
        def set_manager(self, manager: MultiAgentManager) -> None:
            super().set_manager(manager)
            new_set_manager_called.set()

    def workspace_factory(**kwargs: Any) -> ReloadWorkspace:
        workspace = ReloadWorkspace(**kwargs)
        created.append(workspace)
        return workspace

    original_lock = manager._lock
    lock_entries = 0

    class DelayedLock:
        async def __aenter__(self):
            nonlocal lock_entries
            lock_entries += 1
            if lock_entries >= 3:
                await release_swap_lock.wait()
            return await original_lock.__aenter__()

        async def __aexit__(self, exc_type, exc, tb):
            return await original_lock.__aexit__(exc_type, exc, tb)

    manager.agents[cache_key] = old_workspace
    manager._touch_cache_entry(cache_key, old_workspace)
    monkeypatch.setattr(manager_module, "Workspace", workspace_factory)
    monkeypatch.setattr(manager, "_lock", DelayedLock())
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    reload_task = asyncio.create_task(
        manager.reload_agent("default", tenant_id="tenant-a"),
    )
    await new_set_manager_called.wait()
    reload_task.cancel()
    release_swap_lock.set()

    with pytest.raises(asyncio.CancelledError):
        await reload_task

    new_workspace = created[0]
    assert new_workspace.started is True
    assert new_workspace.stopped is True
    assert manager.agents[cache_key] is old_workspace


@pytest.mark.asyncio
async def test_stop_all_cleans_up_reloaded_old_workspace_on_cancel() -> None:
    manager = MultiAgentManager()
    cleanup_started = asyncio.Event()
    cleanup_may_cancel = asyncio.Event()
    old_workspace = _Workspace(
        agent_id="default",
        workspace_dir="/tmp/default",
        tenant_id="tenant-a",
    )

    class BlockingTaskTracker(_TaskTracker):
        async def wait_all_done(self, *, timeout: float) -> bool:
            cleanup_started.set()
            await cleanup_may_cancel.wait()
            return False

    old_workspace.task_tracker = BlockingTaskTracker(has_active_tasks=True)

    await manager._graceful_stop_old_instance(old_workspace, "default")
    await cleanup_started.wait()

    stop_all_task = asyncio.create_task(manager.stop_all())
    cleanup_may_cancel.set()
    await stop_all_task

    assert old_workspace.stopped is True
    assert old_workspace.stop_calls[-1]["kwargs"] == {"final": False}


@pytest.mark.asyncio
async def test_stop_agent_cancels_inflight_start_before_cache_insert(
    monkeypatch,
) -> None:
    manager = MultiAgentManager()
    start_entered = asyncio.Event()
    created: list[_Workspace] = []

    class BlockingWorkspace(_Workspace):
        async def start(self) -> None:
            created.append(self)
            start_entered.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(manager_module, "Workspace", BlockingWorkspace)
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    get_task = asyncio.create_task(
        manager.get_agent("default", tenant_id="tenant-a"),
    )
    await start_entered.wait()

    assert await manager.stop_agent("default", tenant_id="tenant-a") is True
    with pytest.raises(asyncio.CancelledError):
        await get_task

    assert manager.agents == {}
    assert manager._agent_start_tasks == {}
    assert created[0].stopped is True


@pytest.mark.asyncio
async def test_stop_all_cancels_inflight_starts_before_shutdown(
    monkeypatch,
) -> None:
    manager = MultiAgentManager()
    start_entered = asyncio.Event()
    created: list[_Workspace] = []

    class BlockingWorkspace(_Workspace):
        async def start(self) -> None:
            created.append(self)
            start_entered.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(manager_module, "Workspace", BlockingWorkspace)
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    get_task = asyncio.create_task(
        manager.get_agent("default", tenant_id="tenant-a"),
    )
    await start_entered.wait()

    await manager.stop_all()
    with pytest.raises(asyncio.CancelledError):
        await get_task

    assert manager.agents == {}
    assert manager._agent_start_tasks == {}
    assert created[0].stopped is True


@pytest.mark.asyncio
async def test_cancelled_waiters_evict_background_starts_over_capacity(
    monkeypatch,
) -> None:
    manager = MultiAgentManager(
        workspace_cache_max_size=1,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=4,
    )
    started_tenants: set[str] = set()
    all_starts_entered = asyncio.Event()
    allow_starts_to_finish = asyncio.Event()
    created: dict[str, _Workspace] = {}

    class ControlledWorkspace(_Workspace):
        async def start(self) -> None:
            assert self.tenant_id is not None
            created[self.tenant_id] = self
            started_tenants.add(self.tenant_id)
            if started_tenants == {"tenant-a", "tenant-b"}:
                all_starts_entered.set()
            await allow_starts_to_finish.wait()
            await super().start()

    monkeypatch.setattr(manager_module, "Workspace", ControlledWorkspace)
    monkeypatch.setattr(
        manager,
        "_load_agent_config_for_tenant",
        lambda _tenant_id=None: _config("default"),
    )

    task_a = asyncio.create_task(
        manager.get_agent("default", tenant_id="tenant-a"),
    )
    task_b = asyncio.create_task(
        manager.get_agent("default", tenant_id="tenant-b"),
    )
    await all_starts_entered.wait()

    task_a.cancel()
    task_b.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task_a
    with pytest.raises(asyncio.CancelledError):
        await task_b

    start_tasks = list(manager._agent_start_tasks.values())
    allow_starts_to_finish.set()
    await asyncio.gather(
        *start_tasks,
        return_exceptions=True,
    )

    assert len(manager.agents) == manager.workspace_cache_max_size
    assert sum(workspace.stopped for workspace in created.values()) == 1


@pytest.mark.asyncio
async def test_concurrent_capacity_evictions_do_not_over_evict() -> None:
    manager = MultiAgentManager(
        workspace_cache_max_size=1,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=4,
    )
    first_stop_entered = asyncio.Event()
    release_first_stop = asyncio.Event()
    stop_calls = 0

    class BlockingFirstStopWorkspace(_Workspace):
        async def stop(self, *_args: Any, **_kwargs: Any) -> None:
            nonlocal stop_calls
            stop_calls += 1
            if stop_calls == 1:
                first_stop_entered.set()
                await release_first_stop.wait()
            await super().stop(*_args, **_kwargs)

    workspace_a = BlockingFirstStopWorkspace(
        agent_id="default",
        workspace_dir="/tmp/default",
        tenant_id="tenant-a",
    )
    workspace_b = BlockingFirstStopWorkspace(
        agent_id="default",
        workspace_dir="/tmp/default",
        tenant_id="tenant-b",
    )
    manager.agents["tenant-a:default"] = workspace_a
    manager._touch_cache_entry("tenant-a:default", workspace_a)
    manager.agents["tenant-b:default"] = workspace_b
    manager._touch_cache_entry("tenant-b:default", workspace_b)

    eviction_a = asyncio.create_task(
        manager._evict_workspace_candidates(
            [("tenant-b:default", workspace_b, 1000.0, 2)],
            protected_keys={"tenant-a:default"},
            max_removals=1,
        ),
    )
    await first_stop_entered.wait()
    eviction_b = asyncio.create_task(
        manager._evict_workspace_candidates(
            [("tenant-a:default", workspace_a, 1000.0, 1)],
            protected_keys={"tenant-b:default"},
            max_removals=1,
        ),
    )
    await asyncio.sleep(0)
    release_first_stop.set()

    await asyncio.gather(eviction_a, eviction_b)

    assert len(manager.agents) == manager.workspace_cache_max_size
    assert (
        sum(workspace.stopped for workspace in (workspace_a, workspace_b)) == 1
    )


@pytest.mark.asyncio
async def test_capacity_eviction_rechecks_after_failed_inflight_restore() -> (
    None
):
    manager = MultiAgentManager(
        workspace_cache_max_size=1,
        workspace_idle_ttl_seconds=6 * 60 * 60,
        workspace_start_max_concurrent=4,
    )
    first_stop_entered = asyncio.Event()
    release_first_stop = asyncio.Event()

    class StopFailingWorkspace(_Workspace):
        async def stop(self, *_args: Any, **_kwargs: Any) -> None:
            if self.tenant_id == "tenant-b":
                first_stop_entered.set()
                await release_first_stop.wait()
                raise RuntimeError("stop failed")
            await super().stop(*_args, **_kwargs)

    workspace_a = StopFailingWorkspace(
        agent_id="default",
        workspace_dir="/tmp/default",
        tenant_id="tenant-a",
    )
    workspace_b = StopFailingWorkspace(
        agent_id="default",
        workspace_dir="/tmp/default",
        tenant_id="tenant-b",
    )
    manager.agents["tenant-a:default"] = workspace_a
    manager._touch_cache_entry("tenant-a:default", workspace_a)
    manager.agents["tenant-b:default"] = workspace_b
    manager._touch_cache_entry("tenant-b:default", workspace_b)

    eviction_a = asyncio.create_task(
        manager._evict_workspace_cache(
            protected_keys={"tenant-a:default"},
        ),
    )
    await first_stop_entered.wait()
    eviction_b = asyncio.create_task(
        manager._evict_workspace_cache(
            protected_keys={"tenant-b:default"},
        ),
    )
    await asyncio.sleep(0)
    release_first_stop.set()

    await asyncio.gather(eviction_a, eviction_b)

    assert manager.agents == {"tenant-b:default": workspace_b}
    assert workspace_a.stopped is True
    assert workspace_b.stopped is False


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
