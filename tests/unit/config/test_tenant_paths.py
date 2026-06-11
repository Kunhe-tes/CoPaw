# -*- coding: utf-8 -*-
"""Unit tests for tenant path helpers.

Tests tenant-aware path computation and strict failure when
tenant/workspace context is absent.
"""

# pylint: disable=redefined-outer-name
import importlib
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

_ORIGINAL_MODULES = {
    name: sys.modules.get(name)
    for name in [
        "swe.config.config",
        "swe.app.workspace.tenant_init_source_store",
        "swe.app",
        "swe.app.workspace",
    ]
}

config_stub = types.ModuleType("swe.config.config")
config_stub.Config = object
config_stub.HeartbeatConfig = object
config_stub.LastApiConfig = object
config_stub.LastDispatchConfig = object
config_stub.load_agent_config = lambda *args, **kwargs: None
config_stub.save_agent_config = lambda *args, **kwargs: None
sys.modules["swe.config.config"] = config_stub

# Stub tenant_init_source_store module for source_filter tests
tenant_init_source_store_stub = types.ModuleType(
    "swe.app.workspace.tenant_init_source_store",
)


def _get_tenant_init_source_store():
    """Default store getter returns None (database unavailable)."""
    return None


tenant_init_source_store_stub.get_tenant_init_source_store = (
    _get_tenant_init_source_store
)
tenant_init_source_store_stub.TenantInitSourceStore = object
sys.modules["swe.app.workspace.tenant_init_source_store"] = (
    tenant_init_source_store_stub
)

# Stub swe.app namespace and submodules
app_stub = types.ModuleType("swe.app")
app_stub.__path__ = [
    str(Path(__file__).parent.parent.parent.parent / "src" / "swe" / "app"),
]
sys.modules["swe.app"] = app_stub
app_workspace_stub = types.ModuleType("swe.app.workspace")
app_workspace_stub.__path__ = [
    str(
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "swe"
        / "app"
        / "workspace",
    ),
]
sys.modules["swe.app.workspace"] = app_workspace_stub

context_module = importlib.import_module("swe.config.context")
utils_module = importlib.import_module("swe.config.utils")

for _name, _module in _ORIGINAL_MODULES.items():
    if _module is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _module

# 还原真实依赖后重新加载 utils，避免测试桩污染后续测试进程。
utils_module = importlib.reload(utils_module)

TenantContextError = context_module.TenantContextError
encode_scope_id = context_module.encode_scope_id
resolve_storage_tenant_id = context_module.resolve_storage_tenant_id
tenant_context = context_module.tenant_context
get_tenant_working_dir_strict = utils_module.get_tenant_working_dir_strict
get_tenant_config_path_strict = utils_module.get_tenant_config_path_strict
get_tenant_storage_config_path = utils_module.get_tenant_storage_config_path
get_tenant_storage_providers_dir = (
    utils_module.get_tenant_storage_providers_dir
)
get_tenant_storage_working_dir = utils_module.get_tenant_storage_working_dir
list_logical_tenant_ids = utils_module.list_logical_tenant_ids
WORKING_DIR = utils_module.WORKING_DIR


