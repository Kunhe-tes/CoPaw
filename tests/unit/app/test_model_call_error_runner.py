# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agentscope.message import Msg
from agentscope_runtime.engine.schemas.agent_schemas import (
    AgentRequest,
    Message,
    MessageType,
    RunStatus,
    TextContent,
)
from agentscope_runtime.engine.schemas.exception import AppBaseException

from src.swe.app.runner.model_call_error_detail import (
    MODEL_CALL_FAILED_CODE,
    ModelCallFailedException,
    build_empty_model_output_detail,
)
from src.swe.app.runner.runner import AgentRunner, _QueryPreflight


def _request(**overrides):
    payload = {
        "session_id": "session-1",
        "user_id": "user-1",
        "channel": "console",
        "channel_meta": {},
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _model_status_error(message: str, status_code: int = 429) -> Exception:
    exc = Exception(message)
    exc.status_code = status_code
    return exc


def _setup_runner(monkeypatch) -> AgentRunner:
    runner = AgentRunner(agent_id="test-agent")
    runner.session = SimpleNamespace(mutate_session_state=AsyncMock())
    runner._start_query_trace = AsyncMock(return_value=None)
    runner._end_trace_if_needed = AsyncMock()
    runner._load_query_retry_settings = lambda: (2, 1, 0.0, 0.0)
    runner._handle_query_error = AsyncMock()
    runner._cleanup_query_resources = AsyncMock()
    runner._cleanup_blocked_runtime_start = AsyncMock()
    runner._store_qa_content_if_needed = AsyncMock()
    return runner


async def _collect_until_exception(runner: AgentRunner, request):
    items = []
    with pytest.raises(AppBaseException) as exc_info:
        async for item in runner._stream_query_after_preflight(
            [Msg(name="user", role="user", content="hi")],
            request=request,
            query="hi",
            session_id=request.session_id,
            preflight=_QueryPreflight(),
        ):
            items.append(item)
    return items, exc_info.value


@pytest.mark.asyncio
async def test_final_console_model_failure_raises_model_call_failed(
    monkeypatch,
):
    runner = _setup_runner(monkeypatch)
    attempts = 0

    async def fail_attempt(**_kwargs):
        if _kwargs.get("yield_never"):
            yield None
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise asyncio.TimeoutError("first provider timeout")
        raise _model_status_error("final provider rate limit detail", 429)

    runner._stream_single_query_attempt = fail_attempt

    items, exc = await _collect_until_exception(runner, _request())

    assert exc.code == MODEL_CALL_FAILED_CODE
    assert "final provider rate limit detail" in exc.message
    assert "first provider timeout" not in exc.message
    assert "正在重试" not in exc.message
    runner._handle_query_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_model_failure_preserves_already_streamed_output(monkeypatch):
    runner = _setup_runner(monkeypatch)

    async def fail_after_partial(**_kwargs):
        yield Msg(
            name="Friday",
            role="assistant",
            content="partial answer",
        ), False
        raise _model_status_error("provider failed after partial output", 500)

    runner._load_query_retry_settings = lambda: (1, 0, 0.0, 0.0)
    runner._stream_single_query_attempt = fail_after_partial

    items, exc = await _collect_until_exception(runner, _request())

    assert exc.code == MODEL_CALL_FAILED_CODE
    assert items[0][0].content == "partial answer"


@pytest.mark.asyncio
async def test_non_model_failures_keep_existing_error_path(monkeypatch):
    runner = _setup_runner(monkeypatch)

    async def fail_with_storage_error(**_kwargs):
        if _kwargs.get("yield_never"):
            yield None
        raise ValueError("session storage exploded")

    runner._load_query_retry_settings = lambda: (1, 0, 0.0, 0.0)
    runner._stream_single_query_attempt = fail_with_storage_error

    with pytest.raises(ValueError):
        async for _ in runner._stream_query_after_preflight(
            [Msg(name="user", role="user", content="hi")],
            request=_request(),
            query="hi",
            session_id="session-1",
            preflight=_QueryPreflight(),
        ):
            pass

    runner._handle_query_error.assert_awaited_once()


@pytest.mark.asyncio
async def test_model_call_failure_persists_user_visible_detail(monkeypatch):
    runner = _setup_runner(monkeypatch)

    async def fail_with_model_error(**_kwargs):
        if _kwargs.get("yield_never"):
            yield None
        raise _model_status_error("provider detail for history", 429)

    runner._load_query_retry_settings = lambda: (1, 0, 0.0, 0.0)
    runner._stream_single_query_attempt = fail_with_model_error

    _, exc = await _collect_until_exception(runner, _request())

    assert exc.code == MODEL_CALL_FAILED_CODE
    runner.session.mutate_session_state.assert_awaited_once()
    kwargs = runner.session.mutate_session_state.await_args.kwargs
    assert kwargs["session_id"] == "session-1"
    assert kwargs["user_id"] == "user-1"
    state = kwargs["mutator"]({})
    records = state["model_call_failed_messages"]
    assert len(records) == 1
    assert records[0]["type"] == "error"
    assert records[0]["code"] == MODEL_CALL_FAILED_CODE
    assert "provider detail for history" in records[0]["message"]


@pytest.mark.asyncio
async def test_history_persistence_failure_does_not_hide_stream_detail(
    monkeypatch,
):
    runner = _setup_runner(monkeypatch)
    runner.session.mutate_session_state.side_effect = RuntimeError(
        "disk write failed",
    )

    async def fail_with_model_error(**_kwargs):
        if _kwargs.get("yield_never"):
            yield None
        raise _model_status_error("provider detail survives", 429)

    runner._load_query_retry_settings = lambda: (1, 0, 0.0, 0.0)
    runner._stream_single_query_attempt = fail_with_model_error

    _, exc = await _collect_until_exception(runner, _request())

    assert exc.code == MODEL_CALL_FAILED_CODE
    assert "provider detail survives" in exc.message


@pytest.mark.asyncio
async def test_stream_query_emits_terminal_failed_model_call_response():
    runner = AgentRunner(agent_id="test-agent")
    await runner.start()

    async def fail_with_model_call_detail(**_kwargs):
        if _kwargs.get("yield_never"):
            yield None
        raise ModelCallFailedException(
            build_empty_model_output_detail("empty output diagnostic"),
        )

    runner.query_handler = fail_with_model_call_detail
    request = AgentRequest(
        input=[
            Message(
                type=MessageType.MESSAGE,
                role="user",
                content=[TextContent(text="hi")],
            ),
        ],
        session_id="session-1",
        user_id="user-1",
    )

    events = [event async for event in runner.stream_query(request)]

    terminal = events[-1]
    assert terminal.object == "response"
    assert terminal.status == RunStatus.Failed
    assert terminal.error is not None
    assert terminal.error.code == MODEL_CALL_FAILED_CODE
    assert "empty output diagnostic" in terminal.error.message
