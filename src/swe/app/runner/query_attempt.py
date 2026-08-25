# -*- coding: utf-8 -*-
# flake8: noqa: E704
# pylint: disable=too-many-statements
"""Retry and per-attempt orchestration for runner query execution."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Protocol

from agentscope.message import Msg, TextBlock
from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest
from trace_sdk import global_tracer

from ...config.context import (
    reset_current_file_url_network,
    set_current_file_url_network,
)
from ...runtime_invocation_claims import runtime_invocation_claims_context
from ...tracing.models import TraceStatus
from ..agent_context import set_current_agent_id
from .query_contracts import _QueryPreflight, _QueryRuntime
from .retry_classifier import is_query_retryable

logger = logging.getLogger(__name__)


class QueryAttemptOwner(Protocol):
    """Runner operations needed to execute an attempt without importing it."""

    agent_id: str
    tenant_id: str | None

    async def _start_query_trace(
        self,
        request: AgentRequest,
        msgs: list[Any],
    ) -> str | None: ...

    def _load_query_retry_settings(
        self,
        agent_config: Any | None = None,
    ) -> tuple[int, int, float, float]: ...

    def _new_query_turn_outcome(self) -> Any: ...

    def _new_retry_state(self) -> Any: ...

    def _new_query_attempt_input(self, **kwargs: Any) -> Any: ...

    def _new_query_attempt_state(self) -> Any: ...

    def _request_file_url_network(self, request: AgentRequest) -> Any: ...

    def _build_skill_freshness_notice_msg(self, text: str) -> Msg: ...

    async def _stream_retry_backoff_notice(
        self,
        **kwargs: Any,
    ) -> AsyncGenerator[tuple[Msg, bool], None]: ...

    async def _stream_single_query_attempt(
        self,
        **kwargs: Any,
    ) -> AsyncGenerator[tuple[Msg, bool], None]: ...

    def _should_retry(
        self,
        retry_attempt: int,
        max_retry_attempts: int,
        exc: BaseException,
    ) -> bool: ...

    async def _raise_console_model_call_failed_if_needed(
        self,
        **kwargs: Any,
    ) -> None: ...

    async def _handle_query_error(self, **kwargs: Any) -> None: ...

    async def _stream_retryable_query_error(
        self,
        **kwargs: Any,
    ) -> AsyncGenerator[tuple[Msg, bool], None]: ...

    async def _handle_query_cancelled(self, **kwargs: Any) -> None: ...

    async def _cleanup_query_resources(self, **kwargs: Any) -> None: ...

    async def _cleanup_blocked_runtime_start(
        self,
        runtime_start: Any,
    ) -> None: ...

    async def _store_qa_content_if_needed(self, **kwargs: Any) -> None: ...

    async def _prepare_query_runtime(self, **kwargs: Any) -> Any: ...

    async def _end_trace_if_needed(
        self,
        trace_id: str | None,
        status: TraceStatus,
        error: str | None = None,
    ) -> None: ...

    def _rebind_trace_skill_detector_if_needed(
        self,
        **kwargs: Any,
    ) -> None: ...

    async def get_state_loaded(self, *args: Any) -> bool: ...

    async def _refresh_session_skill_freshness(self, **kwargs: Any) -> Any: ...

    async def _build_turn_plan(self, **kwargs: Any) -> Any: ...

    async def _stream_completion_lifecycle(
        self,
        **kwargs: Any,
    ) -> AsyncGenerator[tuple[Msg, bool], None]: ...

    def _schedule_session_title_task(self, **kwargs: Any) -> None: ...

    async def _build_skill_snapshot_to_persist(
        self,
        **kwargs: Any,
    ) -> dict[str, dict[str, Any]] | None: ...

    async def _finish_blocked_query_attempt(self, **kwargs: Any) -> None: ...

    async def _complete_successful_query_attempt(
        self,
        **kwargs: Any,
    ) -> None: ...

    async def save_job_session_state(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None: ...


def extract_retry_config(agent_config: Any) -> tuple[bool, int, float, float]:
    """Extract retry settings with the runner's historic defaults."""
    query_retry_config = getattr(
        getattr(agent_config, "running", None),
        "query_retry",
        None,
    )
    if not query_retry_config:
        return False, 0, 2.0, 30.0
    return (
        getattr(query_retry_config, "enabled", False),
        getattr(query_retry_config, "max_retries", 0),
        getattr(query_retry_config, "backoff_base", 2.0),
        getattr(query_retry_config, "backoff_cap", 30.0),
    )


