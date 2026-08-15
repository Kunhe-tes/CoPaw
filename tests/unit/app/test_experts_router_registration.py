# -*- coding: utf-8 -*-
"""Regression coverage for the root Experts API route."""

from swe.app.routers import _build_router


def test_experts_router_is_registered_in_root_api_router() -> None:
    """Console requests use /api/experts with the selected-Agent header."""
    assert any(route.path == "/experts" for route in _build_router().routes)
