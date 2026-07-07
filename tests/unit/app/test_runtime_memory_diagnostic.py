# -*- coding: utf-8 -*-
"""Tests for on-demand runtime memory diagnostics."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from swe.app.auth import AuthMiddleware
from swe.app.middleware.tenant_identity import TenantIdentityMiddleware
from swe.app.middleware.tenant_workspace import TenantWorkspaceMiddleware
from swe.app import runtime_diagnostic
from swe.app.routers.runtime import router
from swe.app.runtime_diagnostic import RuntimeDiagnosticManager


class _Process:
    def memory_info(self):
        return SimpleNamespace(rss=123, vms=456)

    def num_threads(self) -> int:
        return 7

    def num_fds(self) -> int:
        return 8

    def create_time(self) -> float:
        return 90.0

    def cpu_percent(self) -> float:
        return 0.0


def _manager(**overrides) -> RuntimeDiagnosticManager:
    options = {
        "hostname": "pod-a",
        "wall_time": lambda: 100.0,
        "process": _Process(),
        "disk_usage": lambda _path: SimpleNamespace(
            total=0,
            used=0,
            free=0,
            percent=0.0,
        ),
        "pod_open_fd_count": lambda: 0,
        "pod_disk_io_bytes": lambda: (0, 0),
        "thread_limiter": lambda: SimpleNamespace(
            total_tokens=1,
            borrowed_tokens=0,
        ),
    }
    options.update(overrides)
    return RuntimeDiagnosticManager(**options)


def test_collect_memory_diagnostic_uses_objgraph_and_pympler(
    monkeypatch,
) -> None:
    objgraph = SimpleNamespace(
        typestats=lambda: {
            "dict": 2,
            "list": 5,
            "Workspace": 3,
        },
    )
    muppy = SimpleNamespace(get_objects=lambda: [object(), object(), object()])
    summary = SimpleNamespace(
        summarize=lambda _objects: [
            ("dict", 2, 300),
            ("list", 5, 700),
            ("Workspace", 3, 500),
        ],
    )

    def fake_import(module_name: str):
        modules = {
            "objgraph": objgraph,
            "pympler.muppy": muppy,
            "pympler.summary": summary,
        }
        return modules[module_name]

    monkeypatch.setattr(runtime_diagnostic, "import_module", fake_import)
    monkeypatch.setattr(runtime_diagnostic.gc, "collect", lambda: 4)
    monkeypatch.setattr(runtime_diagnostic.gc, "get_objects", lambda: [1, 2])

    payload = _manager().collect_memory_diagnostic(limit=2)

    assert payload["schema"] == "runtime_diagnostic.v1"
    assert payload["event_type"] == "memory_diagnostic"
    assert payload["hostname"] == "pod-a"
    assert payload["process_rss_bytes"] == 123
    assert payload["process_vms_bytes"] == 456
    assert payload["gc_collected"] == 4
    assert payload["gc_object_count"] == 2
    assert payload["objgraph_available"] is True
    assert payload["objgraph_type_count"] == 3
    assert payload["top_object_types"] == [
        {"type": "list", "count": 5},
        {"type": "Workspace", "count": 3},
    ]
    assert payload["pympler_available"] is True
    assert payload["pympler_object_count"] == 3
    assert payload["top_memory_types"] == [
        {"type": "list", "count": 5, "size_bytes": 700},
        {"type": "Workspace", "count": 3, "size_bytes": 500},
    ]
    assert payload["errors"] == []


def test_collect_memory_diagnostic_reports_missing_optional_collectors(
    monkeypatch,
) -> None:
    def missing_import(module_name: str):
        raise ModuleNotFoundError(module_name)

    monkeypatch.setattr(runtime_diagnostic, "import_module", missing_import)
    monkeypatch.setattr(runtime_diagnostic.gc, "collect", lambda: 0)
    monkeypatch.setattr(runtime_diagnostic.gc, "get_objects", lambda: [])

    payload = _manager().collect_memory_diagnostic(limit=20)

    assert payload["objgraph_available"] is False
    assert payload["top_object_types"] == []
    assert payload["pympler_available"] is False
    assert payload["top_memory_types"] == []
    assert payload["errors"] == [
        {"collector": "objgraph", "message": "objgraph"},
        {"collector": "pympler.muppy", "message": "pympler.muppy"},
        {"collector": "pympler.summary", "message": "pympler.summary"},
    ]


def test_memory_diagnostic_route_calls_runtime_manager() -> None:
    class FakeManager(RuntimeDiagnosticManager):
        def __init__(self) -> None:
            pass

        def collect_memory_diagnostic(
            self,
            *,
            limit: int = 20,
            collect_gc: bool = True,
        ) -> dict[str, object]:
            return {
                "limit": limit,
                "collect_gc": collect_gc,
                "ok": True,
            }

    app = FastAPI()
    app.state.runtime_diagnostic_manager = FakeManager()
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    response = client.get(
        "/api/runtime/memory-diagnostic?limit=5&collect_gc=false",
    )

    assert response.status_code == 200
    assert response.json() == {
        "limit": 5,
        "collect_gc": False,
        "ok": True,
    }


def test_memory_diagnostic_route_requires_runtime_manager() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/runtime/memory-diagnostic")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Runtime diagnostic manager is unavailable",
    }


def test_memory_diagnostic_route_bypasses_auth_and_tenant_middleware(
    monkeypatch,
) -> None:
    class FakeManager(RuntimeDiagnosticManager):
        def __init__(self) -> None:
            pass

        def collect_memory_diagnostic(
            self,
            *,
            limit: int = 20,
            collect_gc: bool = True,
        ) -> dict[str, object]:
            return {"ok": True, "limit": limit, "collect_gc": collect_gc}

    monkeypatch.setattr("swe.app.auth.is_auth_enabled", lambda: True)
    monkeypatch.setattr("swe.app.auth.has_registered_users", lambda: True)

    app = FastAPI()
    app.state.runtime_diagnostic_manager = FakeManager()
    app.include_router(router, prefix="/api")
    app.add_middleware(AuthMiddleware)
    app.add_middleware(TenantWorkspaceMiddleware)
    app.add_middleware(TenantIdentityMiddleware, default_tenant_id=None)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(
        "/api/runtime/memory-diagnostic?limit=3&collect_gc=false",
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "limit": 3,
        "collect_gc": False,
    }
