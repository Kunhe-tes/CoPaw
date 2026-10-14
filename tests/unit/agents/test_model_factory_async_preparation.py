# -*- coding: utf-8 -*-
"""Request model preparation keeps disk work outside the event loop."""

from __future__ import annotations

import threading
from contextvars import ContextVar
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from swe.agents import model_factory
from swe.providers.models import ModelSlotConfig
from swe.providers.provider import ModelRuntimeConfig
from swe.providers.provider_runtime_cache import ProviderRuntimeCache
from swe.providers.retry_chat_model import RateLimitConfig, RetryConfig


@dataclass
class _Provider:
    id: str
    config: ModelRuntimeConfig
    build: object

    def get_model_config(self, _model):
        return self.config

    def build_generation_kwargs(self, config, **_kwargs):
        return config.generation_kwargs("max_tokens")

    def get_chat_model_instance(self, model, **kwargs):
        return self.build(model, kwargs)


@pytest.fixture
def model_boundary(monkeypatch):
    monkeypatch.setattr(
        model_factory,
        "_create_formatter_instance",
        lambda _: object(),
    )
    monkeypatch.setattr(
        model_factory,
        "_wrap_model_with_tracing",
        lambda _, model, **kwargs: model,
    )
    retry_wrapper = MagicMock(side_effect=lambda model, **kwargs: model)
    monkeypatch.setattr(model_factory, "RetryChatModel", retry_wrapper)
    monkeypatch.setattr(model_factory, "_get_tenant_id", lambda: "tenant-a")
    return retry_wrapper


@pytest.mark.asyncio
async def test_preparation_uses_provider_executor_and_constructs_client_on_loop(
    monkeypatch,
    model_boundary,
):
    main_thread = threading.get_ident()
    marker = ContextVar("request_marker", default=None)
    marker.set("source-a")
    seen = []

    def build(model, kwargs):
        assert threading.get_ident() == main_thread
        seen.append((model, kwargs))
        return object()

    provider = _Provider("openai", ModelRuntimeConfig(temperature=0.2), build)
    slot = ModelSlotConfig(provider_id="openai", model="gpt-5")
    manager = SimpleNamespace(
        get_active_model=lambda: slot,
        get_provider=lambda provider_id: provider,
    )
    retry = RetryConfig(max_retries=4)
    rate = RateLimitConfig(max_qpm=17)

    def read_configs(agent_id, tenant_id):
        assert threading.get_ident() != main_thread
        assert marker.get() == "source-a"
        assert (agent_id, tenant_id) == ("agent-a", "tenant-a")
        return retry, rate

    monkeypatch.setattr(
        model_factory,
        "_get_model_runtime_configs",
        read_configs,
    )
    storage = MagicMock(
        side_effect=AssertionError("storage lock on model construction"),
    )
    monkeypatch.setattr(
        model_factory.ProviderManager,
        "ensure_tenant_provider_storage",
        storage,
    )
    cache = ProviderRuntimeCache()
    monkeypatch.setattr(model_factory.ProviderManager, "_runtime_cache", cache)
    try:
        prepared = await model_factory.prepare_model_config_async(
            agent_id="agent-a",
            manager=manager,
        )
        provider.config = ModelRuntimeConfig(temperature=0.9)
        slot.model = "changed-model"
        monkeypatch.setattr(
            model_factory,
            "_get_model_runtime_configs",
            lambda *_: pytest.fail("configuration reread on loop"),
        )
        model_factory.create_model_and_formatter(
            prepared_model_config=prepared,
        )
    finally:
        cache.init_executor.shutdown(wait=True)

    storage.assert_not_called()
    assert seen == [("gpt-5", {"generation_kwargs": {"temperature": 0.2}})]
    assert model_boundary.call_args.kwargs["retry_config"] == retry
    assert model_boundary.call_args.kwargs["rate_limit_config"] == rate
    assert model_boundary.call_args.kwargs["tenant_id"] == "tenant-a"
    assert model_boundary.call_args.kwargs["agent_id"] == "agent-a"


