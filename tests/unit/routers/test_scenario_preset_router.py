# -*- coding: utf-8 -*-
"""Scenario catalog HTTP access boundaries."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from swe.app.scenario_preset import router as scenario_router_module
from swe.app.scenario_preset.router import router


def test_admin_catalog_requires_manager_or_admin_role(monkeypatch) -> None:
    """Untrusted headers cannot grant catalog write access outside known roles."""
    app = FastAPI()
    app.include_router(router)
    monkeypatch.setattr(
        scenario_router_module,
        "get_service",
        lambda: None,
    )
    client = TestClient(app)

    response = client.get(
        "/scenario-presets/admin/catalog",
        headers={"X-Source-Id": "source-a", "X-User-Role": "user"},
    )

    assert response.status_code == 403
