# -*- coding: utf-8 -*-
"""Tests for on-demand runtime memory diagnostics."""

from __future__ import annotations

import asyncio
import json
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


def test_collect_memory_type_holders_reports_referrer_types(
    monkeypatch,
) -> None:
    class TargetProbe:
        pass

    class HolderProbe:
        pass

    target = TargetProbe()
    holder = HolderProbe()
    holder.target = target
    referrers = [
        holder,
        holder.__dict__,
    ]
    objgraph = SimpleNamespace(
        by_type=lambda type_name: (
            [target] if type_name == "TargetProbe" else []
        ),
    )

    def fake_import(module_name: str):
        assert module_name == "objgraph"
        return objgraph

    def fake_get_referrers(obj):
        if obj is target:
            return referrers
        if obj is holder.__dict__:
            return [holder]
        return []

    monkeypatch.setattr(runtime_diagnostic, "import_module", fake_import)
    monkeypatch.setattr(runtime_diagnostic.gc, "collect", lambda: 2)
    monkeypatch.setattr(
        runtime_diagnostic.gc,
        "get_referrers",
        fake_get_referrers,
    )

    payload = _manager().collect_memory_type_holders(
        type_name="TargetProbe",
        holder_type_filter="HolderProbe",
        target_index=0,
        max_samples_per_type=2,
        collect_gc=True,
    )

    assert payload["schema"] == "runtime_diagnostic.v1"
    assert payload["event_type"] == "memory_type_holders"
    assert payload["type_name"] == "TargetProbe"
    assert payload["target_count"] == 1
    assert payload["target_index"] == 0
    assert payload["gc_collected"] == 2
    assert payload["objgraph_available"] is True
    assert payload["holder_type_counts"] == [
        {
            "type": (
                "tests.unit.app.test_runtime_memory_diagnostic."
                "test_collect_memory_type_holders_reports_referrer_types."
                "<locals>.HolderProbe"
            ),
            "count": 1,
        },
    ]
    assert payload["samples"][0]["holder_py_type"] == "HolderProbe"
    assert payload["samples"][0]["owner_hint"] is None
    assert payload["errors"] == []


def test_memory_diff_probe_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SWE_MEMORY_DIFF_PROBE_ENABLED", raising=False)

    manager = _manager()

    assert manager._memory_diff_probe_enabled is False
    assert manager._memory_diff_interval_seconds == 300.0


