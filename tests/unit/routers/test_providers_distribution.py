# -*- coding: utf-8 -*-
"""Providers distribution router tests."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from swe.app.routers import providers as providers_router


def _request(
    tenant_id: str = "tenant-source",
    source_id: str | None = None,
    scope_id: str | None = None,
    headers: dict[str, str] | None = None,
    app: Any | None = None,
) -> SimpleNamespace:
    request = SimpleNamespace(
        headers=headers or {},
        state=SimpleNamespace(
            tenant_id=tenant_id,
            source_id=source_id,
            scope_id=scope_id,
        ),
    )
    if app is not None:
        request.app = app
    return request


class FakeAsyncTaskDb:
    """提供异步任务写入器所需的数据库连接状态。"""

    is_connected = True


class DisconnectedAsyncTaskDb(FakeAsyncTaskDb):
    """模拟连接状态标记为断开但仍可执行写入的任务库。"""

    is_connected = False


def _setup_source_providers(
    secret_dir: Path,
    tenant_id: str,
) -> Path:
    """Create a source providers directory with sample content."""
    providers_dir = secret_dir / tenant_id / "providers"
    providers_dir.mkdir(parents=True, exist_ok=True)

    # Create builtin directory with a sample provider
    builtin_dir = providers_dir / "builtin"
    builtin_dir.mkdir(exist_ok=True)
    builtin_provider = builtin_dir / "openai.json"
    builtin_provider.write_text(
        '{"id": "openai", "name": "OpenAI", "api_key": "sk-test", "base_url": "https://api.openai.com/v1", "models": [{"id": "gpt-4", "name": "GPT-4"}], "extra_models": [], "chat_model": "OpenAIChatModel"}',
        encoding="utf-8",
    )

    # Create custom directory with a sample custom provider
    custom_dir = providers_dir / "custom"
    custom_dir.mkdir(exist_ok=True)
    custom_provider = custom_dir / "custom-llm.json"
    custom_provider.write_text(
        '{"id": "custom-llm", "name": "Custom LLM", "api_key": "custom-key", "base_url": "https://custom.example/v1", "models": [{"id": "custom-model", "name": "Custom Model"}], "extra_models": [], "chat_model": "OpenAIChatModel", "is_custom": true}',
        encoding="utf-8",
    )

    # Create active_model.json
    active_model_file = providers_dir / "active_model.json"
    active_model_file.write_text(
        '{"provider_id": "openai", "model": "gpt-4"}',
        encoding="utf-8",
    )

    return providers_dir


def test_distribute_providers_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test successful distribution to a single tenant."""
    secret_dir = tmp_path / "secret"
    _setup_source_providers(secret_dir, "tenant-source")

    monkeypatch.setattr(providers_router, "SECRET_DIR", secret_dir)
    monkeypatch.setattr(
        providers_router,
        "get_tenant_working_dir_strict",
        lambda tenant_id: tmp_path / str(tenant_id),
    )

    class FakeInitializer:
        def __init__(
            self,
            _base_working_dir: Path,
            tenant_id: str,
            source_id: str | None = None,
        ):
            self.tenant_id = tenant_id
            self.effective_tenant_id = (
                providers_router.resolve_runtime_tenant_id(
                    tenant_id,
                    source_id,
                )
                or tenant_id
            )

        def has_seeded_bootstrap(self) -> bool:
            return True

        def ensure_seeded_bootstrap(self) -> dict[str, Any]:
            return {"minimal": True}

    monkeypatch.setattr(providers_router, "TenantInitializer", FakeInitializer)

    result = asyncio.run(
        providers_router.distribute_providers(
            _request(),
            providers_router.ProvidersDistributionRequest(
                target_tenant_ids=["tenant-target"],
                overwrite=True,
            ),
        ),
    )

    assert result.source_tenant_id == "tenant-source"
    assert len(result.results) == 1
    assert result.results[0].tenant_id == "tenant-target"