@pytest.mark.asyncio
async def test_prepared_private_model_retains_frozen_fallback(
    monkeypatch,
    model_boundary,
):
    builds = []

    def unavailable(_model, _kwargs):
        raise ValueError("selected unavailable")

    def build(model, kwargs):
        builds.append((model, kwargs))
        return object()

    selected = _Provider("selected", ModelRuntimeConfig(), unavailable)
    fallback = _Provider("parent", ModelRuntimeConfig(temperature=0.3), build)
    monkeypatch.setattr(
        model_factory,
        "_get_model_runtime_configs",
        lambda *_: (None, None),
    )
    cache = ProviderRuntimeCache()
    monkeypatch.setattr(model_factory.ProviderManager, "_runtime_cache", cache)
    manager_lookup = MagicMock(
        side_effect=AssertionError("private provider consulted manager"),
    )
    monkeypatch.setattr(
        model_factory.ProviderManager,
        "get_or_create_instance",
        manager_lookup,
    )
    try:
        prepared = await model_factory.prepare_model_config_async(
            agent_id="agent-a",
            model_slot_override=ModelSlotConfig(
                provider_id="selected",
                model="selected-model",
            ),
            model_provider_override=selected,
            fallback_model_slot=ModelSlotConfig(
                provider_id="parent",
                model="parent-model",
            ),
            fallback_model_provider=fallback,
        )
        fallback.config = ModelRuntimeConfig(temperature=0.9)
        resolved = {}
        model_factory.create_model_and_formatter(
            prepared_model_config=prepared,
            resolved_model_info=resolved,
        )
    finally:
        cache.init_executor.shutdown(wait=True)

    manager_lookup.assert_not_called()
    assert builds == [
        ("parent-model", {"generation_kwargs": {"temperature": 0.3}}),
    ]
    assert resolved == {"provider_id": "parent", "model": "parent-model"}


@pytest.mark.asyncio
async def test_preparation_preserves_source_rate_override_and_scoped_model(
    monkeypatch,
    model_boundary,
):
    from swe.app.crons.model_slot_context import bind_model_slot_override
    from swe.app.source_system_config.models import (
        EffectiveSourceSystemConfig,
        SourceSystemConfig,
    )
    from swe.app.source_system_config.runtime import bind_source_system_config

    builds = []
    provider = _Provider(
        "cron-provider",
        ModelRuntimeConfig(),
        lambda model, _: builds.append(model) or object(),
    )
    manager = SimpleNamespace(
        get_active_model=lambda: pytest.fail("cron override lost"),
        get_provider=lambda provider_id: (
            provider if provider_id == "cron-provider" else None
        ),
    )
    config = SimpleNamespace(
        running=SimpleNamespace(
            llm_retry_enabled=True,
            llm_max_retries=6,
            llm_backoff_base=1.0,
            llm_backoff_cap=20.0,
            llm_max_concurrent=7,
            llm_max_qpm=80,
            llm_rate_limit_pause=4.0,
            llm_rate_limit_jitter=0.5,
            llm_acquire_timeout=30.0,
        ),
    )
    reads = []

    def load_agent_config(agent_id, **kwargs):
        reads.append((agent_id, kwargs, threading.get_ident()))
        return config

    monkeypatch.setattr(
        "swe.config.config.load_agent_config",
        load_agent_config,
    )
    cache = ProviderRuntimeCache()
    monkeypatch.setattr(model_factory.ProviderManager, "_runtime_cache", cache)
    source = EffectiveSourceSystemConfig(
        source_id="portal",
        config=SourceSystemConfig.model_validate({}),
        raw_config=SourceSystemConfig.model_validate(
            {"llm_rate_limiter": {"llm_max_qpm": 12}},
        ),
        version=3,
    )
    try:
        with (
            bind_source_system_config(source),
            bind_model_slot_override(
                ModelSlotConfig(
                    provider_id="cron-provider",
                    model="cron-model",
                ),
            ),
        ):
            prepared = await model_factory.prepare_model_config_async(
                agent_id="agent-a",
                manager=manager,
            )
        model_factory.create_model_and_formatter(
            prepared_model_config=prepared,
        )
    finally:
        cache.init_executor.shutdown(wait=True)

    assert builds == ["cron-model"]
    assert len(reads) == 1
    assert reads[0][:2] == ("agent-a", {"tenant_id": "tenant-a"})
    assert reads[0][2] != threading.get_ident()
    assert model_boundary.call_args.kwargs["retry_config"].max_retries == 6
    assert model_boundary.call_args.kwargs["rate_limit_config"].max_qpm == 12


