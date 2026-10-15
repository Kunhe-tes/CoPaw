# -*- coding: utf-8 -*-
"""Request Agent configuration must not read storage on the event loop."""

import threading
from contextvars import ContextVar
from types import SimpleNamespace

import pytest

from swe.app import agent_context
from swe.config import config


@pytest.mark.asyncio
async def test_request_agent_config_load_runs_in_worker(monkeypatch):
    loop_thread = threading.get_ident()
    scope = ContextVar("config_request_scope", default=None)
    token = scope.set("source-a")
    workspace = SimpleNamespace(agent_id="agent-a", tenant_id="tenant-a")
    expected = object()
    seen = []

    async def resolve(*_args, **_kwargs):
        return workspace

    def load(agent_id, *, tenant_id):
        seen.append((threading.get_ident(), scope.get(), agent_id, tenant_id))
        return expected

    monkeypatch.setattr(agent_context, "get_agent_for_request", resolve)
    monkeypatch.setattr(config, "load_agent_config", load)
    try:
        result = await agent_context.get_agent_and_config_for_request(object())
    finally:
        scope.reset(token)
    assert result == (workspace, expected)
    assert seen == [(seen[0][0], "source-a", "agent-a", "tenant-a")]
    assert seen[0][0] != loop_thread
