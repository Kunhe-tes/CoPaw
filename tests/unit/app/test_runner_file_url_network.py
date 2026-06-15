# -*- coding: utf-8 -*-
"""验证 Runner 会按请求绑定静态文件 URL 网络上下文。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.app.runner.runner import AgentRunner
from swe.config.context import get_current_file_url_network


def _fake_agent_config():
    return SimpleNamespace(
        mcp=None,
        hooks=SimpleNamespace(enabled=False),
        running=SimpleNamespace(
            suggestions=SimpleNamespace(
                enabled=False,
            ),
        ),
    )


def _request(**extra):
    payload = {
        "session_id": "session-1",
        "user_id": "user-1",
        "channel": "console",
        "channel_meta": {},
    }
    payload.update(extra)
    return SimpleNamespace(**payload)


async def _run_query(monkeypatch, request):
    runner = AgentRunner(agent_id="test-agent")
    runner.session = SimpleNamespace(
        load_session_state=AsyncMock(),
        save_session_state=AsyncMock(),
    )
    setattr(runner, "_chat_manager", None)

    captured: dict[str, str] = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            del kwargs

        async def register_mcp_clients(self):
            return

        def set_console_output_enabled(self, enabled=False):
            del enabled

        def rebuild_sys_prompt(self):
            return

        async def __call__(self, _msgs):
            captured["network"] = get_current_file_url_network()
            return []

    async def fake_stream_printing_messages(*, agents, coroutine_task):
        del agents
        await coroutine_task
        for item in ():
            yield item

    monkeypatch.setattr(
        "swe.app.runner.runner.load_agent_config",
        lambda *args, **kwargs: _fake_agent_config(),
    )
    monkeypatch.setattr(
        "swe.app.runner.runner._build_and_connect_mcp_clients",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr("swe.app.runner.runner.SWEAgent", FakeAgent)
    monkeypatch.setattr(
        "swe.app.runner.runner.stream_printing_messages",
        fake_stream_printing_messages,
    )
    monkeypatch.setattr(
        "swe.app.runner.runner.build_env_context",
        lambda **kwargs: "base context",
    )
    monkeypatch.setattr(
        "swe.app.runner.runner._cleanup_mcp_clients",
        AsyncMock(),
    )

    msgs = [SimpleNamespace(get_text_content=lambda: "hello")]
    async for _item in runner.query_handler(msgs, request=request):
        pass

    return captured["network"]


@pytest.mark.asyncio
async def test_query_handler_binds_direct_file_url_network(monkeypatch):
    network = await _run_query(
        monkeypatch,
        _request(file_url_network="business"),
    )

    assert network == "business"
    assert get_current_file_url_network() == "office"


@pytest.mark.asyncio
async def test_query_handler_binds_channel_meta_file_url_network(monkeypatch):
    network = await _run_query(
        monkeypatch,
        _request(channel_meta={"file_url_network": "business"}),
    )

    assert network == "business"
    assert get_current_file_url_network() == "office"


@pytest.mark.asyncio
async def test_query_handler_falls_back_for_invalid_file_url_network(
    monkeypatch,
):
    network = await _run_query(
        monkeypatch,
        _request(file_url_network="unknown"),
    )

    assert network == "office"
    assert get_current_file_url_network() == "office"