def test_memory_diff_probe_can_be_enabled_with_interval_env(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SWE_MEMORY_DIFF_PROBE_ENABLED", "true")
    monkeypatch.setenv("SWE_MEMORY_DIFF_PROBE_INTERVAL_SECONDS", "60")

    manager = _manager()

    assert manager._memory_diff_probe_enabled is True
    assert manager._memory_diff_interval_seconds == 60.0


def test_memory_diff_snapshot_reports_last_snapshot_delta(
    monkeypatch,
) -> None:
    manager = _manager()
    snapshots = [
        {
            "event_at_ms": 1000,
            "process_rss_bytes": 100,
            "process_vms_bytes": 1000,
            "process_thread_count": 2,
            "process_open_fd_count": 3,
            "gc_object_count": 10,
            "objgraph_type_count": 5,
            "pympler_object_count": 8,
            "top_object_types": [
                {"type": "dict", "count": 4},
                {"type": "list", "count": 2},
            ],
            "top_memory_types": [
                {"type": "dict", "count": 4, "size_bytes": 400},
            ],
            "errors": [],
        },
        {
            "event_at_ms": 2000,
            "process_rss_bytes": 150,
            "process_vms_bytes": 980,
            "process_thread_count": 3,
            "process_open_fd_count": 6,
            "gc_object_count": 16,
            "objgraph_type_count": 7,
            "pympler_object_count": 11,
            "top_object_types": [
                {"type": "dict", "count": 7},
                {"type": "tuple", "count": 9},
            ],
            "top_memory_types": [
                {"type": "dict", "count": 7, "size_bytes": 900},
                {"type": "tuple", "count": 9, "size_bytes": 100},
            ],
            "errors": [],
        },
    ]
    monkeypatch.setattr(
        manager,
        "collect_memory_diagnostic",
        lambda limit=20, collect_gc=True: snapshots.pop(0),
    )

    baseline = manager.collect_memory_diff_snapshot(tag="baseline")
    after = manager.collect_memory_diff_snapshot(tag="periodic")

    assert baseline["has_previous_snapshot"] is False
    assert baseline["rss_delta_bytes"] is None
    assert after["has_previous_snapshot"] is True
    assert after["from_tag"] == "baseline"
    assert after["to_tag"] == "periodic"
    assert after["elapsed_ms"] == 1000
    assert after["rss_delta_bytes"] == 50
    assert after["vms_delta_bytes"] == -20
    assert after["thread_delta"] == 1
    assert after["open_fd_delta"] == 3
    assert after["gc_object_delta"] == 6
    assert after["objgraph_type_count_delta"] == 2
    assert after["pympler_object_count_delta"] == 3
    assert after["top_object_type_deltas"] == [
        {"type": "tuple", "count_delta": 9},
        {"type": "dict", "count_delta": 3},
        {"type": "list", "count_delta": -2},
    ]
    assert after["top_memory_type_deltas"] == [
        {"type": "dict", "count_delta": 3, "size_bytes_delta": 500},
        {"type": "tuple", "count_delta": 9, "size_bytes_delta": 100},
    ]


def test_emit_memory_diff_probe_logs_json_event(monkeypatch) -> None:
    messages: list[str] = []
    manager = _manager(log_sink=messages.append)
    monkeypatch.setattr(
        manager,
        "collect_memory_diff_snapshot",
        lambda tag: {
            "schema": "runtime_diagnostic.v1",
            "event_type": "memory_diff_probe",
            "tag": tag,
        },
    )

    manager.emit_memory_diff_probe(tag="manual")

    assert len(messages) == 1
    assert messages[0].startswith("RUNTIME_DIAGNOSTIC ")
    payload = json.loads(messages[0].removeprefix("RUNTIME_DIAGNOSTIC "))
    assert payload == {
        "schema": "runtime_diagnostic.v1",
        "event_type": "memory_diff_probe",
        "tag": "manual",
    }


async def test_start_adds_memory_diff_task_only_when_enabled(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SWE_MEMORY_DIFF_PROBE_ENABLED", "true")
    manager = _manager()
    created_names: list[str] = []
    original_create_task = asyncio.create_task

    async def never() -> None:
        await asyncio.Event().wait()

    async def fake_sampler() -> None:
        await never()

    async def fake_periodic() -> None:
        await never()

    async def fake_memory_diff() -> None:
        await never()

    def fake_create_task(coro, *, name=None):
        created_names.append(name)
        task = original_create_task(coro)
        return task

    monkeypatch.setattr(manager, "run_sampler_loop", fake_sampler)
    monkeypatch.setattr(manager, "run_periodic_loop", fake_periodic)
    monkeypatch.setattr(
        manager,
        "run_memory_diff_probe_loop",
        fake_memory_diff,
    )
    monkeypatch.setattr(
        runtime_diagnostic.asyncio,
        "create_task",
        fake_create_task,
    )

    await manager.start()
    await manager.stop()

    assert created_names == [
        "runtime-diagnostic-sampler",
        "runtime-diagnostic-emitter",
        "runtime-memory-diff-probe",
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


def test_memory_type_holders_route_calls_runtime_manager() -> None:
    class FakeManager(RuntimeDiagnosticManager):
        def __init__(self) -> None:
            pass

        def collect_memory_type_holders(
            self,
            *,
            type_name: str,
            target_index: int = 0,
            holder_type_filter: str | None = None,
            max_samples_per_type: int = 5,
            collect_gc: bool = True,
        ) -> dict[str, object]:
            return {
                "type_name": type_name,
                "target_index": target_index,
                "holder_type_filter": holder_type_filter,
                "max_samples_per_type": max_samples_per_type,
                "collect_gc": collect_gc,
                "ok": True,
            }

    app = FastAPI()
    app.state.runtime_diagnostic_manager = FakeManager()
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    response = client.get(
        "/api/runtime/memory-type-holders"
        "?type_name=TargetProbe"
        "&target_index=1"
        "&holder_type_filter=HolderProbe"
        "&max_samples_per_type=3"
        "&collect_gc=false",
    )

    assert response.status_code == 200
    assert response.json() == {
        "type_name": "TargetProbe",
        "target_index": 1,
        "holder_type_filter": "HolderProbe",
        "max_samples_per_type": 3,
        "collect_gc": False,
        "ok": True,
    }


def test_inotify_diagnostic_route_passes_details_with_runtime_token(
    monkeypatch,
) -> None:
    class FakeManager(RuntimeDiagnosticManager):
        def __init__(self) -> None:
            pass

        def collect_inotify_diagnostic(
            self,
            *,
            max_fdinfo_bytes: int = 65536,
            include_fdinfo: bool = False,
            include_details: bool = True,
        ) -> dict[str, object]:
            return {
                "max_fdinfo_bytes": max_fdinfo_bytes,
                "include_fdinfo": include_fdinfo,
                "include_details": include_details,
                "ok": True,
            }

    app = FastAPI()
    app.state.runtime_diagnostic_manager = FakeManager()
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    monkeypatch.setenv("SWE_RUNTIME_DIAGNOSTIC_TOKEN", "secret-token")

    response = client.get(
        "/api/runtime/inotify-diagnostic"
        "?max_fdinfo_bytes=128"
        "&include_fdinfo=true",
        headers={"X-Runtime-Diagnostic-Token": "secret-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "max_fdinfo_bytes": 128,
        "include_fdinfo": True,
        "include_details": True,
        "ok": True,
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


def test_inotify_diagnostic_route_bypasses_auth_and_tenant_middleware(
    monkeypatch,
) -> None:
    class FakeManager(RuntimeDiagnosticManager):
        def __init__(self) -> None:
            pass

        def collect_inotify_diagnostic(
            self,
            *,
            max_fdinfo_bytes: int = 65536,
            include_fdinfo: bool = False,
            include_details: bool = True,
        ) -> dict[str, object]:
            return {"ok": True}

    monkeypatch.setattr("swe.app.auth.is_auth_enabled", lambda: True)
    monkeypatch.setattr("swe.app.auth.has_registered_users", lambda: True)

    app = FastAPI()
    app.state.runtime_diagnostic_manager = FakeManager()
    app.include_router(router, prefix="/api")
    app.add_middleware(AuthMiddleware)
    app.add_middleware(TenantWorkspaceMiddleware)
    app.add_middleware(TenantIdentityMiddleware, default_tenant_id=None)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/runtime/inotify-diagnostic")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_inotify_diagnostic_route_rejects_raw_fdinfo_without_token() -> None:
    class FakeManager(RuntimeDiagnosticManager):
        def __init__(self) -> None:
            pass

        def collect_inotify_diagnostic(
            self,
            *,
            max_fdinfo_bytes: int = 65536,
            include_fdinfo: bool = False,
            include_details: bool = True,
        ) -> dict[str, object]:
            return {"ok": True}

    app = FastAPI()
    app.state.runtime_diagnostic_manager = FakeManager()
    app.include_router(router, prefix="/api")
    client = TestClient(app, client=("203.0.113.10", 12345))

    response = client.get(
        "/api/runtime/inotify-diagnostic?include_fdinfo=true",
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Raw inotify fdinfo requires a runtime diagnostic token"
    )


def test_inotify_diagnostic_route_redacts_remote_details() -> None:
    class FakeManager(RuntimeDiagnosticManager):
        def __init__(self) -> None:
            pass

        def collect_inotify_diagnostic(
            self,
            *,
            max_fdinfo_bytes: int = 65536,
            include_fdinfo: bool = False,
            include_details: bool = True,
        ) -> dict[str, object]:
            return {
                "include_fdinfo": include_fdinfo,
                "include_details": include_details,
            }

    app = FastAPI()
    app.state.runtime_diagnostic_manager = FakeManager()
    app.include_router(router, prefix="/api")
    client = TestClient(app, client=("203.0.113.10", 12345))

    response = client.get("/api/runtime/inotify-diagnostic")

    assert response.status_code == 200
    assert response.json() == {
        "include_fdinfo": False,
        "include_details": False,
    }


def test_inotify_diagnostic_route_redacts_localhost_without_token() -> None:
    class FakeManager(RuntimeDiagnosticManager):
        def __init__(self) -> None:
            pass

        def collect_inotify_diagnostic(
            self,
            *,
            max_fdinfo_bytes: int = 65536,
            include_fdinfo: bool = False,
            include_details: bool = True,
        ) -> dict[str, object]:
            return {
                "include_fdinfo": include_fdinfo,
                "include_details": include_details,
            }

    app = FastAPI()
    app.state.runtime_diagnostic_manager = FakeManager()
    app.include_router(router, prefix="/api")
    client = TestClient(app, client=("127.0.0.1", 12345))

    response = client.get("/api/runtime/inotify-diagnostic")

    assert response.status_code == 200
    assert response.json() == {
        "include_fdinfo": False,
        "include_details": False,
    }


def test_memory_type_holders_route_bypasses_auth_and_tenant_middleware(
    monkeypatch,
) -> None:
    class FakeManager(RuntimeDiagnosticManager):
        def __init__(self) -> None:
            pass

        def collect_memory_type_holders(
            self,
            *,
            type_name: str,
            target_index: int = 0,
            holder_type_filter: str | None = None,
            max_samples_per_type: int = 5,
            collect_gc: bool = True,
        ) -> dict[str, object]:
            return {"ok": True, "type_name": type_name}

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
        "/api/runtime/memory-type-holders?type_name=TargetProbe",
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "type_name": "TargetProbe",
    }
