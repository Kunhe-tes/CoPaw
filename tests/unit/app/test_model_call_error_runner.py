# -*- coding: utf-8 -*-

from __future__ import annotations

import ast
import asyncio
import inspect
import textwrap
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

_CONTROL_NESTING_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
)


def _max_control_nesting_by_line(callable_obj) -> dict[int, int]:
    source_lines, start_line = inspect.getsourcelines(callable_obj)
    tree = ast.parse(textwrap.dedent("".join(source_lines)))
    max_by_line: dict[int, int] = {}

    def _visit(node: ast.AST, depth: int) -> None:
        if isinstance(node, _CONTROL_NESTING_NODES):
            depth += 1
            lineno = start_line + node.lineno - 1
            max_by_line[lineno] = max(depth, max_by_line.get(lineno, 0))

        for child in ast.iter_child_nodes(node):
            _visit(child, depth)

    _visit(tree, 0)
    return max_by_line


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


def _runtime_status_error(message: str, status_code: int = 500) -> Exception:
    exc = Exception(message)
    exc.status_code = status_code
    return exc


def _setup_runner(monkeypatch) -> AgentRunner:
    runner = AgentRunner(agent_id="test-agent")
    runner.session = SimpleNamespace(mutate_session_state=AsyncMock())
    runner._start_query_trace = AsyncMock(return_value=None)
    runner._end_trace_if_needed = AsyncMock()

    def load_query_retry_settings(_agent_config=None):
        return (2, 1, 0.0, 0.0)

    runner._load_query_retry_settings = load_query_retry_settings
    runner._handle_query_error = AsyncMock()
    runner._cleanup_query_resources = AsyncMock()
    runner._cleanup_blocked_runtime_start = AsyncMock()
    runner._store_qa_content_if_needed = AsyncMock()
    return runner


def test_stream_query_after_preflight_control_nesting_stays_within_limit():
    nesting_by_line = _max_control_nesting_by_line(
        AgentRunner._stream_query_after_preflight,
    )
    deepest_line, deepest_depth = max(
        nesting_by_line.items(),
        key=lambda item: item[1],
    )

    assert deepest_depth <= 5, (
        "_stream_query_after_preflight nests control flow deeper than 5 "
        f"levels at runner.py:{deepest_line}"
    )


def test_load_query_retry_settings_applies_current_source_override(
    monkeypatch,
):
    from src.swe.app.source_system_config.models import (
        EffectiveSourceSystemConfig,
        SourceSystemConfig,
    )
    from src.swe.app.source_system_config.runtime import (
        bind_source_system_config,
    )

    runner = AgentRunner(agent_id="test-agent")
    runner.tenant_id = "tenant-a"
    agent_config = SimpleNamespace(
        running=SimpleNamespace(
            query_retry=SimpleNamespace(
                enabled=False,
                max_retries=5,
                backoff_base=1.5,
                backoff_cap=12.0,
            ),
        ),
    )
    monkeypatch.setattr(
        "src.swe.app.runner.runner.load_agent_config",
        lambda agent_id, tenant_id=None: agent_config,
    )
    effective = EffectiveSourceSystemConfig(
        source_id="portal",
        config=SourceSystemConfig.model_validate({}),
        raw_config=SourceSystemConfig.model_validate(
            {
                "query_retry": {
                    "enabled": True,
                    "max_retries": 2,
                },
            },
        ),
        version=3,
    )

    with bind_source_system_config(effective):
        assert runner._load_query_retry_settings() == (3, 2, 1.5, 12.0)


def test_load_query_retry_settings_uses_supplied_config_snapshot(
    monkeypatch,
):
    runner = AgentRunner(agent_id="test-agent")
    runner.tenant_id = "tenant-a"
    agent_config = SimpleNamespace(
        running=SimpleNamespace(
            query_retry=SimpleNamespace(
                enabled=True,
                max_retries=2,
                backoff_base=0.5,
                backoff_cap=3.0,
            ),
        ),
    )

    def fail_load_agent_config(*args, **kwargs):
        del args, kwargs
        raise AssertionError("retry settings should use the preflight config")

    monkeypatch.setattr(
        "src.swe.app.runner.runner.load_agent_config",
        fail_load_agent_config,
    )

    assert runner._load_query_retry_settings(agent_config) == (
        3,
        2,
        0.5,
        3.0,
    )


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
async def test_unmarked_transport_failures_keep_existing_error_path(
    monkeypatch,
):
    failures = [
        asyncio.TimeoutError("tool call timed out"),
        ConnectionResetError("tool socket reset"),
        _runtime_status_error("hook callback failed", 500),
    ]

    for failure in failures:
        runner = _setup_runner(monkeypatch)

        async def fail_with_runtime_error(
            *_args,
            failure_to_raise=failure,
            **_kwargs,
        ):
            if _kwargs.get("yield_never"):
                yield None
            raise failure_to_raise

        runner._load_query_retry_settings = lambda: (1, 0, 0.0, 0.0)
        runner._stream_single_query_attempt = fail_with_runtime_error

        with pytest.raises(type(failure)):
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