def compute_retry_backoff(
    retry_attempt: int,
    backoff_cap: float,
    backoff_base: float,
) -> float:
    return min(backoff_cap, backoff_base * (2 ** (retry_attempt - 1)))


def should_retry(
    retry_attempt: int,
    max_retry_attempts: int,
    exc: BaseException,
) -> bool:
    return retry_attempt < max_retry_attempts - 1 and is_query_retryable(exc)


def summarize_retry_error(exc: BaseException) -> str:
    for candidate in (
        exc,
        getattr(exc, "__cause__", None),
        getattr(exc, "__context__", None),
    ):
        if candidate is None:
            continue
        status_code = getattr(candidate, "status_code", None)
        if status_code is not None:
            return {
                429: "请求频率超限",
                432: "输入Token数已达上限",
                433: "服务过载",
                500: "服务内部错误",
                502: "网关错误",
                503: "服务暂不可用",
                504: "请求超时",
                529: "站点过载",
            }.get(status_code, f"服务错误({status_code})")
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return "请求超时"
    if isinstance(
        exc,
        (ConnectionError, ConnectionResetError, BrokenPipeError),
    ):
        return "网络连接异常"
    message = str(exc).lower()
    if "rate limiter" in message:
        return "请求频率超限"
    if "timed out" in message:
        return "请求超时"
    return "服务暂时不可用"


def build_retry_status_msg(text: str) -> Msg:
    return Msg(
        name="Friday",
        role="assistant",
        content=[TextBlock(type="text", text=text)],
        metadata={"retry_status": True},
    )


async def add_retry_notice_to_memory(agent: Any, retry_msg: Msg) -> None:
    if agent is None:
        return
    try:
        await agent.memory.add(retry_msg)
    except Exception:
        pass


async def save_state_before_retry(
    owner: QueryAttemptOwner,
    agent: Any,
    session_state_loaded: bool,
    session_id: str,
    skip_history: bool,
    user_id: str,
    *,
    cleanup_timeout: float,
) -> None:
    if agent is None or not session_state_loaded:
        return
    try:
        await asyncio.wait_for(
            owner.save_job_session_state(
                agent,
                session_id,
                skip_history,
                user_id,
            ),
            timeout=cleanup_timeout,
        )
    except Exception as exc:
        logger.warning("Failed to save state before retry: %s", exc)


async def stream_retry_backoff_notice(
    owner: QueryAttemptOwner,
    *,
    retry_attempt: int,
    max_retries: int,
    backoff_base: float,
    backoff_cap: float,
    session_id: str,
    retry_state: Any,
) -> AsyncGenerator[tuple[Msg, bool], None]:
    if retry_attempt <= 0:
        return
    backoff = compute_retry_backoff(retry_attempt, backoff_cap, backoff_base)
    logger.info(
        "Query retry attempt %d/%d, backoff=%.1fs (session=%s)",
        retry_attempt,
        max_retries,
        backoff,
        session_id,
    )
    retry_msg = build_retry_status_msg(
        f"正在重试 ({retry_attempt}/{max_retries})...",
    )
    yield retry_msg, False
    await add_retry_notice_to_memory(retry_state.prev_agent, retry_msg)
    await asyncio.sleep(backoff)


async def stream_retryable_query_error(
    owner: QueryAttemptOwner,
    *,
    exc: BaseException,
    retry_attempt: int,
    max_retry_attempts: int,
    max_retries: int,
    retry_state: Any,
    runtime: _QueryRuntime | None,
    session_id: str,
    cleanup_timeout: float,
) -> AsyncGenerator[tuple[Msg, bool], None]:
    error_summary = summarize_retry_error(exc)
    logger.warning(
        "Query failed with retryable error (attempt %d/%d): %s (summary: %s)",
        retry_attempt + 1,
        max_retry_attempts,
        exc,
        error_summary,
    )
    retry_msg = build_retry_status_msg(
        f"{error_summary}，正在重试 ({retry_attempt + 1}/{max_retries})...",
    )
    yield retry_msg, False
    await add_retry_notice_to_memory(retry_state.agent, retry_msg)
    await save_state_before_retry(
        owner,
        retry_state.agent,
        retry_state.session_state_loaded,
        session_id,
        runtime.skip_history if runtime is not None else False,
        runtime.user_id if runtime is not None else "",
        cleanup_timeout=cleanup_timeout,
    )