class TestTenantPathHelpers:
    """Tests for tenant-aware path helpers."""

    @pytest.mark.skip(reason="Requires full app dependencies")
    def test_get_tenant_working_dir_with_tenant_id(self):
        """get_tenant_working_dir returns tenant subdirectory."""
        from swe.config.utils import get_tenant_working_dir
        from swe.constant import WORKING_DIR

        path = get_tenant_working_dir("tenant-1")
        assert path == WORKING_DIR / "tenant-1"

    @pytest.mark.skip(reason="Requires full app dependencies")
    def test_get_tenant_working_dir_without_tenant_id(self):
        """get_tenant_working_dir uses context when no tenant_id provided."""
        from swe.config.utils import get_tenant_working_dir
        from swe.constant import WORKING_DIR

        # When no tenant in context, returns global WORKING_DIR
        path = get_tenant_working_dir()
        assert path == WORKING_DIR

    @pytest.mark.skip(reason="Requires full app dependencies")
    def test_get_tenant_config_path(self):
        """get_tenant_config_path returns tenant config.json path."""
        from swe.config.utils import get_tenant_config_path
        from swe.constant import WORKING_DIR

        path = get_tenant_config_path("tenant-1")
        assert path == WORKING_DIR / "tenant-1" / "config.json"

    @pytest.mark.skip(reason="Requires full app dependencies")
    def test_get_tenant_jobs_path(self):
        """get_tenant_jobs_path returns tenant jobs.json path."""
        from swe.config.utils import get_tenant_jobs_path
        from swe.constant import WORKING_DIR, JOBS_FILE

        path = get_tenant_jobs_path("tenant-1")
        assert path == WORKING_DIR / "tenant-1" / JOBS_FILE

    @pytest.mark.skip(reason="Requires full app dependencies")
    def test_get_tenant_chats_path(self):
        """get_tenant_chats_path returns tenant chats.json path."""
        from swe.config.utils import get_tenant_chats_path
        from swe.constant import WORKING_DIR, CHATS_FILE

        path = get_tenant_chats_path("tenant-1")
        assert path == WORKING_DIR / "tenant-1" / CHATS_FILE

    @pytest.mark.skip(reason="Requires full app dependencies")
    def test_get_tenant_memory_dir(self):
        """get_tenant_memory_dir returns tenant memory directory."""
        from swe.config.utils import get_tenant_memory_dir
        from swe.constant import WORKING_DIR

        path = get_tenant_memory_dir("tenant-1")
        assert path == WORKING_DIR / "tenant-1" / "memory"

    @pytest.mark.skip(reason="Requires full app dependencies")
    def test_get_tenant_media_dir(self):
        """get_tenant_media_dir returns tenant media directory."""
        from swe.config.utils import get_tenant_media_dir
        from swe.constant import WORKING_DIR

        path = get_tenant_media_dir("tenant-1")
        assert path == WORKING_DIR / "tenant-1" / "media"

    @pytest.mark.skip(reason="Requires full app dependencies")
    def test_get_tenant_secrets_dir(self):
        """get_tenant_secrets_dir returns tenant secrets directory."""
        from swe.config.utils import get_tenant_secrets_dir
        from swe.constant import WORKING_DIR

        path = get_tenant_secrets_dir("tenant-1")
        assert path == WORKING_DIR / "tenant-1" / ".secret"

    @pytest.mark.skip(reason="Requires full app dependencies")
    def test_get_tenant_heartbeat_path(self):
        """get_tenant_heartbeat_path returns tenant HEARTBEAT.md path."""
        from swe.config.utils import get_tenant_heartbeat_path
        from swe.constant import WORKING_DIR, HEARTBEAT_FILE

        path = get_tenant_heartbeat_path("tenant-1")
        assert path == WORKING_DIR / "tenant-1" / HEARTBEAT_FILE


class TestTenantPathStrictHelpers:
    """Tests for strict tenant path helpers."""

    def test_get_tenant_working_dir_strict_raises_without_tenant_context(self):
        with pytest.raises(TenantContextError):
            get_tenant_working_dir_strict()

    def test_get_tenant_config_path_strict_uses_explicit_tenant(self):
        path = get_tenant_config_path_strict("tenant-a")
        assert path == WORKING_DIR / "tenant-a" / "config.json"

    def test_tenant_sensitive_helper_call_does_not_fallback_to_global_path(
        self,
    ):
        with pytest.raises(TenantContextError):
            get_tenant_working_dir_strict(None)

    def test_explicit_logical_tenant_is_scoped_by_current_source(self):
        """显式逻辑 tenant 也不能绕过当前 source 的 runtime scope。"""
        with tenant_context(tenant_id="tenant-a", source_id="source-a"):
            path = get_tenant_working_dir_strict("tenant-a")

        assert path == WORKING_DIR / encode_scope_id("tenant-a", "source-a")

    def test_scope_like_raw_tenant_uses_current_scope_context(self):
        """形似 scope 的 raw tenant 也必须落到当前 source 对应目录。"""
        tenant_id = "dGVzdA.c291cmNl"
        with tenant_context(tenant_id=tenant_id, source_id="ruice"):
            path = get_tenant_working_dir_strict(tenant_id)

        assert path == WORKING_DIR / encode_scope_id(tenant_id, "ruice")


