# -*- coding: utf-8 -*-
"""Regression coverage for the root Experts API route."""

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from swe.app.routers import _build_router
from swe.app.routers.experts import _repository


def test_experts_router_is_registered_in_root_api_router() -> None:
    """Console requests use /api/experts with the selected-Agent header."""
    assert any(route.path == "/experts" for route in _build_router().routes)


@pytest.mark.asyncio
async def test_experts_repository_uses_active_agent_resolution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def resolve_active_agent(_request):
        return (
            SimpleNamespace(
                agent_id="active-agent",
                tenant_id="tenant-1",
                workspace_dir=str(tmp_path),
            ),
            SimpleNamespace(),
        )

    agent_context = importlib.import_module("swe.app.agent_context")
    monkeypatch.setattr(
        agent_context,
        "get_agent_and_config_for_request",
        resolve_active_agent,
    )
    request = Request({"type": "http", "headers": []})

    repository = await _repository(request)

    assert (
        repository._root == tmp_path / "agents"
    )  # pylint: disable=protected-access
    assert (
        repository._owner_scope == "tenant-1/active-agent"
    )  # pylint: disable=protected-access
