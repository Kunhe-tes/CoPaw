# -*- coding: utf-8 -*-
"""Characterize externally visible boundaries in the AgentRunner query path."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agentscope.message import Msg

from swe.agents.hook_runtime.models import (
    HookConfig,
    HookDecision,
    HookEventName,
    HookMatcherGroupConfig,
    CommandHookHandlerConfig,
    HookSessionOverlay,
    MergedHookResult,
)
from swe.app.runner.runner import (
    AgentRunner,
    _QueryPreflight,
    _QueryRuntime,
    _QueryRuntimeInputs,
    _RuntimeStartResult,
)


def _request(**overrides):
    payload = {
        "session_id": "session-1",
        "user_id": "user-1",
        "channel": "console",
        "channel_meta": {},
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _agent_config() -> SimpleNamespace:
    return SimpleNamespace(
        id="test-agent",
        mcp=None,
        hooks=HookConfig(),
        running=SimpleNamespace(),
    )


def _blocked_msg(text: str) -> Msg:
    return Msg(name="Friday", role="assistant", content=text)


@pytest.mark.asyncio
async def test_user_prompt_block_terminates_before_runtime_preparation(
    monkeypatch,
    tmp_path,
) -> None:
    runner = AgentRunner(agent_id="test-agent", workspace_dir=tmp_path)
    runner.session = SimpleNamespace(
        get_session_state_dict=AsyncMock(return_value={}),
        mutate_session_state=AsyncMock(return_value={}),
    )
    runner._chat_manager = None
    tenant_hooks = HookConfig(
        enabled=True,
        events={
            HookEventName.USER_PROMPT_SUBMIT: [
                HookMatcherGroupConfig(
                    hooks=[
                        CommandHookHandlerConfig(
                            id="blocker",
                            command="unused",
                        ),
                    ],
                ),
            ],
        },
    )
    monkeypatch.setattr(
        "swe.app.runner.runner.load_agent_config",
        lambda *_args, **_kwargs: _agent_config(),
    )
    monkeypatch.setattr(
        "swe.app.runner.runner._load_tenant_hook_config",
        lambda *_args, **_kwargs: tenant_hooks,
    )
    monkeypatch.setattr(
        "swe.app.runner.runner._emit_runner_hook",
        AsyncMock(
            return_value=MergedHookResult(
                decision=HookDecision.BLOCK,
                reason="prompt blocked",
            ),
        ),
    )
    prepare_runtime = AsyncMock()
    runner._prepare_query_runtime = prepare_runtime

    outputs = [
        item
        async for item in runner.query_handler(
            [Msg(name="user", role="user", content="hello")],
            request=_request(),
        )
    ]

    assert [(msg.get_text_content(), last) for msg, last in outputs] == [
        ("prompt blocked", True),
    ]
    prepare_runtime.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("approval_consumed", [False, True])
async def test_command_dispatch_requires_unconsumed_approval(
    monkeypatch,
    tmp_path,
    approval_consumed: bool,
) -> None:
    runner = AgentRunner(agent_id="test-agent", workspace_dir=tmp_path)
    runner._prepare_query_preflight = AsyncMock(
        return_value=_QueryPreflight(
            approval_consumed=approval_consumed,
        ),
    )
    command_calls: list[str] = []

    async def command_path(*_args):
        command_calls.append("command")
        yield _blocked_msg("command response"), True

    async def normal_path(*_args, **_kwargs):
        yield _blocked_msg("normal response"), True

    monkeypatch.setattr(
        "swe.app.runner.runner.run_command_path",
        command_path,
    )
    runner._stream_query_after_preflight = normal_path
    runner._start_query_trace = AsyncMock(return_value=None)
    runner._end_trace_if_needed = AsyncMock()

    outputs = [
        item
        async for item in runner.query_handler(
            [Msg(name="user", role="user", content="/history")],
            request=_request(),
        )
    ]

    expected = "normal response" if approval_consumed else "command response"
    assert outputs[-1][0].get_text_content() == expected
    assert command_calls == ([] if approval_consumed else ["command"])


@pytest.mark.asyncio
async def test_runtime_resources_resolve_chat_before_mcp_setup(
    monkeypatch,
    tmp_path,
) -> None:
    runner = AgentRunner(agent_id="test-agent", workspace_dir=tmp_path)
    chat = SimpleNamespace(id="chat-1")
    events: list[object] = []

    async def get_or_create_chat(*_args, **_kwargs):
        events.append("chat")
        return chat

    def build_clients(*_args, **kwargs):
        events.append(("mcp", kwargs["chat_id"]))
        return []

    runner._chat_manager = SimpleNamespace(
        get_or_create_chat=get_or_create_chat,
    )
    runner._emit_session_start_hook = AsyncMock(return_value=("base", None))
    monkeypatch.setattr(
        "swe.app.runner.runner._build_lazy_mcp_clients",
        build_clients,
    )
    monkeypatch.setattr(
        "swe.app.runner.context_references.build_context_reference_directives",
        AsyncMock(return_value=[]),
    )

    inputs = _QueryRuntimeInputs(
        session_id="session-1",
        user_id="user-1",
        channel="console",
        skip_history=False,
        agent_config=_agent_config(),
        tenant_hooks=HookConfig(),
        hook_overlay=HookSessionOverlay(),
        env_context="base",
        selected_context_directives=[],
        auth_token=None,
        passthrough_headers={},
    )
    clients: list[object] = []

    resources, block_result = await runner._start_query_runtime_resources(
        request=_request(),
        msgs=[Msg(name="user", role="user", content="hello")],
        inputs=inputs,
        mcp_clients=clients,
    )

    assert resources.chat is chat
    assert block_result is None
    assert events == ["chat", ("mcp", "chat-1")]


@pytest.mark.asyncio
async def test_session_start_block_cleans_previously_created_chat_and_mcp(
    monkeypatch,
    tmp_path,
) -> None:
    runner = AgentRunner(agent_id="test-agent", workspace_dir=tmp_path)
    runner._prepare_query_preflight = AsyncMock(return_value=_QueryPreflight())
    chat = SimpleNamespace(id="chat-1")
    mcp_client = object()
    runner._prepare_query_runtime = AsyncMock(
        return_value=_RuntimeStartResult(
            block_response=_blocked_msg("session start blocked"),
            blocked_chat=chat,
            blocked_mcp_clients=[mcp_client],
            blocked_session_id="session-1",
        ),
    )
    events: list[object] = []

    async def update_chat(updated_chat):
        events.append(("chat", updated_chat))

    async def cleanup_mcp(clients):
        events.append(("mcp", clients))

    runner._chat_manager = SimpleNamespace(update_chat=update_chat)
    monkeypatch.setattr(
        "swe.app.runner.runner._cleanup_mcp_clients",
        cleanup_mcp,
    )
    runner._start_query_trace = AsyncMock(return_value=None)
    runner._end_trace_if_needed = AsyncMock()
    runner._load_query_retry_settings = lambda *_args: (1, 0, 0.0, 0.0)
    runner._store_qa_content_if_needed = AsyncMock()

    outputs = [
        item
        async for item in runner.query_handler(
            [Msg(name="user", role="user", content="hello")],
            request=_request(),
        )
    ]

    assert outputs[-1][0].get_text_content() == "session start blocked"
    assert events == [("chat", chat), ("mcp", [mcp_client])]


@pytest.mark.asyncio
async def test_retry_notice_is_streamed_before_the_next_attempt(
    tmp_path,
) -> None:
    runner = AgentRunner(agent_id="test-agent", workspace_dir=tmp_path)
    runner._start_query_trace = AsyncMock(return_value=None)
    runner._end_trace_if_needed = AsyncMock()
    runner._load_query_retry_settings = lambda *_args: (2, 1, 0.0, 0.0)
    runner._cleanup_query_resources = AsyncMock()
    runner._cleanup_blocked_runtime_start = AsyncMock()
    runner._store_qa_content_if_needed = AsyncMock()
    attempts: list[str] = []

    async def attempt(*_args, **_kwargs):
        attempts.append(f"attempt-{len(attempts) + 1}")
        if len(attempts) == 1:
            error = RuntimeError("rate limiter unavailable")
            error.status_code = 429
            raise error
        yield _blocked_msg("second attempt response"), True

    runner._stream_single_query_attempt = attempt

    outputs = [
        item
        async for item in runner._stream_query_after_preflight(
            [Msg(name="user", role="user", content="hello")],
            request=_request(),
            query="hello",
            session_id="session-1",
            preflight=_QueryPreflight(),
        )
    ]

    assert [msg.get_text_content() for msg, _last in outputs] == [
        "请求频率超限，正在重试 (1/1)...",
        "正在重试 (1/1)...",
        "second attempt response",
    ]
    assert attempts == ["attempt-1", "attempt-2"]


@pytest.mark.asyncio
async def test_final_cleanup_dispatches_resources_in_declared_order(
    monkeypatch,
    tmp_path,
) -> None:
    runner = AgentRunner(agent_id="test-agent", workspace_dir=tmp_path)
    events: list[str] = []

    async def save_job_session_state(*_args, **_kwargs):
        events.append("session save")

    async def update_chat(*_args, **_kwargs):
        events.append("chat update")

    async def cleanup_mcp(*_args, **_kwargs):
        events.append("mcp close")

    async def detector_shutdown():
        events.append("detector shutdown")

    runner.save_job_session_state = save_job_session_state
    runner._chat_manager = SimpleNamespace(update_chat=update_chat)
    monkeypatch.setattr(
        "swe.app.runner.runner._cleanup_mcp_clients",
        cleanup_mcp,
    )
    runtime = _QueryRuntime(
        agent=SimpleNamespace(),
        agent_config=_agent_config(),
        tenant_hooks=HookConfig(),
        hook_overlay=HookSessionOverlay(),
        chat=SimpleNamespace(id="chat-1"),
        session_skill_detector=SimpleNamespace(
            on_reasoning_end=detector_shutdown,
        ),
        mcp_clients=[object()],
        session_id="session-1",
        user_id="user-1",
        channel="console",
        skip_history=False,
        pending_confirmed_skill_snapshots={},
    )

    await runner._cleanup_query_resources(
        runtime=runtime,
        session_state_loaded=True,
        session_id="session-1",
    )

    assert events == [
        "session save",
        "chat update",
        "mcp close",
        "detector shutdown",
    ]
