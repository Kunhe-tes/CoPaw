# -*- coding: utf-8 -*-
"""持续治理分析报表路由测试。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from swe.app.routers.dream_logs import router
from swe.config.context import encode_scope_id


class _FakeTenantSourceStore:
    """为报表测试提供当前 source 下的可管理用户清单。"""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[str] = []

    async def get_by_source(self, source_id: str) -> list[dict[str, Any]]:
        """只返回指定 source 的用户，模拟数据库隔离口径。"""
        self.calls.append(source_id)
        return [
            row for row in self.rows if row.get("source_id") == source_id
        ]


def _dream_record(
    record_id: str,
    *,
    timestamp: str,
    status: str = "success",
    trigger: str = "manual",
    size_saved: int = 100,
    files_changed: int = 1,
    duration_ms: int = 1000,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "id": record_id,
        "timestamp": timestamp,
        "trigger": trigger,
        "status": status,
        "files_optimized": ["MEMORY.md"],
        "file_stats": {
            "MEMORY.md": {
                "size_before": 1000,
                "size_after": 1000 - size_saved,
                "size_saved": size_saved,
                "lines_before": 40,
                "lines_after": 30,
                "lines_removed": 10,
                "backup_path": "backup/memory.md",
            },
        },
        "total_size_saved": size_saved,
        "total_files_changed": files_changed,
        "duration_ms": duration_ms,
        "model_used": "gpt-test",
        "input_tokens": 10,
        "output_tokens": 20,
        "summary": "ok",
        "error": error,
    }


def _tenant_agent_dir(
    base_dir: Path,
    tenant_id: str,
    source_id: str,
    agent_id: str = "default",
) -> Path:
    workspace_dir = (
        base_dir
        / encode_scope_id(tenant_id, source_id)
        / "workspaces"
        / agent_id
    )
    workspace_dir.mkdir(parents=True, exist_ok=True)
    return workspace_dir


def _write_dream_logs(
    base_dir: Path,
    tenant_id: str,
    source_id: str,
    records: list[dict[str, Any]],
    *,
    agent_id: str = "default",
) -> None:
    workspace_dir = _tenant_agent_dir(base_dir, tenant_id, source_id, agent_id)
    stats = {
        "total_executions": len(records),
        "success_count": sum(
            1 for record in records if record["status"] == "success"
        ),
        "failed_count": sum(
            1 for record in records if record["status"] == "failed"
        ),
        "total_size_saved": sum(
            record.get("total_size_saved", 0) for record in records
        ),
        "total_files_changed": sum(
            record.get("total_files_changed", 0) for record in records
        ),
        "total_duration_ms": sum(
            record.get("duration_ms", 0) for record in records
        ),
        "last_execution": max(
            (record.get("timestamp") for record in records),
            default=None,
        ),
    }
    (workspace_dir / "dream_logs.json").write_text(
        json.dumps({"records": records, "stats": stats}),
        encoding="utf-8",
    )


def _write_damaged_dream_logs(
    base_dir: Path,
    tenant_id: str,
    source_id: str,
) -> None:
    workspace_dir = _tenant_agent_dir(base_dir, tenant_id, source_id)
    (workspace_dir / "dream_logs.json").write_text(
        "{not-valid-json",
        encoding="utf-8",
    )


def _client(
    tmp_path: Path,
    monkeypatch,
    rows: list[dict[str, Any]],
) -> tuple[TestClient, _FakeTenantSourceStore]:
    store = _FakeTenantSourceStore(rows)
    monkeypatch.setattr(
        "swe.app.workspace.tenant_init_source_store"
        ".get_tenant_init_source_store",
        lambda: store,
    )

    app = FastAPI()

    @app.middleware("http")
    async def _attach_request_state(request: Request, call_next):
        source_id = request.headers.get("X-Source-Id", "source-a")
        scope_id = encode_scope_id("manager", source_id)
        request.state.source_id = source_id
        request.state.tenant_id = "manager"
        request.state.scope_id = scope_id
        request.state.workspace = SimpleNamespace(
            workspace_dir=tmp_path / scope_id,
        )
        request.state.workspace.workspace_dir.mkdir(
            parents=True,
            exist_ok=True,
        )
        return await call_next(request)

    app.include_router(router)
    return TestClient(app), store


def test_report_requires_manager_or_admin(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch, [])

    response = client.get(
        "/dream-logs/report",
        headers={"X-Source-Id": "source-a", "X-User-Role": "user"},
    )

    assert response.status_code == 403


def test_report_aggregates_current_source_and_keeps_no_log_users(
    tmp_path,
    monkeypatch,
) -> None:
    rows = [
        {
            "tenant_id": "alice",
            "source_id": "source-a",
            "tenant_name": "Alice",
            "bbk_id": "bbk-1",
        },
        {
            "tenant_id": "bob",
            "source_id": "source-a",
            "tenant_name": "Bob",
            "bbk_id": "bbk-2",
        },
        {
            "tenant_id": "charlie",
            "source_id": "source-b",
            "tenant_name": "Charlie",
            "bbk_id": "bbk-3",
        },
    ]
    _write_dream_logs(
        tmp_path,
        "alice",
        "source-a",
        [
            _dream_record(
                "alice-success",
                timestamp="2026-05-24T09:00:00Z",
                size_saved=200,
            ),
            _dream_record(
                "alice-failed",
                timestamp="2026-05-25T09:00:00Z",
                status="failed",
                trigger="cron",
                size_saved=0,
                files_changed=0,
                error="model timeout",
            ),
        ],
    )
    _write_dream_logs(
        tmp_path,
        "charlie",
        "source-b",
        [
            _dream_record(
                "cross-source",
                timestamp="2026-05-26T09:00:00Z",
                size_saved=999,
            ),
        ],
    )
    client, store = _client(tmp_path, monkeypatch, rows)

    response = client.get(
        "/dream-logs/report",
        headers={"X-Source-Id": "source-a", "X-User-Role": "manager"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert store.calls == ["source-a"]
    assert payload["summary"]["covered_users"] == 2
    assert payload["summary"]["governed_users"] == 1
    assert payload["summary"]["ungoverned_users"] == 1
    assert payload["summary"]["total_executions"] == 2
    assert payload["summary"]["success_count"] == 1
    assert payload["summary"]["failed_count"] == 1
    assert payload["summary"]["total_size_saved"] == 200
    assert {item["user_id"] for item in payload["users"]} == {
        "alice",
        "bob",
    }
    assert "charlie" not in {item["user_id"] for item in payload["users"]}


def test_report_tolerates_damaged_logs_and_applies_filters(
    tmp_path,
    monkeypatch,
) -> None:
    rows = [
        {
            "tenant_id": "alice",
            "source_id": "source-a",
            "tenant_name": "Alice",
            "bbk_id": "bbk-1",
        },
        {
            "tenant_id": "bob",
            "source_id": "source-a",
            "tenant_name": "Bob",
            "bbk_id": "bbk-1",
        },
        {
            "tenant_id": "carol",
            "source_id": "source-a",
            "tenant_name": "Carol",
            "bbk_id": "bbk-2",
        },
    ]
    _write_dream_logs(
        tmp_path,
        "alice",
        "source-a",
        [
            _dream_record(
                "alice-success",
                timestamp="2026-05-24T09:00:00Z",
                status="success",
                trigger="manual",
            ),
        ],
    )
    _write_dream_logs(
        tmp_path,
        "bob",
        "source-a",
        [
            _dream_record(
                "bob-failed",
                timestamp="2026-05-25T09:00:00Z",
                status="failed",
                trigger="cron",
                size_saved=0,
                files_changed=0,
                error="bad response",
            ),
        ],
    )
    _write_damaged_dream_logs(tmp_path, "carol", "source-a")
    client, _ = _client(tmp_path, monkeypatch, rows)

    response = client.get(
        "/dream-logs/report",
        params={
            "status": "failed",
            "trigger": "cron",
            "bbk_id": "bbk-1",
            "page": 1,
            "page_size": 2,
        },
        headers={"X-Source-Id": "source-a", "X-User-Role": "admin"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["covered_users"] == 2
    assert payload["summary"]["governed_users"] == 1
    assert payload["summary"]["total_executions"] == 1
    assert payload["summary"]["failed_count"] == 1
    assert payload["users"][0]["user_id"] == "bob"
    assert payload["users"][0]["latest_error"] == "bad response"


def test_report_user_records_are_read_only_and_source_scoped(
    tmp_path,
    monkeypatch,
) -> None:
    rows = [
        {
            "tenant_id": "alice",
            "source_id": "source-a",
            "tenant_name": "Alice",
            "bbk_id": "bbk-1",
        },
        {
            "tenant_id": "charlie",
            "source_id": "source-b",
            "tenant_name": "Charlie",
            "bbk_id": "bbk-3",
        },
    ]
    _write_dream_logs(
        tmp_path,
        "alice",
        "source-a",
        [
            _dream_record(
                "older",
                timestamp="2026-05-24T09:00:00Z",
            ),
            _dream_record(
                "newer",
                timestamp="2026-05-25T09:00:00Z",
                trigger="cron",
            ),
        ],
    )
    client, _ = _client(tmp_path, monkeypatch, rows)

    response = client.get(
        "/dream-logs/report/users/alice/records",
        params={"page": 1, "page_size": 1, "agent_id": "default"},
        headers={"X-Source-Id": "source-a", "X-User-Role": "manager"},
    )
    cross_source = client.get(
        "/dream-logs/report/users/charlie/records",
        headers={"X-Source-Id": "source-a", "X-User-Role": "manager"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["records"][0]["id"] == "newer"
    assert payload["records"][0]["agent_id"] == "default"
    assert cross_source.status_code == 404
