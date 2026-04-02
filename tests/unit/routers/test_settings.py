# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name
"""Unit tests for the tenant-scoped settings router (/api/settings/language)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from copaw.app.routers.settings import router

app = FastAPI()
app.include_router(router, prefix="/api")


@pytest.fixture(autouse=True)
def _use_tmp_settings(tmp_path: Path):
    """Redirect settings file to a temp directory for every test."""
    # Create tenant directories
    tenant_a_dir = tmp_path / "tenant-a"
    tenant_b_dir = tmp_path / "tenant-b"
    tenant_a_dir.mkdir()
    tenant_b_dir.mkdir()

    settings_file_a = tenant_a_dir / "settings.json"
    settings_file_b = tenant_b_dir / "settings.json"

    # Patch get_tenant_working_dir to return tenant-specific paths
    def mock_get_tenant_working_dir(tenant_id=None):
        if tenant_id == "tenant-a":
            return tenant_a_dir
        if tenant_id == "tenant-b":
            return tenant_b_dir
        return tmp_path / (tenant_id or "default")

    with patch(
        "copaw.app.routers.settings.get_tenant_working_dir",
        mock_get_tenant_working_dir,
    ):
        yield {
            "tenant-a": settings_file_a,
            "tenant-b": settings_file_b,
            "tmp_path": tmp_path,
        }


@pytest.fixture
def api_client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ── GET /settings/language ───────────────────────────────────────────


async def test_get_language_default(api_client):
    """Should return 'en' when no settings file exists."""
    async with api_client:
        resp = await api_client.get("/api/settings/language")
    assert resp.status_code == 200
    assert resp.json() == {"language": "en"}


async def test_get_language_persisted(api_client, _use_tmp_settings):
    """Should return the persisted language value."""
    _use_tmp_settings["tenant-a"].write_text(
        json.dumps({"language": "ja"}), "utf-8"
    )
    async with api_client:
        resp = await api_client.get(
            "/api/settings/language",
            headers={"X-Tenant-Id": "tenant-a"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"language": "ja"}


# ── PUT /settings/language ───────────────────────────────────────────


@pytest.mark.parametrize("lang", ["en", "zh", "ja", "ru"])
async def test_put_language_valid(
    api_client,
    lang,
    _use_tmp_settings,
):
    """Should accept all valid languages and persist them."""
    async with api_client:
        resp = await api_client.put(
            "/api/settings/language",
            json={"language": lang},
            headers={"X-Tenant-Id": "tenant-a"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"language": lang}

    data = json.loads(_use_tmp_settings["tenant-a"].read_text("utf-8"))
    assert data["language"] == lang


async def test_put_language_invalid(api_client):
    """Should reject invalid language with 400."""
    async with api_client:
        resp = await api_client.put(
            "/api/settings/language",
            json={"language": "xx"},
            headers={"X-Tenant-Id": "tenant-a"},
        )
    assert resp.status_code == 400
    assert "Invalid language" in resp.json()["detail"]


async def test_put_language_empty(api_client):
    """Should reject empty language with 400."""
    async with api_client:
        resp = await api_client.put(
            "/api/settings/language",
            json={"language": ""},
            headers={"X-Tenant-Id": "tenant-a"},
        )
    assert resp.status_code == 400


async def test_put_language_missing_key(api_client):
    """Should reject body without 'language' key with 400."""
    async with api_client:
        resp = await api_client.put(
            "/api/settings/language",
            json={"lang": "zh"},
            headers={"X-Tenant-Id": "tenant-a"},
        )
    assert resp.status_code == 400


async def test_put_then_get_roundtrip(api_client):
    """PUT then GET should return the updated language."""
    async with api_client:
        await api_client.put(
            "/api/settings/language",
            json={"language": "ru"},
            headers={"X-Tenant-Id": "tenant-a"},
        )
        resp = await api_client.get(
            "/api/settings/language",
            headers={"X-Tenant-Id": "tenant-a"},
        )
    assert resp.json() == {"language": "ru"}


async def test_put_language_preserves_other_settings(
    api_client,
    _use_tmp_settings,
):
    """PUT should not overwrite other keys in settings.json."""
    _use_tmp_settings["tenant-a"].write_text(
        json.dumps({"theme": "dark", "language": "en"}),
        "utf-8",
    )
    async with api_client:
        await api_client.put(
            "/api/settings/language",
            json={"language": "zh"},
            headers={"X-Tenant-Id": "tenant-a"},
        )

    data = json.loads(_use_tmp_settings["tenant-a"].read_text("utf-8"))
    assert data["language"] == "zh"
    assert data["theme"] == "dark"


# ── Tenant isolation tests ───────────────────────────────────────────


async def test_tenant_a_cannot_see_tenant_b_settings(
    api_client,
    _use_tmp_settings,
):
    """Tenant A should not see Tenant B's settings."""
    # Set different languages for each tenant
    _use_tmp_settings["tenant-a"].write_text(
        json.dumps({"language": "zh"}), "utf-8"
    )
    _use_tmp_settings["tenant-b"].write_text(
        json.dumps({"language": "ja"}), "utf-8"
    )

    async with api_client:
        # Tenant A gets zh
        resp_a = await api_client.get(
            "/api/settings/language",
            headers={"X-Tenant-Id": "tenant-a"},
        )
        # Tenant B gets ja
        resp_b = await api_client.get(
            "/api/settings/language",
            headers={"X-Tenant-Id": "tenant-b"},
        )

    assert resp_a.json() == {"language": "zh"}
    assert resp_b.json() == {"language": "ja"}


async def test_tenant_settings_are_isolated(
    api_client,
    _use_tmp_settings,
):
    """Changing settings for one tenant doesn't affect another."""
    async with api_client:
        # Set tenant-a to zh
        await api_client.put(
            "/api/settings/language",
            json={"language": "zh"},
            headers={"X-Tenant-Id": "tenant-a"},
        )

        # Set tenant-b to ja
        await api_client.put(
            "/api/settings/language",
            json={"language": "ja"},
            headers={"X-Tenant-Id": "tenant-b"},
        )

        # Verify tenant-a still has zh
        resp_a = await api_client.get(
            "/api/settings/language",
            headers={"X-Tenant-Id": "tenant-a"},
        )
        # Verify tenant-b still has ja
        resp_b = await api_client.get(
            "/api/settings/language",
            headers={"X-Tenant-Id": "tenant-b"},
        )

    assert resp_a.json() == {"language": "zh"}
    assert resp_b.json() == {"language": "ja"}

    # Verify files are separate
    data_a = json.loads(_use_tmp_settings["tenant-a"].read_text("utf-8"))
    data_b = json.loads(_use_tmp_settings["tenant-b"].read_text("utf-8"))
    assert data_a["language"] == "zh"
    assert data_b["language"] == "ja"
