# -*- coding: utf-8 -*-
"""验证 Runner 会把系统提示词注入追加到运行上下文。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.app.runner.runner import AgentRunner
from swe.app.source_system_config.models import (
    EffectiveSourceSystemConfig,
    SourceSystemConfig,
)
from swe.app.source_system_config.runtime import bind_source_system_config


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
            captured["env_context"] = kwargs["env_context"]

        async def register_mcp_clients(self):
            return

        def set_console_output_enabled(self, enabled=False):
            del enabled

        def rebuild_sys_prompt(self):
            return

        async def __call__(self, _msgs):
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
    results = []
    async for item in runner.query_handler(msgs, request=request):
        results.append(item)

    assert not results
    return captured["env_context"]


@pytest.mark.asyncio
async def test_query_handler_appends_source_system_prompt_injections(
    monkeypatch,
) -> None:
    config = EffectiveSourceSystemConfig(
        source_id="portal",
        config=SourceSystemConfig.model_validate(
            {"system_prompt_injections": ["source prompt"]},
        ),
    )

    with bind_source_system_config(config):
        env_context = await _run_query(monkeypatch, _request())

    assert "[System prompt injections]" in env_context
    assert "source prompt" in env_context


@pytest.mark.asyncio
async def test_query_handler_appends_request_system_prompt_injections(
    monkeypatch,
) -> None:
    env_context = await _run_query(
        monkeypatch,
        _request(system_prompt_injections=["request prompt"]),
    )

    assert "[System prompt injections]" in env_context
    assert "request prompt" in env_context


@pytest.mark.asyncio
async def test_query_handler_merges_system_prompt_injections_in_stable_order(
    monkeypatch,
) -> None:
    config = EffectiveSourceSystemConfig(
        source_id="portal",
        config=SourceSystemConfig.model_validate(
            {"system_prompt_injections": ["shared", "source only"]},
        ),
    )
    request = _request(
        channel_meta={
            "system_prompt_injections": [" shared ", "request only"],
        },
    )

    with bind_source_system_config(config):
        env_context = await _run_query(monkeypatch, request)

    assert env_context.count("shared") == 1
    assert (
        env_context.index("shared")
        < env_context.index("source only")
        < env_context.index("request only")
    )


@pytest.mark.asyncio
async def test_query_handler_omits_empty_system_prompt_injection_block(
    monkeypatch,
) -> None:
    env_context = await _run_query(monkeypatch, _request())

    assert "[System prompt injections]" not in env_context
