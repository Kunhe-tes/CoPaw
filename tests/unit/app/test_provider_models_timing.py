# -*- coding: utf-8 -*-
"""Tests for provider models timing middleware."""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from swe.app.middleware import provider_models_timing


def test_provider_models_request_done_logs_threadpool_wait(monkeypatch):
    """Request summary includes provider dependency threadpool wait timing."""
    logged_messages = []
    app = FastAPI()
    app.add_middleware(provider_models_timing.ProviderModelsTimingMiddleware)
    monkeypatch.setattr(
        provider_models_timing.logger,
        "info",
        lambda message, *args, **kwargs: logged_messages.append(
            message % args,
        ),
    )

    @app.get("/api/models")
    async def list_models(request: Request):
        request.state.provider_manager_dependency_ms = 124
        request.state.provider_manager_dependency_ensure_ms = 2
        request.state.provider_manager_dependency_get_instance_ms = 3
        request.state.provider_manager_dependency_threadpool_wait_ms = 119
        request.state.provider_manager_dependency_cache_hit_before = False
        request.state.provider_models_handler_ms = 4
        return []

    response = TestClient(app).get("/api/models")

    assert response.status_code == 200
    assert any(
        "provider_models_request_done" in message
        and "dependency_threadpool_wait_ms=119" in message
        for message in logged_messages
    )
