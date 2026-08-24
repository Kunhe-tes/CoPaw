# -*- coding: utf-8 -*-
"""Contract tests for Provider persistence, cache, and catalog boundaries."""

from __future__ import annotations

import asyncio
import json
import os
import threading

import pytest

from swe.providers.provider import ModelInfo
from swe.providers.models import ModelSlotConfig
from swe.providers.openai_provider import OpenAIProvider
from swe.providers.provider_runtime_cache import ProviderRuntimeCache
from swe.providers.tenant_provider_repository import TenantProviderRepository


@pytest.fixture
def provider() -> OpenAIProvider:
    return OpenAIProvider(
        id="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key="sk-test-provider-boundary",
        models=[ModelInfo(id="gpt-5", name="GPT-5")],
        freeze_url=True,
    )


@pytest.fixture
def repository(tmp_path) -> TenantProviderRepository:
    return TenantProviderRepository(tmp_path / ".swe.secret")


def test_repository_uses_tenant_scoped_builtin_and_custom_paths(
    repository: TenantProviderRepository,
) -> None:
    paths = repository.prepare_scope("tenant-a")

    assert paths.root == repository.secret_dir / "tenant-a" / "providers"
    assert paths.builtin == paths.root / "builtin"
    assert paths.custom == paths.root / "custom"
    assert paths.builtin.is_dir()
    assert paths.custom.is_dir()


