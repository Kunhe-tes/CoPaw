# -*- coding: utf-8 -*-
"""Config router source-scope distribution tests."""

import asyncio
import sys
from types import SimpleNamespace
from pathlib import Path

from swe.app.routers import config as config_router
from swe.config.context import encode_scope_id


def test_prepare_target_tenant_uses_runtime_scope_for_target_tenant(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """通道配置分发目标目录必须按目标 tenant 的 runtime scope 解析。"""
    observed: dict[str, object] = {}
    scope_id = encode_scope_id("tenant-b", "ruice")

    def fake_get_tenant_working_dir_strict(
        tenant_id: str | None = None,
    ) -> Path:
        observed["working_dir_tenant_id"] = tenant_id
        return tmp_path / str(tenant_id)

    class FakeInitializer:
        def __init__(
            self,
            base_working_dir: Path,
            tenant_id: str,
            source_id: str | None = None,
        ) -> None:
            observed["initializer_base_working_dir"] = base_working_dir
            observed["initializer_tenant_id"] = tenant_id
            observed["initializer_source_id"] = source_id
            self.effective_tenant_id = scope_id

        def has_seeded_bootstrap(self) -> bool:
            return True

        def ensure_seeded_bootstrap(self) -> dict[str, object]:
            raise AssertionError("should not bootstrap an existing tenant")

    monkeypatch.setattr(
        "swe.config.utils.get_tenant_storage_working_dir",
        fake_get_tenant_working_dir_strict,
    )
    monkeypatch.setitem(
        sys.modules,
        "swe.app.workspace.tenant_initializer",
        SimpleNamespace(TenantInitializer=FakeInitializer),
    )

    request = SimpleNamespace(
        state=SimpleNamespace(
            tenant_id="tenant-a",
            source_id="ruice",
        ),
    )

    resolved = asyncio.run(
        config_router._prepare_target_tenant(request, "tenant-b"),
    )

    assert observed["working_dir_tenant_id"] == scope_id
    assert observed["initializer_base_working_dir"] == tmp_path
    assert observed["initializer_tenant_id"] == "tenant-b"
    assert observed["initializer_source_id"] == "ruice"
    assert resolved == ("tenant-b", scope_id, True)


def test_prepare_target_tenant_maps_default_to_template_dir(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """source-scoped default 分发必须落到 default_{source} 模板目录。"""
    observed: dict[str, object] = {}

    def fake_get_tenant_working_dir_strict(
        tenant_id: str | None = None,
    ) -> Path:
        observed["working_dir_tenant_id"] = tenant_id
        return tmp_path / str(tenant_id)

    class FakeInitializer:
        def __init__(
            self,
            base_working_dir: Path,
            tenant_id: str,
            source_id: str | None = None,
        ) -> None:
            observed["initializer_base_working_dir"] = base_working_dir
            observed["initializer_tenant_id"] = tenant_id
            observed["initializer_source_id"] = source_id
            self.effective_tenant_id = "default_ruice"

        def has_seeded_bootstrap(self) -> bool:
            return True

        def ensure_seeded_bootstrap(self) -> dict[str, object]:
            raise AssertionError("should not bootstrap an existing tenant")

    monkeypatch.setattr(
        "swe.config.utils.get_tenant_storage_working_dir",
        fake_get_tenant_working_dir_strict,
    )
    monkeypatch.setitem(
        sys.modules,
        "swe.app.workspace.tenant_initializer",
        SimpleNamespace(TenantInitializer=FakeInitializer),
    )

    request = SimpleNamespace(
        state=SimpleNamespace(
            tenant_id="tenant-a",
            source_id="ruice",
        ),
    )

    resolved = asyncio.run(
        config_router._prepare_target_tenant(request, "default"),
    )

    assert observed["working_dir_tenant_id"] == "default_ruice"
    assert observed["initializer_base_working_dir"] == tmp_path
    assert observed["initializer_tenant_id"] == "default"
    assert observed["initializer_source_id"] == "ruice"
    assert resolved == ("default", "default_ruice", True)