class TestStorageTenantPathHelpers:
    """Tests for storage-aware tenant path helpers."""

    def test_resolve_storage_tenant_for_default_source_uses_template_dir(
        self,
    ):
        assert resolve_storage_tenant_id("default", "ruice") == "default_ruice"

    def test_storage_working_dir_keeps_template_dir_raw(self):
        path = get_tenant_storage_working_dir("default_ruice")
        assert path == WORKING_DIR / "default_ruice"

    def test_storage_config_path_for_default_source_uses_template_dir(self):
        with tenant_context(tenant_id="default", source_id="ruice"):
            path = get_tenant_storage_config_path("default")

        assert path == WORKING_DIR / "default_ruice" / "config.json"

    def test_storage_providers_dir_for_default_source_uses_template_dir(self):
        with tenant_context(tenant_id="default", source_id="ruice"):
            path = get_tenant_storage_providers_dir("default")

        assert path == utils_module.SECRET_DIR / "default_ruice" / "providers"


class TestLegacyScopeDirectoryLookup:
    """旧 scope 目录即使存在，也不能在路径查询时被自动迁移。"""

    def test_legacy_scope_lookup_keeps_legacy_directory_untouched(
        self,
        monkeypatch,
        tmp_path,
    ):
        canonical_scope_id = encode_scope_id("tenant-a", "source-a")
        legacy_scope_id = f"scope.v1.{canonical_scope_id}"
        legacy_dir = tmp_path / legacy_scope_id
        legacy_dir.mkdir()
        (legacy_dir / "legacy.txt").write_text("legacy", encoding="utf-8")
        monkeypatch.setattr(utils_module, "WORKING_DIR", tmp_path)

        path = get_tenant_working_dir_strict(legacy_scope_id)

        assert path == tmp_path / canonical_scope_id
        assert legacy_dir.exists()
        assert (legacy_dir / "legacy.txt").read_text(encoding="utf-8") == (
            "legacy"
        )

    def test_existing_legacy_directory_is_not_merged_into_canonical(
        self,
        monkeypatch,
        tmp_path,
    ):
        canonical_scope_id = encode_scope_id("tenant-a", "source-a")
        canonical_dir = tmp_path / canonical_scope_id
        legacy_scope_id = f"scope.v1.{canonical_scope_id}"
        legacy_dir = tmp_path / legacy_scope_id
        canonical_dir.mkdir()
        legacy_dir.mkdir()
        (canonical_dir / "canonical.txt").write_text(
            "canonical",
            encoding="utf-8",
        )
        (legacy_dir / "legacy.txt").write_text(
            "legacy",
            encoding="utf-8",
        )
        monkeypatch.setattr(utils_module, "WORKING_DIR", tmp_path)

        path = get_tenant_working_dir_strict(canonical_scope_id)

        assert path == canonical_dir
        assert (path / "canonical.txt").read_text(encoding="utf-8") == (
            "canonical"
        )
        assert legacy_dir.exists()
        assert not (canonical_dir / "legacy.txt").exists()

    @pytest.mark.skip(reason="Requires full app dependencies")
    def test_get_tenant_working_dir_strict_with_tenant_id(self):
        """get_tenant_working_dir_strict works with explicit tenant_id."""
        from swe.config.utils import get_tenant_working_dir_strict
        from swe.constant import WORKING_DIR

        path = get_tenant_working_dir_strict("tenant-1")
        assert path == WORKING_DIR / "tenant-1"

    @pytest.mark.skip(reason="Requires full app dependencies")
    def test_get_tenant_config_path_strict_raises_without_context(self):
        """get_tenant_config_path_strict raises when no tenant context."""
        from swe.config.utils import get_tenant_config_path_strict
        from swe.config.context import TenantContextError

        with pytest.raises(TenantContextError):
            get_tenant_config_path_strict()


