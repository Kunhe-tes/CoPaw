# -*- coding: utf-8 -*-
"""Source-scoped cutover 运行态缓存清理回归测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from swe.app import _app as app_module
from swe.providers.provider_manager import ProviderManager
from swe.providers import rate_limiter as rate_limiter_module
from swe.tenant_models.manager import TenantModelManager


@pytest.mark.asyncio
async def test_reset_scope_sensitive_runtime_state_clears_stale_caches() -> (
    None
):
    """cutover 前应清空旧的 tenant-only 运行态缓存。"""

    class FakeManager:
        def __init__(self) -> None:
            self.stop_calls = 0

        async def stop_all(self) -> None:
            self.stop_calls += 1

    fake_manager = FakeManager()
    original_runner_manager = app_module.runner._multi_agent_manager
    app_module.runner.set_multi_agent_manager(fake_manager)

    ProviderManager._instances["tenant-a"] = object()
    ProviderManager._instance = object()
    TenantModelManager._cache["tenant-a"] = object()
    rate_limiter_module._limiter_registry["tenant-a"] = object()

    app = SimpleNamespace(
        state=SimpleNamespace(multi_agent_manager=fake_manager),
    )

    try:
        await app_module._reset_scope_sensitive_runtime_state(app)
    finally:
        ProviderManager.reset_instance_cache()
        TenantModelManager.invalidate_cache()
        rate_limiter_module.reset_rate_limiter()
        app_module.runner.set_multi_agent_manager(original_runner_manager)

    assert fake_manager.stop_calls == 1
    assert app.state.multi_agent_manager is None
    assert ProviderManager._instances == {}
    assert ProviderManager._instance is None
    assert TenantModelManager._cache == {}
    assert rate_limiter_module._limiter_registry == {}
    assert app_module.runner._multi_agent_manager is None


@pytest.mark.asyncio
async def test_reset_scope_sensitive_runtime_state_releases_workspace_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cutover 停旧 manager 后不应继续通过诊断回调强引用它。"""

    class FakeManager:
        async def stop_all(self) -> None:
            return None

    class FakeRuntimeDiagnosticManager:
        def __init__(self) -> None:
            self.workspace_metric_callbacks: list[object] = []

        def set_workspace_metrics(self, callback) -> None:
            self.workspace_metric_callbacks.append(callback)

    fake_runtime_diagnostic_manager = FakeRuntimeDiagnosticManager()
    monkeypatch.setattr(
        app_module,
        "runtime_diagnostic_manager",
        fake_runtime_diagnostic_manager,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(multi_agent_manager=FakeManager()),
    )

    await app_module._reset_scope_sensitive_runtime_state(app)

    assert fake_runtime_diagnostic_manager.workspace_metric_callbacks == [
        None,
    ]


@pytest.mark.asyncio
async def test_reset_scope_sensitive_runtime_state_releases_metrics_on_stop_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenManager:
        async def stop_all(self) -> None:
            raise RuntimeError("stop failed")

    class FakeRuntimeDiagnosticManager:
        def __init__(self) -> None:
            self.workspace_metric_callbacks: list[object] = []

        def set_workspace_metrics(self, callback) -> None:
            self.workspace_metric_callbacks.append(callback)

    fake_runtime_diagnostic_manager = FakeRuntimeDiagnosticManager()
    monkeypatch.setattr(
        app_module,
        "runtime_diagnostic_manager",
        fake_runtime_diagnostic_manager,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(multi_agent_manager=BrokenManager()),
    )

    with pytest.raises(RuntimeError, match="stop failed"):
        await app_module._reset_scope_sensitive_runtime_state(app)

    assert fake_runtime_diagnostic_manager.workspace_metric_callbacks == [
        None,
    ]