async def stream_single_query_attempt(
    owner: QueryAttemptOwner,
    *,
    attempt_input: Any,
    outcome: Any,
    retry_state: Any,
    attempt_state: Any,
) -> AsyncGenerator[tuple[Msg, bool], None]:
    attempt_state.runtime_start = await owner._prepare_query_runtime(
        request=attempt_input.request,
        msgs=attempt_input.msgs,
        query=attempt_input.query,
        preflight=attempt_input.preflight,
    )
    if attempt_state.runtime_start.block_response is not None:
        await owner._end_trace_if_needed(
            attempt_input.trace_id,
            TraceStatus.COMPLETED,
        )
        yield attempt_state.runtime_start.block_response, True
        attempt_state.should_return = True
        return
    runtime = attempt_state.runtime_start.runtime
    attempt_state.runtime = runtime
    if runtime is None:
        attempt_state.should_return = True
        return
    with runtime_invocation_claims_context(
        chat_id=runtime.chat.id if runtime.chat is not None else None,
    ):
        owner._rebind_trace_skill_detector_if_needed(
            runtime=runtime,
            trace_id=attempt_input.trace_id,
        )
        if attempt_input.trace_id and runtime.session_skill_detector is None:
            await runtime.agent.setup_skill_detector(attempt_input.trace_id)
        logger.debug("Agent Query msgs %s", attempt_input.msgs)
        attempt_state.session_state_loaded = await owner.get_state_loaded(
            runtime.agent,
            runtime.session_id,
            attempt_state.session_state_loaded,
            runtime.skip_history,
            runtime.user_id,
        )
        retry_state.agent = runtime.agent
        retry_state.session_state_loaded = attempt_state.session_state_loaded
        skill_freshness_refresh = await owner._refresh_session_skill_freshness(
            runtime=runtime,
        )
        runtime.agent.rebuild_sys_prompt()
        plan = await owner._build_turn_plan(
            runtime=runtime,
            request=attempt_input.request,
            msgs=attempt_input.msgs,
            query=attempt_input.query,
        )
        if skill_freshness_refresh.notice_text:
            plan.turn_msgs.insert(
                0,
                owner._build_skill_freshness_notice_msg(
                    skill_freshness_refresh.notice_text,
                ),
            )
        async for msg, last in owner._stream_completion_lifecycle(
            request=attempt_input.request,
            runtime=runtime,
            plan=plan,
            outcome=outcome,
        ):
            if not attempt_state.session_title_task_started:
                owner._schedule_session_title_task(
                    request=attempt_input.request,
                    chat=runtime.chat,
                    msgs=attempt_input.msgs,
                    trace_id=attempt_input.trace_id,
                )
                attempt_state.session_title_task_started = True
            yield msg, last
        skill_snapshot_to_persist = (
            await owner._build_skill_snapshot_to_persist(
                runtime=runtime,
                refresh_result=skill_freshness_refresh,
            )
        )
        if outcome.completion_blocked:
            await owner._finish_blocked_query_attempt(
                runtime=runtime,
                outcome=outcome,
                trace_id=attempt_input.trace_id,
                skill_snapshot_to_persist=skill_snapshot_to_persist,
            )
            attempt_state.should_return = True
            return
        await owner._complete_successful_query_attempt(
            runtime=runtime,
            plan=plan,
            outcome=outcome,
            trace_id=attempt_input.trace_id,
            skill_snapshot_to_persist=skill_snapshot_to_persist,
        )
    retry_state.task_completed = outcome.task_completed
    attempt_state.succeeded = True


