# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name
"""Unit tests for the tenant-scoped settings router (/api/settings/language)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from swe.app.middleware.tenant_identity import TenantIdentityMiddleware
from swe.app.routers.settings import router
from swe.config.context import encode_scope_id

app = FastAPI()
app.add_middleware(
    TenantIdentityMiddleware,
    require_tenant=False,
    default_tenant_id=None,
)
app.include_router(router, prefix="/api")

_SOURCE_HEADERS = {"X-Source-Id": "source-a"}


@pytest.fixture(autouse=True)
def _use_tmp_settings(tmp_path: Path):
    """Redirect settings file to a temp directory for every test."""

    def mock_get_tenant_request_working_dir(tenant_id=None):
        tenant_dir = tmp_path / (tenant_id or "default")
        tenant_dir.mkdir(parents=True, exist_ok=True)
        return tenant_dir

    with patch(
        "swe.app.routers.settings.get_tenant_request_working_dir",
        mock_get_tenant_request_working_dir,
    ):
        yield {
            "tenant-a": tmp_path / "tenant-a" / "settings.json",
            "tenant-b": tmp_path / "tenant-b" / "settings.json",
            "tmp_path": tmp_path,
        }


@pytest.fixture
def api_client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ── GET /settings/language ───────────────────────────────────────────


def test_get_language_default(api_client):
    """Should return 'en' when no settings file exists."""

    async def run_test():
        async with api_client:
            return await api_client.get(
                "/api/settings/language",
                headers=_SOURCE_HEADERS,
            )

    resp = asyncio.run(run_test())
    assert resp.status_code == 200
    assert resp.json() == {"language": "en"}


def test_get_language_persisted(api_client, _use_tmp_settings):
    """Should return the persisted language value."""
    scope_file = (
        _use_tmp_settings["tmp_path"]
        / encode_scope_id("tenant-a", "source-a")
        / "settings.json"
    )
    scope_file.parent.mkdir(parents=True, exist_ok=True)
    scope_file.write_text(
        json.dumps({"language": "ja"}),
        "utf-8",
    )

    async def run_test():
        async with api_client:
            return await api_client.get(
                "/api/settings/language",
                headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
            )

    resp = asyncio.run(run_test())
    assert resp.status_code == 200
    assert resp.json() == {"language": "ja"}


# ── PUT /settings/language ───────────────────────────────────────────


@pytest.mark.parametrize("lang", ["en", "zh", "ja", "ru"])
def test_put_language_valid(
    api_client,
    lang,
    _use_tmp_settings,
):
    """Should accept all valid languages and persist them."""

    async def run_test():
        async with api_client:
            return await api_client.put(
                "/api/settings/language",
                json={"language": lang},
                headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
            )

    resp = asyncio.run(run_test())
    assert resp.status_code == 200
    assert resp.json() == {"language": lang}

    scope_file = (
        _use_tmp_settings["tmp_path"]
        / encode_scope_id("tenant-a", "source-a")
        / "settings.json"
    )
    data = json.loads(scope_file.read_text("utf-8"))
    assert data["language"] == lang


def test_put_language_invalid(api_client):
    """Should reject invalid language with 400."""

    async def run_test():
        async with api_client:
            return await api_client.put(
                "/api/settings/language",
                json={"language": "xx"},
                headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
            )

    resp = asyncio.run(run_test())
    assert resp.status_code == 400
    assert "Invalid language" in resp.json()["detail"]


def test_put_language_empty(api_client):
    """Should reject empty language with 400."""

    async def run_test():
        async with api_client:
            return await api_client.put(
                "/api/settings/language",
                json={"language": ""},
                headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
            )

    resp = asyncio.run(run_test())
    assert resp.status_code == 400


def test_put_language_missing_key(api_client):
    """Should reject body without 'language' key with 400."""

    async def run_test():
        async with api_client:
            return await api_client.put(
                "/api/settings/language",
                json={"lang": "zh"},
                headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
            )

    resp = asyncio.run(run_test())
    assert resp.status_code == 400


def test_put_then_get_roundtrip(api_client):
    """PUT then GET should return the updated language."""

    async def run_test():
        async with api_client:
            await api_client.put(
                "/api/settings/language",
                json={"language": "ru"},
                headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
            )
            return await api_client.get(
                "/api/settings/language",
                headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
            )

    resp = asyncio.run(run_test())
    assert resp.json() == {"language": "ru"}


def test_put_language_preserves_other_settings(
    api_client,
    _use_tmp_settings,
):
    """PUT should not overwrite other keys in settings.json."""
    scope_file = (
        _use_tmp_settings["tmp_path"]
        / encode_scope_id("tenant-a", "source-a")
        / "settings.json"
    )
    scope_file.parent.mkdir(parents=True, exist_ok=True)
    scope_file.write_text(
        json.dumps({"theme": "dark", "language": "en"}),
        "utf-8",
    )

    async def run_test():
        async with api_client:
            await api_client.put(
                "/api/settings/language",
                json={"language": "zh"},
                headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
            )

    asyncio.run(run_test())

    data = json.loads(scope_file.read_text("utf-8"))
    assert data["language"] == "zh"
    assert data["theme"] == "dark"


# ── Tenant isolation tests ───────────────────────────────────────────


def test_tenant_a_cannot_see_tenant_b_settings(
    api_client,
    _use_tmp_settings,
):
    """Tenant A should not see Tenant B's settings."""
    tenant_a_scope_file = (
        _use_tmp_settings["tmp_path"]
        / encode_scope_id("tenant-a", "source-a")
        / "settings.json"
    )
    tenant_b_scope_file = (
        _use_tmp_settings["tmp_path"]
        / encode_scope_id("tenant-b", "source-a")
        / "settings.json"
    )
    tenant_a_scope_file.parent.mkdir(parents=True, exist_ok=True)
    tenant_b_scope_file.parent.mkdir(parents=True, exist_ok=True)
    tenant_a_scope_file.write_text(
        json.dumps({"language": "zh"}),
        "utf-8",
    )
    tenant_b_scope_file.write_text(
        json.dumps({"language": "ja"}),
        "utf-8",
    )

    async def run_test():
        async with api_client:
            resp_a = await api_client.get(
                "/api/settings/language",
                headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
            )
            resp_b = await api_client.get(
                "/api/settings/language",
                headers={"X-Tenant-Id": "tenant-b", **_SOURCE_HEADERS},
            )
            return resp_a, resp_b

    resp_a, resp_b = asyncio.run(run_test())
    assert resp_a.json() == {"language": "zh"}
    assert resp_b.json() == {"language": "ja"}


