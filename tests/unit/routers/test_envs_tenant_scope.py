# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name
"""Unit tests for tenant-scoped env router and env store behavior."""

from __future__ import annotations

import os
import json
import types
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from swe.app.routers.envs import router
from swe.config.context import encode_scope_id
from swe.envs.store import delete_env_var, load_envs, save_envs

app = FastAPI()


@app.middleware("http")
async def bind_tenant_id(request: Request, call_next):
    """Bind tenant ID from request header for router tests."""
    request.state.tenant_id = request.headers.get("X-Tenant-Id")
    request.state.source_id = request.headers.get("X-Source-Id")
    if request.state.tenant_id and request.state.source_id:
        request.state.scope_id = (
            f"{request.state.tenant_id}.{request.state.source_id}"
        )
    return await call_next(request)


app.include_router(router, prefix="/api")

_SOURCE_HEADERS = {"X-Source-Id": "source-a"}


@pytest.fixture(autouse=True)
def _use_tmp_env_paths(tmp_path: Path):
    """Redirect tenant secrets directories to a temp directory."""

    def mock_get_tenant_secrets_dir(tenant_id=None):
        return tmp_path / (tenant_id or "default") / ".secret"

    with patch(
        "swe.app.routers.envs.get_tenant_secrets_dir",
        mock_get_tenant_secrets_dir,
    ):
        yield tmp_path


@pytest.fixture
def client():
    """Create a sync test client."""
    return TestClient(app)


def test_save_envs_with_custom_path_does_not_mutate_process_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Custom-path env writes should stay file-scoped."""
    envs_path = tmp_path / "tenant-a" / ".secret" / "envs.json"
    monkeypatch.delenv("TENANT_ONLY_KEY", raising=False)

    save_envs({"TENANT_ONLY_KEY": "value-a"}, envs_path)

    assert load_envs(envs_path) == {"TENANT_ONLY_KEY": "value-a"}
    assert "TENANT_ONLY_KEY" not in os.environ


def test_delete_env_var_with_custom_path_does_not_remove_process_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Custom-path deletes should not remove process env vars."""
    envs_path = tmp_path / "tenant-a" / ".secret" / "envs.json"
    monkeypatch.setenv("TENANT_ONLY_KEY", "runtime")
    save_envs({"TENANT_ONLY_KEY": "tenant"}, envs_path)

    delete_env_var("TENANT_ONLY_KEY", envs_path)

    assert load_envs(envs_path) == {}
    assert os.environ["TENANT_ONLY_KEY"] == "runtime"


def test_tenant_env_api_is_file_scoped_not_process_scoped(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    _use_tmp_env_paths: Path,
):
    """Tenant env API writes should not mutate process-global env."""
    monkeypatch.delenv("TENANT_ONLY_KEY", raising=False)

    response = client.put(
        "/api/envs",
        headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
        json={"TENANT_ONLY_KEY": "value-a"},
    )

    envs_path = (
        _use_tmp_env_paths / "tenant-a.source-a" / ".secret" / "envs.json"
    )

    assert response.status_code == 200
    assert load_envs(envs_path) == {"TENANT_ONLY_KEY": "value-a"}
    assert response.json() == [
        {"key": "TENANT_ONLY_KEY", "value": "value-a"},
    ]
    assert "TENANT_ONLY_KEY" not in os.environ


def test_tenant_env_api_rejects_malformed_and_protected_keys(
    client: TestClient,
):
    """API 写入前必须拒绝不可移植或受保护的 env key。"""
    for payload in ({"BAD-NAME": "x"}, {"PATH": "/tmp/bin"}):
        response = client.put(
            "/api/envs",
            headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
            json=payload,
        )

        assert response.status_code == 400
        assert next(iter(payload)) in response.text


def test_list_envs_returns_plain_values(
    client: TestClient,
):
    """GET /envs 返回原始值，便于控制台回显和编辑。"""
    client.put(
        "/api/envs",
        headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
        json={"API_TOKEN": "tenant-secret"},
    )

    response = client.get(
        "/api/envs",
        headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
    )

    assert response.status_code == 200
    assert response.json() == [
        {"key": "API_TOKEN", "value": "tenant-secret"},
    ]
    assert "tenant-secret" in response.text


def test_patch_envs_merges_values_and_preserves_unmentioned_keys(
    client: TestClient,
    _use_tmp_env_paths: Path,
):
    """PATCH /envs 只传 values 时应新增或覆盖并保留未提及变量。"""
    client.put(
        "/api/envs",
        headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
        json={"API_TOKEN": "old-secret", "OLD_KEY": "keep-me"},
    )

    response = client.patch(
        "/api/envs",
        headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
        json={
            "values": {
                "API_TOKEN": "new-secret",
                "NEW_TOKEN": "created-secret",
            },
        },
    )

    envs_path = (
        _use_tmp_env_paths / "tenant-a.source-a" / ".secret" / "envs.json"
    )
    assert response.status_code == 200
    assert load_envs(envs_path) == {
        "API_TOKEN": "new-secret",
        "NEW_TOKEN": "created-secret",
        "OLD_KEY": "keep-me",
    }
    assert response.json() == [
        {"key": "API_TOKEN", "value": "new-secret"},
        {"key": "NEW_TOKEN", "value": "created-secret"},
        {"key": "OLD_KEY", "value": "keep-me"},
    ]