def test_repository_preserves_current_provider_json_bytes_and_tracks_writes(
    repository: TenantProviderRepository,
    provider: OpenAIProvider,
) -> None:
    before = repository.freshness_token("tenant-a")

    repository.write_provider(
        "tenant-a",
        provider.model_dump(),
        is_builtin=True,
    )

    provider_path = repository.builtin_path("tenant-a") / "openai.json"
    assert provider_path.read_bytes() == json.dumps(
        provider.model_dump(),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    assert repository.read_provider("tenant-a", "openai", is_builtin=True) == (
        provider.model_dump()
    )
    assert repository.freshness_token("tenant-a") != before


def test_repository_reads_and_writes_active_model_and_ignores_invalid_json(
    repository: TenantProviderRepository,
) -> None:
    active_model = ModelSlotConfig(provider_id="openai", model="gpt-5")

    repository.write_active_model("tenant-a", active_model)

    active_path = repository.root_path("tenant-a") / "active_model.json"
    assert active_path.read_bytes() == json.dumps(
        active_model.model_dump(),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    assert repository.read_active_model("tenant-a") == active_model

    active_path.write_text("{invalid-json", encoding="utf-8")
    assert repository.read_active_model("tenant-a") is None


def test_repository_seeds_a_new_scope_from_default_without_overwriting_itself(
    repository: TenantProviderRepository,
    provider: OpenAIProvider,
) -> None:
    repository.write_provider(
        "default",
        provider.model_dump(),
        is_builtin=True,
    )
    repository.write_active_model(
        "default",
        ModelSlotConfig(provider_id="openai", model="gpt-5"),
    )

    repository.prepare_scope("tenant-a")

    assert (
        repository.read_provider(
            "tenant-a",
            "openai",
            is_builtin=True,
        )
        == provider.model_dump()
    )
    assert repository.read_active_model("tenant-a") == ModelSlotConfig(
        provider_id="openai",
        model="gpt-5",
    )
    assert repository.root_path("tenant-a") != repository.root_path("default")


@pytest.mark.asyncio
async def test_runtime_cache_single_flights_same_scope() -> None:
    cache = ProviderRuntimeCache()
    started = asyncio.Event()
    release = asyncio.Event()
    builds = 0

    async def build() -> str:
        nonlocal builds
        builds += 1
        started.set()
        await release.wait()
        return "scope-a-state"

    first = asyncio.create_task(cache.get_or_create("scope-a", build))
    await started.wait()
    second = asyncio.create_task(cache.get_or_create("scope-a", build))
    await asyncio.sleep(0)
    assert builds == 1

    release.set()
    assert await asyncio.gather(first, second) == [
        "scope-a-state",
        "scope-a-state",
    ]


@pytest.mark.asyncio
async def test_runtime_cache_builds_different_scopes_concurrently() -> None:
    cache = ProviderRuntimeCache()
    started_a = asyncio.Event()
    started_b = asyncio.Event()
    release = asyncio.Event()

    async def build_a() -> str:
        started_a.set()
        await release.wait()
        return "scope-a-state"

    async def build_b() -> str:
        started_b.set()
        await release.wait()
        return "scope-b-state"

    task_a = asyncio.create_task(cache.get_or_create("scope-a", build_a))
    task_b = asyncio.create_task(cache.get_or_create("scope-b", build_b))
    await asyncio.wait_for(
        asyncio.gather(started_a.wait(), started_b.wait()),
        timeout=0.2,
    )

    release.set()
    assert await asyncio.gather(task_a, task_b) == [
        "scope-a-state",
        "scope-b-state",
    ]


@pytest.mark.asyncio
async def test_runtime_cache_clears_a_failed_single_flight_for_retry() -> None:
    cache = ProviderRuntimeCache()
    attempts = 0

    async def build() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient provider initialization failure")
        return "recovered-state"

    with pytest.raises(RuntimeError, match="transient provider"):
        await cache.get_or_create("scope-a", build)

    assert await cache.get_or_create("scope-a", build) == "recovered-state"
    assert attempts == 2


@pytest.mark.asyncio
async def test_runtime_cache_refreshes_due_scope_once() -> None:
    cache = ProviderRuntimeCache(freshness_ttl_seconds=60)
    refreshes = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def refresh() -> None:
        nonlocal refreshes
        refreshes += 1
        started.set()
        await release.wait()

    cache.mark_freshness_due("scope-a")
    first = asyncio.create_task(cache.refresh_if_due("scope-a", refresh))
    await started.wait()
    second = asyncio.create_task(cache.refresh_if_due("scope-a", refresh))
    await asyncio.sleep(0)
    assert refreshes == 1
    release.set()
    await asyncio.gather(first, second)
    await cache.refresh_if_due("scope-a", refresh)
    assert refreshes == 1


@pytest.mark.asyncio
async def test_runtime_cache_keeps_refresh_due_when_invalidated_inflight() -> (
    None
):
    cache = ProviderRuntimeCache(freshness_ttl_seconds=60)
    started = asyncio.Event()
    release = asyncio.Event()
    refreshes = 0

    async def refresh() -> None:
        nonlocal refreshes
        refreshes += 1
        started.set()
        await release.wait()

    cache.mark_freshness_due("scope-a")
    first = asyncio.create_task(cache.refresh_if_due("scope-a", refresh))
    await started.wait()
    cache.invalidate("scope-a")
    release.set()
    await first

    await cache.refresh_if_due("scope-a", refresh)

    assert refreshes == 2


@pytest.mark.asyncio
async def test_runtime_cache_invalidation_evicts_only_the_written_scope() -> (
    None
):
    cache = ProviderRuntimeCache()
    builds: list[str] = []

    async def build(scope: str) -> str:
        builds.append(scope)
        return f"{scope}-{len(builds)}"

    first_a = await cache.get_or_create("scope-a", lambda: build("scope-a"))
    first_b = await cache.get_or_create("scope-b", lambda: build("scope-b"))
    cache.invalidate("scope-a")

    second_a = await cache.get_or_create("scope-a", lambda: build("scope-a"))
    second_b = await cache.get_or_create("scope-b", lambda: build("scope-b"))

    assert (first_a, first_b, second_a, second_b) == (
        "scope-a-1",
        "scope-b-2",
        "scope-a-3",
        "scope-b-2",
    )


def test_repository_concurrent_scope_seed_produces_complete_template_copy(
    repository: TenantProviderRepository,
    provider: OpenAIProvider,
) -> None:
    repository.write_provider(
        "default",
        provider.model_dump(),
        is_builtin=True,
    )
    repository.write_active_model(
        "default",
        ModelSlotConfig(provider_id="openai", model="gpt-5"),
    )
    barrier = threading.Barrier(2)

    def prepare() -> None:
        barrier.wait()
        repository.prepare_scope("tenant-a")

    first = threading.Thread(target=prepare)
    second = threading.Thread(target=prepare)
    first.start()
    second.start()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert repository.read_provider("tenant-a", "openai", is_builtin=True) == (
        provider.model_dump()
    )
    assert repository.read_active_model("tenant-a") == ModelSlotConfig(
        provider_id="openai",
        model="gpt-5",
    )


def test_repository_replaces_provider_json_from_a_same_directory_temp_file(
    repository: TenantProviderRepository,
    provider: OpenAIProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replacements: list[tuple[os.PathLike[str], os.PathLike[str]]] = []
    original_replace = os.replace

    def record_replace(source, destination):  # noqa: ANN001
        replacements.append((source, destination))
        original_replace(source, destination)

    monkeypatch.setattr(os, "replace", record_replace)

    provider_path = repository.write_provider(
        "tenant-a",
        provider.model_dump(),
        is_builtin=True,
    )

    assert len(replacements) == 1
    temporary_source, replacement_destination = replacements[0]
    assert replacement_destination == provider_path
    temporary_path = os.fspath(temporary_source)
    assert os.path.dirname(temporary_path) == os.fspath(provider_path.parent)
    assert not os.path.exists(temporary_path)
    assert (
        json.loads(provider_path.read_text(encoding="utf-8"))
        == provider.model_dump()
    )