async def stream_query_after_preflight(
    owner: QueryAttemptOwner,
    *,
    msgs: list[Any],
    request: AgentRequest,
    query: str | None,
    session_id: str,
    preflight: _QueryPreflight,
) -> AsyncGenerator[tuple[Msg, bool], None]:
    """Run retry attempts and final cleanup after preflight succeeds."""
    logger.debug(
        "AgentRunner.stream_query: request=%s, agent_id=%s",
        request,
        owner.agent_id,
    )
    set_current_agent_id(owner.agent_id)
    file_url_network_token = set_current_file_url_network(
        owner._request_file_url_network(request),
    )
    trace_id = await owner._start_query_trace(request, msgs)
    claims_context = runtime_invocation_claims_context(
        session_id=session_id,
        trace_id=trace_id,
    )
    claims_context.__enter__()
    outcome = owner._new_query_turn_outcome()
    retry_state = owner._new_retry_state()
    if preflight.agent_config is None:
        max_retry_attempts, max_retries, backoff_base, backoff_cap = (
            owner._load_query_retry_settings()
        )
    else:
        max_retry_attempts, max_retries, backoff_base, backoff_cap = (
            owner._load_query_retry_settings(preflight.agent_config)
        )
    attempt_input = owner._new_query_attempt_input(
        request=request,
        msgs=msgs,
        query=query,
        preflight=preflight,
        trace_id=trace_id,
    )
    attempt_state = owner._new_query_attempt_state()
    try:
        for retry_attempt in range(max_retry_attempts):
            retry_state.prev_agent = retry_state.agent
            retry_state.prev_session_state_loaded = (
                retry_state.session_state_loaded
            )
            retry_state.agent = None
            retry_state.session_state_loaded = False
            attempt_state = owner._new_query_attempt_state()
            async for msg, last in owner._stream_retry_backoff_notice(
                retry_attempt=retry_attempt,
                max_retries=max_retries,
                backoff_base=backoff_base,
                backoff_cap=backoff_cap,
                session_id=session_id,
                retry_state=retry_state,
            ):
                yield msg, last
            try:
                async with global_tracer.start_as_current_span(
                    "agent.attempt",
                ) as span:
                    span.set_attribute("retry.index", retry_attempt)
                    async for msg, last in owner._stream_single_query_attempt(
                        attempt_input=attempt_input,
                        outcome=outcome,
                        retry_state=retry_state,
                        attempt_state=attempt_state,
                    ):
                        yield msg, last
                    if attempt_state.should_return:
                        return
                    if attempt_state.succeeded:
                        break
            except asyncio.CancelledError as exc:
                await owner._handle_query_cancelled(
                    trace_id=trace_id,
                    session_id=session_id,
                    agent=(
                        attempt_state.runtime.agent
                        if attempt_state.runtime is not None
                        else None
                    ),
                    exc=exc,
                )
                return
            except Exception as exc:
                if not owner._should_retry(
                    retry_attempt,
                    max_retry_attempts,
                    exc,
                ):
                    await owner._raise_console_model_call_failed_if_needed(
                        request=request,
                        exc=exc,
                        trace_id=trace_id,
                    )
                    await owner._handle_query_error(
                        request=request,
                        exc=exc,
                        trace_id=trace_id,
                        locals_snapshot=locals(),
                    )
                    raise
                async for msg, last in owner._stream_retryable_query_error(
                    exc=exc,
                    retry_attempt=retry_attempt,
                    max_retry_attempts=max_retry_attempts,
                    max_retries=max_retries,
                    retry_state=retry_state,
                    runtime=attempt_state.runtime,
                    session_id=session_id,
                ):
                    yield msg, last
    finally:
        try:
            claims_context.__exit__(None, None, None)
        except ValueError:
            logger.debug(
                "Skipped runtime invocation claims context reset from a different async context",
                exc_info=True,
            )
        try:
            reset_current_file_url_network(file_url_network_token)
        except ValueError:
            logger.debug(
                "Skipped file URL network context reset from a different async context",
                exc_info=True,
            )
        cleanup_runtime = attempt_state.runtime
        cleanup_state_loaded = attempt_state.session_state_loaded
        if cleanup_runtime is None and retry_state.prev_agent is not None:
            cleanup_state_loaded = (
                retry_state.session_state_loaded
                or retry_state.prev_session_state_loaded
            )
        await owner._cleanup_query_resources(
            runtime=cleanup_runtime,
            session_state_loaded=cleanup_state_loaded,
            session_id=session_id,
        )
        await owner._cleanup_blocked_runtime_start(attempt_state.runtime_start)
        await owner._store_qa_content_if_needed(
            runtime=cleanup_runtime,
            query=query,
            outcome=outcome,
        )