def test_patch_envs_deletes_keys_and_ignores_preserve_compat_field(
    client: TestClient,
    _use_tmp_env_paths: Path,
):
    """preserve 是兼容字段，不应影响 merge 更新结果。"""
    client.put(
        "/api/envs",
        headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
        json={
            "API_TOKEN": "old-secret",
            "OLD_KEY": "remove-me",
            "KEEP_KEY": "keep-me",
        },
    )

    response = client.patch(
        "/api/envs",
        headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
        json={
            "values": {"API_TOKEN": "new-secret"},
            "preserve": ["OLD_KEY"],
            "delete": ["OLD_KEY"],
        },
    )

    envs_path = (
        _use_tmp_env_paths / "tenant-a.source-a" / ".secret" / "envs.json"
    )
    assert response.status_code == 200
    assert load_envs(envs_path) == {
        "API_TOKEN": "new-secret",
        "KEEP_KEY": "keep-me",
    }
    assert response.json() == [
        {"key": "API_TOKEN", "value": "new-secret"},
        {"key": "KEEP_KEY", "value": "keep-me"},
    ]


def test_delete_envs_returns_plain_remaining_values(
    client: TestClient,
):
    """DELETE /envs 返回删除后的原始值列表。"""
    client.put(
        "/api/envs",
        headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
        json={"API_TOKEN": "tenant-secret", "OLD_KEY": "remove-me"},
    )

    response = client.delete(
        "/api/envs/OLD_KEY",
        headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
    )

    assert response.status_code == 200
    assert response.json() == [
        {"key": "API_TOKEN", "value": "tenant-secret"},
    ]


@pytest.mark.parametrize(
    "reserved_key",
    [
        "tenant_id",
        "source_id",
        "target_tenant_id",
        "target_source_id",
    ],
)
def test_current_scope_env_api_rejects_reserved_scope_fields(
    client: TestClient,
    _use_tmp_env_paths: Path,
    reserved_key: str,
):
    """普通 env API 遇到保留 scope 字段时必须显式失败。"""
    current_path = (
        _use_tmp_env_paths / "tenant-a.source-a" / ".secret" / "envs.json"
    )
    save_envs({"EXISTING_TOKEN": "keep-me"}, current_path)

    response = client.put(
        "/api/envs",
        headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
        json={
            reserved_key: "scope-value",
        },
    )

    assert response.status_code == 400
    assert reserved_key in response.text
    assert load_envs(current_path) == {"EXISTING_TOKEN": "keep-me"}


def test_same_logical_tenant_different_sources_use_separate_api_env_files(
    client: TestClient,
    _use_tmp_env_paths: Path,
):
    """同一 logical tenant 的不同 source API 写入必须互相隔离。"""
    response_a = client.put(
        "/api/envs",
        headers={"X-Tenant-Id": "tenant-a", "X-Source-Id": "source-a"},
        json={"API_TOKEN": "source-a"},
    )
    response_b = client.put(
        "/api/envs",
        headers={"X-Tenant-Id": "tenant-a", "X-Source-Id": "source-b"},
        json={"API_TOKEN": "source-b"},
    )

    assert response_a.status_code == 200
    assert response_b.status_code == 200
    assert load_envs(
        _use_tmp_env_paths / "tenant-a.source-a" / ".secret" / "envs.json",
    ) == {"API_TOKEN": "source-a"}
    assert load_envs(
        _use_tmp_env_paths / "tenant-a.source-b" / ".secret" / "envs.json",
    ) == {"API_TOKEN": "source-b"}


def test_manager_target_env_write_requires_manager_role(
    client: TestClient,
):
    """非 manager 角色不能写入显式 target scope env。"""
    response = client.put(
        "/api/envs/target",
        headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
        json={
            "target_tenant_id": "tenant-b",
            "target_source_id": "source-b",
            "values": {"API_TOKEN": "target-secret"},
        },
    )

    assert response.status_code == 403


def test_manager_target_env_write_uses_explicit_scope_and_audit_metadata(
    client: TestClient,
    _use_tmp_env_paths: Path,
):
    """manager target API 应写入目标 scope，并只返回 key 级审计信息。"""
    response = client.put(
        "/api/envs/target",
        headers={
            "X-Tenant-Id": "tenant-a",
            "X-Source-Id": "source-a",
            "X-User-Role": "manager",
            "X-User-Id": "manager-1",
        },
        json={
            "target_tenant_id": "tenant-b",
            "target_source_id": "source-b",
            "values": {"API_TOKEN": "target-secret"},
        },
    )

    target_path = (
        _use_tmp_env_paths
        / encode_scope_id("tenant-b", "source-b")
        / ".secret"
        / "envs.json"
    )
    assert response.status_code == 200
    assert load_envs(target_path) == {"API_TOKEN": "target-secret"}
    assert response.json()["audit"] == {
        "actor": "manager-1",
        "target_tenant_id": "tenant-b",
        "target_source_id": "source-b",
        "keys": ["API_TOKEN"],
    }
    assert "target-secret" not in response.text
    audit_path = target_path.parent / "envs.audit.jsonl"
    audit_record = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert audit_record["actor"] == "manager-1"
    assert audit_record["keys"] == ["API_TOKEN"]
    assert "target-secret" not in audit_path.read_text(encoding="utf-8")


def test_same_tenant_different_sources_use_scope_specific_env_file(
    _use_tmp_env_paths: Path,
):
    """同一 tenant 的不同 source 必须落到不同 scope secrets 目录。"""
    from swe.app.routers import envs as envs_router

    request = types.SimpleNamespace(
        state=types.SimpleNamespace(
            tenant_id="tenant-a",
            scope_id="scope.v1.tenant-a.source-b",
        ),
    )

    envs_path = envs_router._get_tenant_envs_path(request)

    assert envs_path == (
        _use_tmp_env_paths
        / "scope.v1.tenant-a.source-b"
        / ".secret"
        / "envs.json"
    )
