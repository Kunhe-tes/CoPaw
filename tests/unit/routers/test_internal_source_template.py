# -*- coding: utf-8 -*-
"""Contract tests for explicit source-template provisioning."""

import sys
from unittest.mock import AsyncMock
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "src"))


def _client(pool=None) -> TestClient:
    from swe.app.routers.internal import router

    app = FastAPI()
    if pool is not None:
        app.state.tenant_workspace_pool = pool
    app.include_router(router)
    return TestClient(app)


def test_ensure_source_template_requires_internal_token(monkeypatch) -> None:
    from swe.app.routers import internal

    monkeypatch.setattr(internal, "_INTERNAL_TOKEN", "test-token")

    response = _client().post(
        "/internal/source-templates/ensure",
        json={"source_id": "ruice"},
    )

    assert response.status_code == 401


def test_ensure_source_template_returns_provisioning_status(
    monkeypatch,
) -> None:
    from swe.app.routers import internal

    class FakeProvisioner:
        def __init__(self, _base_working_dir):
            pass

        async def ensure(self, source_id: str):
            return type(
                "Result",
                (),
                {
                    "source_id": source_id,
                    "template_name": "default_ruice",
                    "status": "created",
                },
            )()

    monkeypatch.setattr(internal, "_INTERNAL_TOKEN", "test-token")
    monkeypatch.setattr(internal, "SourceTemplateProvisioner", FakeProvisioner)

    response = _client().post(
        "/internal/source-templates/ensure",
        json={"source_id": "ruice"},
        headers={"X-Internal-Token": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "source_id": "ruice",
        "template_name": "default_ruice",
        "status": "created",
    }


def test_ensure_source_template_invalidates_ready_registry_scope(
    monkeypatch,
) -> None:
    from swe.app.routers import internal

    class FakeProvisioner:
        def __init__(self, _base_working_dir):
            pass

        async def ensure(self, source_id: str):
            return type(
                "Result",
                (),
                {
                    "source_id": source_id,
                    "template_name": "default_ruice",
                    "status": "created",
                },
            )()

    pool = AsyncMock()
    monkeypatch.setattr(internal, "_INTERNAL_TOKEN", "test-token")
    monkeypatch.setattr(internal, "SourceTemplateProvisioner", FakeProvisioner)

    response = _client(pool).post(
        "/internal/source-templates/ensure",
        json={"source_id": "ruice"},
        headers={"X-Internal-Token": "Bearer test-token"},
    )

    assert response.status_code == 200
    pool.invalidate_bootstrap.assert_awaited_once_with(
        "default_ruice",
        reason="source_template_reload",
    )


def test_ensure_source_template_propagates_invalidation_failure(
    monkeypatch,
) -> None:
    from swe.app.routers import internal

    class FakeProvisioner:
        def __init__(self, _base_working_dir):
            pass

        async def ensure(self, source_id: str):
            return type(
                "Result",
                (),
                {
                    "source_id": source_id,
                    "template_name": "default_ruice",
                    "status": "created",
                },
            )()

    pool = AsyncMock()
    pool.invalidate_bootstrap = AsyncMock(
        side_effect=RuntimeError("invalidation failed"),
    )
    monkeypatch.setattr(internal, "_INTERNAL_TOKEN", "test-token")
    monkeypatch.setattr(internal, "SourceTemplateProvisioner", FakeProvisioner)

    with pytest.raises(RuntimeError, match="invalidation failed"):
        _client(pool).post(
            "/internal/source-templates/ensure",
            json={"source_id": "ruice"},
            headers={"X-Internal-Token": "Bearer test-token"},
        )


def test_ensure_source_template_does_not_invalidate_ready_scope(
    monkeypatch,
) -> None:
    from swe.app.routers import internal

    class FakeProvisioner:
        def __init__(self, _base_working_dir):
            pass

        async def ensure(self, source_id: str):
            return type(
                "Result",
                (),
                {
                    "source_id": source_id,
                    "template_name": "default_ruice",
                    "status": "ready",
                },
            )()

    pool = AsyncMock()
    monkeypatch.setattr(internal, "_INTERNAL_TOKEN", "test-token")
    monkeypatch.setattr(internal, "SourceTemplateProvisioner", FakeProvisioner)

    response = _client(pool).post(
        "/internal/source-templates/ensure",
        json={"source_id": "ruice"},
        headers={"X-Internal-Token": "Bearer test-token"},
    )

    assert response.status_code == 200
    pool.invalidate_bootstrap.assert_not_awaited()
