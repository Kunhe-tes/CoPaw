# -*- coding: utf-8 -*-
"""HTTP contract tests for Default Agent Profile Hook management."""

from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from swe.app.hook_management import HookConfigurationSnapshot
from swe.app.routers import hook_management
from swe.config.context import encode_scope_id


class _FakeService:
    def __init__(self) -> None:
        self.snapshot = HookConfigurationSnapshot(
            hooks={"enabled": False, "events": {}},
            revision="revision-1",
        )
        self.saved: dict | None = None

    def get_configuration(self) -> HookConfigurationSnapshot:
        return self.snapshot

    def save_configuration(self, *, hooks, expected_revision, actor):
        self.saved = {
            "hooks": hooks,
            "expected_revision": expected_revision,
            "actor": actor,
        }
        self.snapshot = HookConfigurationSnapshot(
            hooks=hooks,
            revision="revision-2",
        )
        return self.snapshot


def _client(monkeypatch) -> tuple[TestClient, _FakeService, Mock]:
    service = _FakeService()
    reload = Mock()
    monkeypatch.setattr(
        hook_management,
        "_service_for_request",
        lambda request: service,
    )
    monkeypatch.setattr(hook_management, "schedule_agent_reload", reload)
    app = FastAPI()

    @app.middleware("http")
    async def _request_identity(request: Request, call_next):
        request.state.tenant_id = "tenant-a"
        request.state.source_id = "source-a"
        request.state.scope_id = encode_scope_id("tenant-a", "source-a")
        request.state.user_id = "user-a"
        return await call_next(request)

    app.include_router(hook_management.router)
    return TestClient(app), service, reload


def test_put_configuration_reloads_default_agent_after_save(
    monkeypatch,
) -> None:
    client, service, reload = _client(monkeypatch)

    response = client.put(
        "/hook-management/configuration",
        headers={"If-Match": "revision-1"},
        json={"hooks": {"enabled": True, "events": {}}},
    )

    assert response.status_code == 200
    assert service.saved is not None
    assert reload.call_args.args[1] == "default"
    assert reload.call_args.kwargs["tenant_id"] == encode_scope_id(
        "tenant-a",
        "source-a",
    )


def test_manual_test_requires_real_execution_confirmation(monkeypatch) -> None:
    client, _, _ = _client(monkeypatch)

    response = client.post(
        "/hook-management/manual-test",
        json={
            "confirm_real_execution": False,
            "handler": {"id": "command", "type": "command", "argv": ["echo"]},
            "context": {
                "session_id": "test",
                "transcript_path": "",
                "cwd": ".",
                "hook_event_name": "PreToolUse",
                "tenant_id": "tenant-a",
                "effective_tenant_id": "tenant-a",
                "user_id": "user-a",
                "agent_id": "default",
                "channel": "test",
            },
        },
    )

    assert response.status_code == 400
