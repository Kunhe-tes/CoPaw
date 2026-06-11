# -*- coding: utf-8 -*-
"""Unit tests for manager system-check cron auth expiry API."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from swe.config.context import encode_scope_id


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from swe.app.routers import system_check

    def mock_get_tenant_secrets_dir(tenant_id=None):
        return tmp_path / (tenant_id or "default") / ".secret"

    monkeypatch.setattr(
        system_check,
        "get_tenant_secrets_dir",
        mock_get_tenant_secrets_dir,
    )
    app = FastAPI()
    app.include_router(system_check.router, prefix="/api")
    return TestClient(app)


def _write_auth(
    root: Path,
    tenant_id: str,
    source_id: str,
    payload: dict,
) -> Path:
    path = (
        root
        / encode_scope_id(tenant_id, source_id)
        / ".secret"
        / "cron_auth.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_batch_auth_expiry_requires_manager_or_admin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from swe.app.routers import system_check

    def fail_if_called(_tenant_id=None):
        raise AssertionError("tenant auth file should not be resolved")

    monkeypatch.setattr(
        system_check,
        "get_tenant_secrets_dir",
        fail_if_called,
    )
    app = FastAPI()
    app.include_router(system_check.router, prefix="/api")
    unauthorized_client = TestClient(app)

    response = unauthorized_client.post(
        "/api/system-check/cron-auth-expiry",
        json={"source_id": "RMASSIST", "tenant_ids": ["tenant-a"]},
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("payload", "expected_field"),
    [
        ({"source_id": "../bad", "tenant_ids": ["tenant-a"]}, "source_id"),
        ({"source_id": "RMASSIST", "tenant_ids": [""]}, "tenant_id"),
        (
            {"source_id": "RMASSIST", "tenant_ids": ["tenant-a", "tenant-a"]},
            "duplicate",
        ),
    ],
)
def test_batch_auth_expiry_rejects_invalid_identity_before_file_access(
    payload: dict,
    expected_field: str,
    monkeypatch: pytest.MonkeyPatch,
):
    from swe.app.routers import system_check

    def fail_if_called(_tenant_id=None):
        raise AssertionError("tenant auth file should not be resolved")

    monkeypatch.setattr(
        system_check,
        "get_tenant_secrets_dir",
        fail_if_called,
    )
    app = FastAPI()
    app.include_router(system_check.router, prefix="/api")
    test_client = TestClient(app)

    response = test_client.post(
        "/api/system-check/cron-auth-expiry",
        headers={"X-User-Role": "manager"},
        json=payload,
    )

    assert response.status_code == 400
    assert expected_field in response.text


def test_batch_auth_expiry_uses_source_scoped_tenant_path(
    client: TestClient,
    tmp_path: Path,
):
    expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    _write_auth(
        tmp_path,
        "tenant-a",
        "RMASSIST",
        {
            "user_info": {"id": "user-a"},
            "user_info_expires_at": expiry.isoformat(),
            "auth_token": "secret-token",
            "cookie_header": "cookie=secret",
        },
    )

    response = client.post(
        "/api/system-check/cron-auth-expiry",
        headers={"X-User-Role": "manager", "X-Source-Id": "default"},
        json={"source_id": "RMASSIST", "tenant_ids": ["tenant-a"]},
    )

    assert response.status_code == 200
    assert response.json()["results"][0] == {
        "tenant_id": "tenant-a",
        "source_id": "RMASSIST",
        "status": "valid",
        "is_expired": False,
        "user_info_expires_at": expiry.isoformat(),
        "message": "Auth user info is valid",
    }
    assert "secret-token" not in response.text
    assert "cookie=secret" not in response.text
    assert str(tmp_path) not in response.text


def test_batch_auth_expiry_classifies_all_result_statuses(
    client: TestClient,
    tmp_path: Path,
):
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    _write_auth(
        tmp_path,
        "valid-tenant",
        "RMASSIST",
        {
            "user_info": {"id": "valid"},
            "user_info_expires_at": future.isoformat(),
        },
    )
    _write_auth(
        tmp_path,
        "expired-tenant",
        "RMASSIST",
        {
            "user_info": {"id": "expired"},
            "user_info_expires_at": past.isoformat(),
        },
    )
    _write_auth(
        tmp_path,
        "unknown-tenant",
        "RMASSIST",
        {"user_info": {"id": "unknown"}},
    )
    invalid_path = (
        tmp_path
        / encode_scope_id("invalid-tenant", "RMASSIST")
        / ".secret"
        / "cron_auth.json"
    )
    invalid_path.parent.mkdir(parents=True)
    invalid_path.write_text("{not-json", encoding="utf-8")

    response = client.post(
        "/api/system-check/cron-auth-expiry",
        headers={"X-User-Role": "admin"},
        json={
            "source_id": "RMASSIST",
            "tenant_ids": [
                "valid-tenant",
                "expired-tenant",
                "missing-tenant",
                "invalid-tenant",
                "unknown-tenant",
            ],
        },
    )

    assert response.status_code == 200
    results = {item["tenant_id"]: item for item in response.json()["results"]}
    assert results["valid-tenant"]["status"] == "valid"
    assert results["valid-tenant"]["is_expired"] is False
    assert results["expired-tenant"]["status"] == "expired"
    assert results["expired-tenant"]["is_expired"] is True
    assert results["missing-tenant"] == {
        "tenant_id": "missing-tenant",
        "source_id": "RMASSIST",
        "status": "missing_file",
        "is_expired": None,
        "user_info_expires_at": None,
        "message": "No cron auth file was found",
    }
    assert results["invalid-tenant"]["status"] == "invalid_content"
    assert results["invalid-tenant"]["is_expired"] is None
    assert results["unknown-tenant"]["status"] == "unknown"
    assert results["unknown-tenant"]["is_expired"] is None
