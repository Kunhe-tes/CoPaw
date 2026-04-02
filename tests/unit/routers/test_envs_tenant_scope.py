# -*- coding: utf-8 -*-
"""Tenant env API and storage isolation tests."""
import importlib.util
import os
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

if "google" not in sys.modules:
    google_module = types.ModuleType("google")
    genai_module = types.ModuleType("google.genai")
    errors_module = types.ModuleType("google.genai.errors")
    types_module = types.ModuleType("google.genai.types")

    class _APIError(Exception):
        pass

    class _HttpOptions:
        def __init__(self, *args, **kwargs):
            pass

    class _Dummy:
        def __init__(self, *args, **kwargs):
            pass

    errors_module.APIError = _APIError
    types_module.HttpOptions = _HttpOptions
    types_module.Part = _Dummy
    types_module.Blob = _Dummy
    types_module.GenerateContentConfig = _Dummy
    genai_module.Client = _Dummy
    genai_module.errors = errors_module
    genai_module.types = types_module
    google_module.genai = genai_module

    sys.modules["google"] = google_module
    sys.modules["google.genai"] = genai_module
    sys.modules["google.genai.errors"] = errors_module
    sys.modules["google.genai.types"] = types_module

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from copaw.envs.store import delete_env_var, load_envs, save_envs

_ROUTER_FILE = Path(__file__).parent.parent.parent.parent / "src" / "copaw" / "app" / "routers" / "envs.py"
_PACKAGE_PATH = str(_ROUTER_FILE.parent)
if "copaw.app.routers" not in sys.modules:
    routers_pkg = types.ModuleType("copaw.app.routers")
    routers_pkg.__path__ = [_PACKAGE_PATH]
    sys.modules["copaw.app.routers"] = routers_pkg

_spec = importlib.util.spec_from_file_location(
    "copaw.app.routers.envs",
    _ROUTER_FILE,
)
envs_router = importlib.util.module_from_spec(_spec)
sys.modules["copaw.app.routers.envs"] = envs_router
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(envs_router)
router = envs_router.router


class _TenantStateMiddleware:
    def __init__(self, app, tenant_id: str = "tenant-a"):
        self.app = app
        self.tenant_id = tenant_id

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})
            scope["state"]["tenant_id"] = self.tenant_id
        await self.app(scope, receive, send)


def _build_client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.add_middleware(_TenantStateMiddleware, tenant_id="tenant-a")
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_save_envs_with_custom_path_does_not_mutate_process_env(tmp_path, monkeypatch):
    envs_path = tmp_path / "tenant-a" / ".secret" / "envs.json"
    monkeypatch.delenv("TENANT_ONLY_KEY", raising=False)

    save_envs({"TENANT_ONLY_KEY": "value-a"}, envs_path)

    assert load_envs(envs_path) == {"TENANT_ONLY_KEY": "value-a"}
    assert "TENANT_ONLY_KEY" not in os.environ


def test_delete_env_var_with_custom_path_does_not_remove_process_env(tmp_path, monkeypatch):
    envs_path = tmp_path / "tenant-a" / ".secret" / "envs.json"
    monkeypatch.setenv("TENANT_ONLY_KEY", "runtime")
    save_envs({"TENANT_ONLY_KEY": "tenant"}, envs_path)

    delete_env_var("TENANT_ONLY_KEY", envs_path)

    assert load_envs(envs_path) == {}
    assert os.environ["TENANT_ONLY_KEY"] == "runtime"


def test_tenant_env_api_is_file_scoped_not_process_scoped(tmp_path, monkeypatch):
    monkeypatch.delenv("TENANT_ONLY_KEY", raising=False)

    def fake_tenant_envs_path(request: Request) -> Path:
        return tmp_path / "tenant-a" / ".secret" / "envs.json"

    monkeypatch.setattr(envs_router, "_get_tenant_envs_path", fake_tenant_envs_path)
    client = _build_client(tmp_path)

    response = client.put(
        "/api/envs",
        json={"TENANT_ONLY_KEY": "value-a"},
    )

    assert response.status_code == 200
    assert load_envs(tmp_path / "tenant-a" / ".secret" / "envs.json") == {
        "TENANT_ONLY_KEY": "value-a",
    }
    assert "TENANT_ONLY_KEY" not in os.environ
