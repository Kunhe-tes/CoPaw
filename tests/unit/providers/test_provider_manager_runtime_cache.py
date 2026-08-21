# -*- coding: utf-8 -*-
"""RED tests for scoped ProviderManager runtime initialization and freshness."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio

from swe.providers.provider_manager import ProviderManager
from swe.providers.provider import ModelInfo, ProviderInfo


def _manager_for(scope: str) -> ProviderManager:
    manager = object.__new__(ProviderManager)
    manager.tenant_id = scope
    manager.builtin_providers = {}
    manager.custom_providers = {}
    manager._file_freshness_tokens = {}
    manager.root_path = Path("/") / scope
    manager.builtin_path = manager.root_path / "builtin"
    manager.custom_path = manager.root_path / "custom"
    manager.active_model = None
    return manager


@pytest_asyncio.fixture(autouse=True)
async def clear_provider_manager_cache() -> AsyncGenerator[None, None]:
    ProviderManager._instances.clear()
    ProviderManager._instance = None
    yield
    for registry_name in ("_inflight", "_instance_tasks"):
        registry = getattr(ProviderManager, registry_name, {})
        tasks = [
            task
            for task in registry.values()
            if isinstance(task, asyncio.Task)
        ]
        for task in tasks:
            if isinstance(task, asyncio.Task) and not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        registry.clear()
    ProviderManager._instances.clear()
    ProviderManager._instance = None


@pytest.mark.asyncio
async def test_get_or_create_instance_constructs_scope_once(monkeypatch):
    created: list[str] = []
    started = threading.Event()
    release = threading.Event()

    def build(scope: str):
        created.append(scope)
        started.set()
        release.wait(timeout=5)
        return _manager_for(scope)

    def init(self, scope="default"):
        built = build(scope)
        self.__dict__.update(built.__dict__)

    monkeypatch.setattr(ProviderManager, "__init__", init)

    first_task = asyncio.create_task(
        ProviderManager.get_or_create_instance("scope-a"),
    )
    await asyncio.to_thread(started.wait, 5)
    second_task = asyncio.create_task(
        ProviderManager.get_or_create_instance("scope-a"),
    )
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(asyncio.shield(second_task), timeout=0.01)
    release.set()
    first, second = await asyncio.gather(first_task, second_task)

    assert first is second
    assert created == ["scope-a"]


@pytest.mark.asyncio
async def test_cold_scope_does_not_block_other_scope_hit(monkeypatch):
    hot = _manager_for("scope-hot")
    ProviderManager._instances["scope-hot"] = hot

    def scope_entries(registry_name: str) -> set[object]:
        registry = getattr(ProviderManager, registry_name, {})
        return {
            key
            for key in registry
            if key == "scope-hot"
            or (isinstance(key, tuple) and "scope-hot" in key)
        }

    before_task_hot = scope_entries("_instance_tasks")
    before_inflight_hot = scope_entries("_inflight")
    started = threading.Event()
    blocker = threading.Event()

    def build(scope: str):
        started.set()
        blocker.wait(timeout=5)
        return _manager_for(scope)

    def init(self, scope="default"):
        built = build(scope)
        self.__dict__.update(built.__dict__)

    monkeypatch.setattr(ProviderManager, "__init__", init)
    cold = asyncio.create_task(
        ProviderManager.get_or_create_instance("scope-cold"),
    )
    assert await asyncio.to_thread(started.wait, 5)

    assert (
        await asyncio.wait_for(
            ProviderManager.get_or_create_instance("scope-hot"),
            timeout=0.5,
        )
        is hot
    )
    assert scope_entries("_instance_tasks") == before_task_hot
    assert scope_entries("_inflight") == before_inflight_hot

    blocker.set()
    assert isinstance(await cold, ProviderManager)


@pytest.mark.asyncio
async def test_different_cold_scopes_construct_concurrently(monkeypatch):
    started = {"scope-a": threading.Event(), "scope-b": threading.Event()}
    release = {"scope-a": threading.Event(), "scope-b": threading.Event()}

    def build(scope: str):
        started[scope].set()
        release[scope].wait(timeout=5)
        return _manager_for(scope)

    def init(self, scope="default"):
        built = build(scope)
        self.__dict__.update(built.__dict__)

    monkeypatch.setattr(ProviderManager, "__init__", init)
    task_a = asyncio.create_task(
        ProviderManager.get_or_create_instance("scope-a"),
    )
    assert await asyncio.to_thread(started["scope-a"].wait, 5)
    task_b = asyncio.create_task(
        ProviderManager.get_or_create_instance("scope-b"),
    )
    assert await asyncio.to_thread(started["scope-b"].wait, 5)
    release["scope-a"].set()
    release["scope-b"].set()

    result_a, result_b = await asyncio.gather(task_a, task_b)
    assert isinstance(result_a, ProviderManager)
    assert isinstance(result_b, ProviderManager)


@pytest.mark.asyncio
async def test_failed_scope_construction_can_retry(monkeypatch):
    attempts = 0

    def failing_init(self, scope="default"):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("construction failed")

    monkeypatch.setattr(ProviderManager, "__init__", failing_init)
    first, second = await asyncio.gather(
        ProviderManager.get_or_create_instance("scope-fail"),
        ProviderManager.get_or_create_instance("scope-fail"),
        return_exceptions=True,
    )
    assert isinstance(first, RuntimeError)
    assert isinstance(second, RuntimeError)
    assert attempts == 1

    def successful_init(self, scope="default"):
        self.__dict__.update(_manager_for(scope).__dict__)

    monkeypatch.setattr(ProviderManager, "__init__", successful_init)
    manager = await ProviderManager.get_or_create_instance("scope-fail")
    assert isinstance(manager, ProviderManager)


@pytest.mark.asyncio
async def test_owner_cancellation_clears_scope_inflight(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def init(self, scope="default"):
        started.set()
        release.wait(timeout=5)
        self.__dict__.update(_manager_for(scope).__dict__)

    monkeypatch.setattr(ProviderManager, "__init__", init)
    owner = asyncio.create_task(
        ProviderManager.get_or_create_instance("scope-cancel"),
    )
    assert await asyncio.to_thread(started.wait, 5)
    waiter = asyncio.create_task(
        ProviderManager.get_or_create_instance("scope-cancel"),
    )
    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await owner
    release.set()
    assert isinstance(await waiter, ProviderManager)
    for registry_name in ("_inflight", "_instance_tasks"):
        assert all(
            key[1] != "scope-cancel"
            for key in getattr(ProviderManager, registry_name, {})
        )


@pytest.mark.asyncio
async def test_refresh_if_due_is_single_flight(monkeypatch):
    manager = _manager_for("scope-a")
    manager._next_freshness_check_at = time.monotonic() - 1
    refreshes = 0

    def refresh():
        nonlocal refreshes
        refreshes += 1
        time.sleep(0.05)

    monkeypatch.setattr(manager, "_refresh_if_stale", refresh)
    await asyncio.gather(*[manager.refresh_if_due() for _ in range(3)])
    assert refreshes == 1


@pytest.mark.asyncio
async def test_provider_info_before_ttl_does_not_scan_files(monkeypatch):
    manager = _manager_for("scope-a")
    manager._next_freshness_check_at = time.monotonic() + 60
    monkeypatch.setattr(
        manager,
        "_refresh_if_stale",
        lambda: (_ for _ in ()).throw(AssertionError("freshness scan")),
    )

    monkeypatch.setattr(
        manager,
        "_get_provider_info_with_timing",
        lambda provider, provider_kind: asyncio.sleep(0),
    )
    assert await manager.list_provider_info() == []


@pytest.mark.asyncio
async def test_provider_info_after_ttl_refreshes(monkeypatch):
    manager = _manager_for("scope-a")
    manager._next_freshness_check_at = time.monotonic() - 1
    refreshed = []
    monkeypatch.setattr(
        manager,
        "_refresh_if_stale",
        lambda: refreshed.append(True),
    )

    assert await manager.list_provider_info() == []
    assert refreshed == [True]
    refreshed.clear()
    await manager.list_provider_info()
    assert refreshed == []
    assert manager._next_freshness_check_at > time.monotonic()


@pytest.mark.asyncio
async def test_provider_write_invalidates_only_affected_scope(
    monkeypatch,
    tmp_path,
):
    invalidated: list[str] = []
    monkeypatch.setattr(
        "swe.providers.provider_manager.reset_scope_bound_model_caches",
        lambda scope=None: invalidated.append(scope),
    )
    manager = _manager_for("scope-a")
    manager.root_path = tmp_path / "providers"
    manager.builtin_path = manager.root_path / "builtin"
    manager.custom_path = manager.root_path / "custom"
    manager.custom_path.mkdir(parents=True)
    manager.builtin_path.mkdir()

    await manager.add_custom_provider(
        ProviderInfo(
            id="custom",
            name="Custom",
            models=[ModelInfo(id="model", name="Model")],
        ),
    )

    written = manager.custom_path / "custom.json"
    assert written.exists()
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["id"] == "custom"
    assert "custom" in manager.custom_providers
    assert invalidated == ["scope-a"]