class TestLogicalTenantListing:
    """Tests logical tenant ID projection for source-scoped callers."""

    async def test_without_source_id_returns_raw_ids(self, monkeypatch):
        monkeypatch.setattr(
            utils_module,
            "list_all_tenant_ids",
            lambda: ["default", "tenant-a"],
        )

        assert await list_logical_tenant_ids() == ["default", "tenant-a"]

    async def test_source_id_ignores_legacy_default_templates(
        self,
        monkeypatch,
    ):
        monkeypatch.setattr(
            utils_module,
            "list_all_tenant_ids",
            lambda: [
                "default",
                "default_ruice",
                "default_other",
                "tenant-a",
            ],
        )

        assert await list_logical_tenant_ids("ruice") == [
            "default",
            "tenant-a",
        ]

    async def test_source_id_ignores_default_prefixed_templates(
        self,
        monkeypatch,
    ):
        monkeypatch.setattr(
            utils_module,
            "list_all_tenant_ids",
            lambda: [
                "default_ruice",
                "default_sales",
                "tenant-a",
            ],
        )

        assert await list_logical_tenant_ids("ruice") == ["tenant-a"]

    async def test_source_id_projects_scope_directories_back_to_logical_ids(
        self,
        monkeypatch,
    ):
        monkeypatch.setattr(
            utils_module,
            "list_all_tenant_ids",
            lambda: [
                encode_scope_id("default", "ruice"),
                encode_scope_id("tenant-a", "ruice"),
                encode_scope_id("tenant-a", "sales"),
                "tenant-b",
            ],
        )

        assert await list_logical_tenant_ids("ruice") == [
            "default",
            "tenant-a",
            "tenant-b",
        ]

    async def test_source_filter_returns_tenants_from_store(self, monkeypatch):
        """source_filter=True returns tenants from TenantInitSourceStore."""
        fake_store = AsyncMock()
        fake_store.get_by_source.return_value = [
            {"tenant_id": "tenant-a", "source_id": "ruice"},
            {"tenant_id": "tenant-b", "source_id": "ruice"},
        ]

        monkeypatch.setitem(
            sys.modules,
            "swe.app.workspace.tenant_init_source_store",
            tenant_init_source_store_stub,
        )
        monkeypatch.setattr(
            tenant_init_source_store_stub,
            "get_tenant_init_source_store",
            lambda: fake_store,
        )

        result = await list_logical_tenant_ids("ruice", source_filter=True)
        assert result == ["tenant-a", "tenant-b"]
        fake_store.get_by_source.assert_called_once_with("ruice")

    async def test_source_filter_returns_empty_when_store_unavailable(
        self,
        monkeypatch,
    ):
        """source_filter=True returns empty list when store is None."""
        monkeypatch.setitem(
            sys.modules,
            "swe.app.workspace.tenant_init_source_store",
            tenant_init_source_store_stub,
        )
        monkeypatch.setattr(
            tenant_init_source_store_stub,
            "get_tenant_init_source_store",
            lambda: None,
        )

        result = await list_logical_tenant_ids("ruice", source_filter=True)
        assert result == []

    async def test_source_filter_returns_empty_when_source_id_missing(
        self,
    ):
        """source_filter=True returns empty list when source_id is None."""
        result = await list_logical_tenant_ids(None, source_filter=True)
        assert result == []

    async def test_source_filter_false_uses_existing_logic(self, monkeypatch):
        """source_filter=False uses existing file system scan logic."""
        monkeypatch.setattr(
            utils_module,
            "list_all_tenant_ids",
            lambda: ["default", "tenant-a"],
        )

        result = await list_logical_tenant_ids("ruice", source_filter=False)
        assert result == ["default", "tenant-a"]


class TestTenantPathBackwardCompatibility:
    """Tests for backward compatibility with non-tenant code."""

    @pytest.mark.skip(reason="Requires full app dependencies")
    def test_global_helpers_still_work(self):
        """Global path helpers still work for system-level paths."""
        from swe.config.utils import get_config_path, get_jobs_path
        from swe.constant import WORKING_DIR, CONFIG_FILE, JOBS_FILE

        # Global helpers return paths under WORKING_DIR
        assert get_config_path() == WORKING_DIR / CONFIG_FILE
        assert get_jobs_path() == WORKING_DIR / JOBS_FILE