def test_distribute_providers_requires_async_task_db(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """供应商分发必须提交异步任务，缺少任务库时返回明确错误。"""
    secret_dir = tmp_path / "secret"
    _setup_source_providers(secret_dir, "tenant-source")

    monkeypatch.setattr(providers_router, "SECRET_DIR", secret_dir)
    app = SimpleNamespace(state=SimpleNamespace())

    with pytest.raises(providers_router.HTTPException) as exc_info:
        asyncio.run(
            providers_router.distribute_providers(
                _request(app=app),
                providers_router.ProvidersDistributionRequest(
                    target_tenant_ids=["tenant-target"],
                    overwrite=True,
                ),
            ),
        )

    assert exc_info.value.status_code == 503
    assert (
        exc_info.value.detail
        == "Async task database connection is not available"
    )


def test_distribute_providers_uses_request_scope_for_source_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Source-scoped 请求必须从 runtime scope 目录读取源 providers。"""
    secret_dir = tmp_path / "secret"
    scope_id = "scope.v1.dGVuYW50LXNvdXJjZQ.cnVpY2U"
    canonical_scope_id = "dGVuYW50LXNvdXJjZQ.cnVpY2U"
    _setup_source_providers(secret_dir, canonical_scope_id)
    observed: dict[str, str | None] = {}

    monkeypatch.setattr(providers_router, "SECRET_DIR", secret_dir)

    def fake_get_tenant_working_dir_strict(tenant_id: str | None) -> Path:
        observed["tenant_id"] = tenant_id
        return tmp_path / str(tenant_id)

    monkeypatch.setattr(
        providers_router,
        "get_tenant_working_dir_strict",
        fake_get_tenant_working_dir_strict,
    )

    class FakeInitializer:
        def __init__(
            self,
            _base_working_dir: Path,
            tenant_id: str,
            source_id: str | None = None,
        ):
            self.tenant_id = tenant_id
            self.effective_tenant_id = (
                providers_router.resolve_runtime_tenant_id(
                    tenant_id,
                    source_id,
                )
                or tenant_id
            )

        def has_seeded_bootstrap(self) -> bool:
            return True

        def ensure_seeded_bootstrap(self) -> dict[str, Any]:
            return {"minimal": True}

    monkeypatch.setattr(providers_router, "TenantInitializer", FakeInitializer)

    result = asyncio.run(
        providers_router.distribute_providers(
            _request(
                tenant_id="tenant-source",
                source_id="ruice",
                scope_id=scope_id,
            ),
            providers_router.ProvidersDistributionRequest(
                target_tenant_ids=["tenant-target"],
                overwrite=True,
            ),
        ),
    )

    assert observed["tenant_id"] == canonical_scope_id
    assert result.source_tenant_id == canonical_scope_id
    assert result.results[0].success is True
    assert (
        secret_dir
        / providers_router.resolve_runtime_tenant_id("tenant-target", "ruice")
        / "providers"
    ).exists()


def test_distribute_providers_multiple_tenants(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test successful distribution to multiple tenants."""
    secret_dir = tmp_path / "secret"
    _setup_source_providers(secret_dir, "tenant-source")

    monkeypatch.setattr(providers_router, "SECRET_DIR", secret_dir)
    monkeypatch.setattr(
        providers_router,
        "get_tenant_working_dir_strict",
        lambda tenant_id: tmp_path / str(tenant_id),
    )

    class FakeInitializer:
        def __init__(
            self,
            _base_working_dir: Path,
            tenant_id: str,
            source_id: str | None = None,
        ):
            self.tenant_id = tenant_id
            self.effective_tenant_id = (
                providers_router.resolve_runtime_tenant_id(
                    tenant_id,
                    source_id,
                )
                or tenant_id
            )

        def has_seeded_bootstrap(self) -> bool:
            return True

        def ensure_seeded_bootstrap(self) -> dict[str, Any]:
            return {"minimal": True}

    monkeypatch.setattr(providers_router, "TenantInitializer", FakeInitializer)

    result = asyncio.run(
        providers_router.distribute_providers(
            _request(),
            providers_router.ProvidersDistributionRequest(
                target_tenant_ids=["tenant-a", "tenant-b"],
                overwrite=True,
            ),
        ),
    )

    assert len(result.results) == 2
    assert all(r.success for r in result.results)
    assert [r.tenant_id for r in result.results] == ["tenant-a", "tenant-b"]


def test_distribute_providers_overwrite_required(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test that overwrite=False returns 400 error."""
    secret_dir = tmp_path / "secret"
    _setup_source_providers(secret_dir, "tenant-source")

    monkeypatch.setattr(providers_router, "SECRET_DIR", secret_dir)
    monkeypatch.setattr(
        providers_router,
        "get_tenant_working_dir_strict",
        lambda tenant_id: tmp_path / str(tenant_id),
    )

    with pytest.raises(providers_router.HTTPException) as exc_info:
        asyncio.run(
            providers_router.distribute_providers(
                _request(),
                providers_router.ProvidersDistributionRequest(
                    target_tenant_ids=["tenant-target"],
                    overwrite=False,
                ),
            ),
        )

    assert exc_info.value.status_code == 400
    assert "overwrite=true" in str(exc_info.value.detail)


def test_distribute_providers_empty_tenants(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test that empty target_tenant_ids returns 400 error."""
    secret_dir = tmp_path / "secret"
    _setup_source_providers(secret_dir, "tenant-source")

    monkeypatch.setattr(providers_router, "SECRET_DIR", secret_dir)
    monkeypatch.setattr(
        providers_router,
        "get_tenant_working_dir_strict",
        lambda tenant_id: tmp_path / str(tenant_id),
    )

    with pytest.raises(providers_router.HTTPException) as exc_info:
        asyncio.run(
            providers_router.distribute_providers(
                _request(),
                providers_router.ProvidersDistributionRequest(
                    target_tenant_ids=[],
                    overwrite=True,
                ),
            ),
        )

    assert exc_info.value.status_code == 400
    assert "No target tenant IDs" in str(exc_info.value.detail)


def test_distribute_providers_source_not_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test that missing source providers directory returns 400 error."""
    secret_dir = tmp_path / "secret"
    # Do NOT create source providers directory

    monkeypatch.setattr(providers_router, "SECRET_DIR", secret_dir)
    monkeypatch.setattr(
        providers_router,
        "get_tenant_working_dir_strict",
        lambda tenant_id: tmp_path / str(tenant_id),
    )

    with pytest.raises(providers_router.HTTPException) as exc_info:
        asyncio.run(
            providers_router.distribute_providers(
                _request(),
                providers_router.ProvidersDistributionRequest(
                    target_tenant_ids=["tenant-target"],
                    overwrite=True,
                ),
            ),
        )

    assert exc_info.value.status_code == 400
    assert "Source providers directory not found" in str(exc_info.value.detail)


def test_distribute_providers_partial_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test that partial failure doesn't affect other tenants."""
    secret_dir = tmp_path / "secret"
    _setup_source_providers(secret_dir, "tenant-source")

    monkeypatch.setattr(providers_router, "SECRET_DIR", secret_dir)
    monkeypatch.setattr(
        providers_router,
        "get_tenant_working_dir_strict",
        lambda tenant_id: tmp_path / str(tenant_id),
    )

    call_count = 0

    def mock_distribute(
        *,
        source_providers_dir: Path,
        target_tenant_id: str,
        source_working_dir: Path,
        source_id: str | None,
    ) -> providers_router.ProvidersDistributionTenantResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call (tenant-a) succeeds
            return providers_router.ProvidersDistributionTenantResult(
                tenant_id=target_tenant_id,
                success=True,
                bootstrapped=False,
            )
        # Second call (tenant-b) fails
        return providers_router.ProvidersDistributionTenantResult(
            tenant_id=target_tenant_id,
            success=False,
            error="Simulated failure",
        )

    monkeypatch.setattr(
        providers_router,
        "_distribute_providers_to_tenant",
        mock_distribute,
    )

    result = asyncio.run(
        providers_router.distribute_providers(
            _request(),
            providers_router.ProvidersDistributionRequest(
                target_tenant_ids=["tenant-a", "tenant-b"],
                overwrite=True,
            ),
        ),
    )

    assert len(result.results) == 2
    assert result.results[0].success is True
    assert result.results[1].success is False
    assert "Simulated failure" in str(result.results[1].error)


def test_distribute_providers_bootstraps_tenant(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test that unbootstrapped tenant gets initialized."""
    secret_dir = tmp_path / "secret"
    _setup_source_providers(secret_dir, "tenant-source")

    monkeypatch.setattr(providers_router, "SECRET_DIR", secret_dir)
    monkeypatch.setattr(
        providers_router,
        "get_tenant_working_dir_strict",
        lambda tenant_id: tmp_path / str(tenant_id),
    )

    bootstrap_calls: list[str] = []

    class FakeInitializer:
        def __init__(
            self,
            _base_working_dir: Path,
            tenant_id: str,
            source_id: str | None = None,
        ):
            self.tenant_id = tenant_id
            self.effective_tenant_id = (
                providers_router.resolve_runtime_tenant_id(
                    tenant_id,
                    source_id,
                )
                or tenant_id
            )

        def has_seeded_bootstrap(self) -> bool:
            return False

        def ensure_seeded_bootstrap(self) -> dict[str, Any]:
            bootstrap_calls.append(self.tenant_id)
            return {"minimal": True}

    monkeypatch.setattr(providers_router, "TenantInitializer", FakeInitializer)

    result = asyncio.run(
        providers_router.distribute_providers(
            _request(),
            providers_router.ProvidersDistributionRequest(
                target_tenant_ids=["tenant-new"],
                overwrite=True,
            ),
        ),
    )

    assert bootstrap_calls == ["tenant-new"]
    assert result.results[0].bootstrapped is True


def test_distribute_providers_returns_async_task_submission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """提交 providers 分发后应返回受理中的任务信息。"""
    secret_dir = tmp_path / "secret"
    _setup_source_providers(secret_dir, "tenant-source")
    submitted: dict[str, Any] = {}
    task_ids: list[str] = []

    monkeypatch.setattr(providers_router, "SECRET_DIR", secret_dir)
    monkeypatch.setattr(
        providers_router,
        "get_tenant_working_dir_strict",
        lambda tenant_id: tmp_path / str(tenant_id),
    )

    class FakeStore:
        def __init__(self, db) -> None:  # noqa: ANN001
            submitted["db"] = db

        async def start_task(self, **kwargs) -> None:  # noqa: ANN003
            submitted["start_task"] = kwargs

    async def fake_task_runner(*args, **kwargs):  # noqa: ANN001, ANN003
        submitted["runner"] = (args, kwargs)

    def fake_create_task(coro):  # noqa: ANN001
        task_ids.append("scheduled")
        submitted["coroutine"] = coro
        coro.close()
        return object()

    monkeypatch.setattr(
        providers_router,
        "AsyncTaskStore",
        FakeStore,
        raising=False,
    )
    monkeypatch.setattr(
        providers_router.asyncio,
        "create_task",
        fake_create_task,
    )
    monkeypatch.setattr(
        providers_router,
        "_run_providers_distribution_task",
        fake_task_runner,
        raising=False,
    )

    result = asyncio.run(
        providers_router.distribute_providers(
            _request(
                headers={
                    "X-User-Id": "operator-1",
                    "X-User-Name": "%E5%BC%A0%E4%B8%89",
                },
                app=SimpleNamespace(
                    state=SimpleNamespace(
                        db_connection=DisconnectedAsyncTaskDb(),
                    ),
                ),
            ),
            providers_router.ProvidersDistributionRequest(
                target_tenant_ids=["tenant-a"],
                overwrite=True,
            ),
        ),
    )

    assert result.status == "queued"
    assert result.reused is False
    assert result.task_id
    assert task_ids == ["scheduled"]
    assert isinstance(submitted["db"], DisconnectedAsyncTaskDb)
    assert (
        submitted["start_task"]["task_type"] == "provider.providers.distribute"
    )
    assert (
        submitted["start_task"]["summary"]
        == "分发供应商配置「openai, custom-llm」，目标 1 个用户"
    )
    assert submitted["start_task"]["actor_user_id"] == "operator-1"
    assert submitted["start_task"]["actor_user_name"] == "张三"