def test_tenant_settings_are_isolated(
    api_client,
    _use_tmp_settings,
):
    """Changing settings for one tenant doesn't affect another."""

    async def run_test():
        async with api_client:
            await api_client.put(
                "/api/settings/language",
                json={"language": "zh"},
                headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
            )
            await api_client.put(
                "/api/settings/language",
                json={"language": "ja"},
                headers={"X-Tenant-Id": "tenant-b", **_SOURCE_HEADERS},
            )
            resp_a = await api_client.get(
                "/api/settings/language",
                headers={"X-Tenant-Id": "tenant-a", **_SOURCE_HEADERS},
            )
            resp_b = await api_client.get(
                "/api/settings/language",
                headers={"X-Tenant-Id": "tenant-b", **_SOURCE_HEADERS},
            )
            return resp_a, resp_b

    resp_a, resp_b = asyncio.run(run_test())
    assert resp_a.json() == {"language": "zh"}
    assert resp_b.json() == {"language": "ja"}

    data_a = json.loads(
        (
            _use_tmp_settings["tmp_path"]
            / encode_scope_id("tenant-a", "source-a")
            / "settings.json"
        ).read_text("utf-8"),
    )
    data_b = json.loads(
        (
            _use_tmp_settings["tmp_path"]
            / encode_scope_id("tenant-b", "source-a")
            / "settings.json"
        ).read_text("utf-8"),
    )
    assert data_a["language"] == "zh"
    assert data_b["language"] == "ja"


def test_same_tenant_different_sources_use_scope_specific_settings_file(
    _use_tmp_settings,
):
    """同一 tenant 的不同 source 必须落到不同 scope 文件。"""
    from swe.app.routers import settings as settings_router

    request = type(
        "Req",
        (),
        {
            "state": type(
                "State",
                (),
                {
                    "tenant_id": "tenant-a",
                    "scope_id": encode_scope_id("tenant-a", "source-b"),
                },
            )(),
        },
    )()

    settings_file = settings_router._get_settings_file(request)

    assert settings_file == (
        _use_tmp_settings["tmp_path"]
        / encode_scope_id("tenant-a", "source-b")
        / "settings.json"
    )