@pytest.mark.asyncio
async def test_query_runtime_prepares_model_before_agent_construction(
    monkeypatch,
):
    from unittest.mock import AsyncMock
    from swe.app.runner import query_runtime

    events = []
    snapshot = object()
    manager = SimpleNamespace(refresh_if_due=AsyncMock())
    inputs = SimpleNamespace(agent_config=SimpleNamespace(id="agent-a"))

    async def prepare(**kwargs):
        assert kwargs == {
            "agent_id": "agent-a",
            "tenant_id": "tenant-a",
            "manager": manager,
        }
        events.append("prepare")
        return snapshot

    async def finalize(**kwargs):
        assert kwargs["inputs"].prepared_model_config is snapshot
        events.append("construct")
        return object()

    monkeypatch.setattr(
        query_runtime.ProviderManager,
        "get_or_create_instance",
        AsyncMock(return_value=manager),
    )
    monkeypatch.setattr(
        model_factory,
        "prepare_model_config_async",
        prepare,
        raising=False,
    )
    owner = SimpleNamespace(
        tenant_id="tenant-a",
        _build_query_runtime_inputs=AsyncMock(return_value=inputs),
        _start_query_runtime_resources=AsyncMock(
            return_value=(object(), None),
        ),
        _finalize_query_runtime=finalize,
        _cleanup_query_runtime_mcp_clients=AsyncMock(),
    )
    await query_runtime.prepare_query_runtime(
        owner,
        request=object(),
        msgs=[],
        query=None,
        preflight=object(),
    )
    assert events == ["prepare", "construct"]


@pytest.mark.asyncio
async def test_standalone_preparation_initializes_scope_and_preserves_context(
    monkeypatch,
):
    from unittest.mock import AsyncMock
    from swe.config.context import (
        tenant_context,
        get_current_effective_tenant_id,
    )

    threads = []
    provider = _Provider("openai", ModelRuntimeConfig(), lambda *_: object())
    manager = SimpleNamespace(
        refresh_if_due=AsyncMock(),
        get_active_model=lambda: ModelSlotConfig(
            provider_id="openai",
            model="gpt-5",
        ),
        get_provider=lambda _: provider,
    )
    lookup = AsyncMock(return_value=manager)
    monkeypatch.setattr(
        model_factory.ProviderManager,
        "get_or_create_instance",
        lookup,
    )

    def read_configs(agent_id, tenant_id):
        assert agent_id == "agent-a"
        assert tenant_id == get_current_effective_tenant_id()
        threads.append(threading.get_ident())
        return None, None

    monkeypatch.setattr(
        model_factory,
        "_get_model_runtime_configs",
        read_configs,
    )
    cache = ProviderRuntimeCache()
    monkeypatch.setattr(model_factory.ProviderManager, "_runtime_cache", cache)
    try:
        with tenant_context(tenant_id="default", source_id="portal"):
            expected_scope = get_current_effective_tenant_id()
            prepared = await model_factory.prepare_model_config_async(
                agent_id="agent-a",
                tenant_id="default",
            )
    finally:
        cache.init_executor.shutdown(wait=True)

    lookup.assert_awaited_once_with("default")
    manager.refresh_if_due.assert_awaited_once()
    assert prepared.tenant_id == expected_scope
    assert threads and threads[0] != threading.get_ident()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "slot,expected_error",
    [
        (None, "No tenant model configuration found."),
        (
            ModelSlotConfig(provider_id="", model=""),
            "No tenant model configuration found.",
        ),
        (
            ModelSlotConfig(provider_id="missing", model="gpt-5"),
            "Provider 'missing' not found.",
        ),
    ],
)
async def test_preparation_preserves_missing_model_errors(
    monkeypatch,
    slot,
    expected_error,
):
    manager = SimpleNamespace(
        get_active_model=lambda: slot,
        get_provider=lambda _: None,
    )
    cache = ProviderRuntimeCache()
    monkeypatch.setattr(model_factory.ProviderManager, "_runtime_cache", cache)
    try:
        with pytest.raises(ValueError, match=expected_error):
            await model_factory.prepare_model_config_async(
                agent_id="agent-a",
                manager=manager,
            )
    finally:
        cache.init_executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_cancelled_preparation_consumes_late_worker_failure(monkeypatch):
    import asyncio
    import gc

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    errors = []
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: errors.append(context))

    def get_active_model():
        started.set()
        try:
            assert release.wait(timeout=5)
            raise ValueError("provider read failed after cancellation")
        finally:
            finished.set()

    manager = SimpleNamespace(get_active_model=get_active_model)
    cache = ProviderRuntimeCache()
    monkeypatch.setattr(model_factory.ProviderManager, "_runtime_cache", cache)
    try:
        task = asyncio.create_task(
            model_factory.prepare_model_config_async(manager=manager),
        )
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        assert await asyncio.to_thread(finished.wait, 5)
        await asyncio.sleep(0)
        del task
        gc.collect()
        await asyncio.sleep(0)
        assert errors == []
    finally:
        release.set()
        cache.init_executor.shutdown(wait=True)
        loop.set_exception_handler(previous_handler)
