# -*- coding: utf-8 -*-
"""Tests for Runtime Diagnostic application integration."""

from __future__ import annotations

import inspect

from swe.app.middleware.sse_diagnostic import SSEDiagnosticMiddleware
from swe.app.middleware.liveness_probe import LivenessProbeMiddleware
from swe.app.runtime_diagnostic import RuntimeDiagnosticManager


def test_app_exposes_runtime_diagnostic_manager() -> None:
    from swe.app._app import app, runtime_diagnostic_manager

    assert isinstance(runtime_diagnostic_manager, RuntimeDiagnosticManager)
    assert app.state.runtime_diagnostic_manager is runtime_diagnostic_manager


def test_app_installs_sse_diagnostic_middleware_with_shared_manager() -> None:
    from swe.app._app import app, runtime_diagnostic_manager

    middleware = next(
        item
        for item in app.user_middleware
        if item.cls is SSEDiagnosticMiddleware
    )

    assert middleware.kwargs["manager"] is runtime_diagnostic_manager


def test_app_installs_liveness_probe_as_outermost_middleware() -> None:
    from swe.app._app import app

    assert app.user_middleware[0].cls is LivenessProbeMiddleware


def test_lifespan_starts_and_stops_runtime_diagnostic_manager() -> None:
    from swe.app._app import lifespan

    source = inspect.getsource(lifespan)

    assert "await runtime_diagnostic_manager.start()" in source
    assert "await runtime_diagnostic_manager.stop()" in source
