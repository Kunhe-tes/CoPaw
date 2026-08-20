# -*- coding: utf-8 -*-
"""Expert Community router tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from market.app.routers import api_router


class FakeMarketplace:
    """Minimal marketplace double for expert routes."""

    def __init__(self) -> None:
        self.list_expert_items = AsyncMock()
        self.get_expert_detail = AsyncMock()
        self.publish_expert = AsyncMock()
        self.restore_expert_version = AsyncMock()
        self.unpublish_expert = AsyncMock()
        self._get_expert_version_service = MagicMock()
        self.marketplace_root = Path("/tmp/market")


@pytest.fixture
def test_app() -> FastAPI:
    """Create a FastAPI app with the market router."""
    app = FastAPI()
    app.state.marketplace = FakeMarketplace()
    app.include_router(api_router)
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """Normal user client."""
    return TestClient(test_app)


@pytest.fixture
def manager_client(test_app: FastAPI) -> TestClient:
    """Manager client."""
    return TestClient(test_app, headers={"X-Manager": "true"})


def _expert_item() -> dict[str, object]:
    return {
        "item_id": "expert-1",
        "name": "Community Expert",
        "description": "Expert description",
        "version": "1.0.0",
        "creator_id": "author-a",
        "creator_name": "Author A",
        "category_id": 7,
        "bbk_ids": ["100"],
        "status": "active",
        "created_at": "2026-08-20T10:00:00Z",
        "updated_at": "2026-08-20T10:00:00Z",
    }


def test_list_experts(client: TestClient, test_app: FastAPI) -> None:
    """Browse endpoint should return active expert items."""
    test_app.state.marketplace.list_expert_items.return_value = [_expert_item()]

    response = client.get("/market/experts", headers={"X-Source-Id": "SRC"})

    assert response.status_code == 200
    assert response.json()[0]["name"] == "Community Expert"


def test_get_expert_detail(client: TestClient, test_app: FastAPI) -> None:
    """Detail endpoint should return expert metadata and version history."""
    test_app.state.marketplace.get_expert_detail.return_value = SimpleNamespace(
        **_expert_item(),
        versions=[
            {
                "version_id": "1.0.0",
                "created_at": "2026-08-20T10:00:00Z",
                "created_by": "manager",
                "created_by_name": "Manager",
                "description": "Initial",
                "signature": "abc",
                "is_current": True,
                "is_initial": True,
            },
        ],
        definition={"name": "Community Expert"},
    )

    response = client.get("/market/experts/expert-1", headers={"X-Source-Id": "SRC"})

    assert response.status_code == 200
    assert response.json()["definition"]["name"] == "Community Expert"


def test_list_expert_versions(
    client: TestClient,
    test_app: FastAPI,
    tmp_path: Path,
) -> None:
    """Version history endpoint should return the current version list."""
    test_app.state.marketplace.marketplace_root = tmp_path
    index_dir = tmp_path / "SRC"
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "index.json").write_text(
        """
        {
          "items": [
            {
              "item_id": "expert-1",
              "item_type": "expert",
              "name": "Community Expert",
              "description": "Expert description",
              "version": "1.0.0",
              "creator_id": "author-a",
              "creator_name": "Author A",
              "category_id": 7,
              "bbk_ids": ["100"],
              "status": "active"
            }
          ]
        }
        """.strip(),
        encoding="utf-8",
    )
    test_app.state.marketplace._get_expert_version_service.return_value = SimpleNamespace(
        list_versions=MagicMock(
            return_value={
                "expert_name": "Community Expert",
                "versions": [
                    {
                        "version_id": "1.0.0",
                        "created_at": "2026-08-20T10:00:00Z",
                        "created_by": "manager",
                        "created_by_name": "Manager",
                        "description": "Initial",
                        "signature": "abc",
                        "is_current": True,
                        "is_initial": True,
                    },
                ],
            },
        ),
    )

    response = client.get("/market/experts/expert-1/versions", headers={"X-Source-Id": "SRC"})

    assert response.status_code == 200
    assert response.json()["versions"][0]["version_id"] == "1.0.0"


def test_publish_expert_manager_only(
    manager_client: TestClient,
    test_app: FastAPI,
) -> None:
    """Publish endpoint requires manager header."""
    test_app.state.marketplace.publish_expert.return_value = (
        SimpleNamespace(**_expert_item()),
        False,
    )

    response = manager_client.post(
        "/market/experts",
        headers={"X-Source-Id": "SRC"},
        json={"source_dir": "/tmp/source"},
    )

    assert response.status_code == 201
    assert response.json()["version"] == "1.0.0"


def test_restore_and_unpublish_expert(
    manager_client: TestClient,
    test_app: FastAPI,
) -> None:
    """Restore and unpublish endpoints should be manager-only."""
    test_app.state.marketplace.restore_expert_version.return_value = SimpleNamespace(
        **_expert_item(),
    )
    test_app.state.marketplace.get_expert_detail.return_value = SimpleNamespace(
        **_expert_item(),
        versions=[
            {
                "version_id": "1.0.0",
                "created_at": "2026-08-20T10:00:00Z",
                "created_by": "manager",
                "created_by_name": "Manager",
                "description": "Initial",
                "signature": "abc",
                "is_current": True,
                "is_initial": True,
            },
        ],
        definition={"name": "Community Expert"},
    )
    test_app.state.marketplace.unpublish_expert.return_value = True

    restore_response = manager_client.post(
        "/market/experts/expert-1/versions/1.0.0/restore",
        headers={"X-Source-Id": "SRC"},
    )
    unpublish_response = manager_client.delete(
        "/market/experts/expert-1",
        headers={"X-Source-Id": "SRC"},
    )

    assert restore_response.status_code == 200
    assert unpublish_response.status_code == 200
