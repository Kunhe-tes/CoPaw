# -*- coding: utf-8 -*-
# flake8: noqa: E704
"""Query finally-stage resource cleanup orchestration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from .query_contracts import _QueryRuntime

logger = logging.getLogger(__name__)


async def cleanup_mcp_clients(clients: list[Any]) -> None:
    """Close every MCP client created for one query."""
    for client in clients:
        try:
            await client.close()
        except Exception as exc:
            logger.warning("Error closing MCP client: %s", exc)


async def cleanup_blocked_runtime_start(
    owner: Any,
    runtime_start: Any,
    *,
    cleanup_timeout: float,
    cleanup_mcp: Any | None = None,
) -> None:
    """Release chat and MCP resources created before a blocking start Hook."""
    if (
        runtime_start is None
        or runtime_start.block_response is None
        or runtime_start.runtime is not None
    ):
        return
    session_id = runtime_start.blocked_session_id
    chat = runtime_start.blocked_chat
    if owner._chat_manager is not None and chat is not None:
        try:
            await asyncio.wait_for(
                owner._chat_manager.update_chat(chat),
                timeout=cleanup_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Runner finally: blocked chat update timed out "
                "(session_id=%s, timeout=%.0fs)",
                session_id,
                cleanup_timeout,
            )
        except asyncio.CancelledError:
            logger.debug(
                "Runner finally: blocked chat update cancelled "
                "(session_id=%s)",
                session_id,
            )
    mcp_clients = runtime_start.blocked_mcp_clients or []
    if not mcp_clients:
        return
    if cleanup_mcp is None:
        cleanup_mcp = cleanup_mcp_clients
    try:
        await asyncio.wait_for(
            cleanup_mcp(mcp_clients),
            timeout=cleanup_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Runner finally: blocked MCP cleanup timed out "
            "(session_id=%s, timeout=%.0fs)",
            session_id,
            cleanup_timeout,
        )
    except asyncio.CancelledError:
        logger.debug(
            "Runner finally: blocked MCP cleanup cancelled " "(session_id=%s)",
            session_id,
        )


async def save_state_during_cleanup(
    owner: Any,
    *,
    runtime: _QueryRuntime | None,
    session_state_loaded: bool,
    cleanup_timeout: float,
    hook_config_enabled: Any,
) -> None:
    """Persist session state during query cleanup within the configured limit."""
    logger.info(
        "_save_state_during_cleanup: runtime=%s session_state_loaded=%s",
        runtime is not None,
        session_state_loaded,
    )
    if runtime is None or not session_state_loaded:
        return
    hook_overlay = None
    if hook_config_enabled(
        runtime.tenant_hooks,
        runtime.agent_config,
        runtime.hook_overlay,
    ):
        hook_overlay = runtime.hook_overlay
    try:
        await asyncio.wait_for(
            owner.save_job_session_state(
                runtime.agent,
                runtime.session_id,
                runtime.skip_history,
                runtime.user_id,
                hook_overlay=hook_overlay,
            ),
            timeout=cleanup_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Runner finally: session state save timed out "
            "(session_id=%s, timeout=%.0fs)",
            runtime.session_id,
            cleanup_timeout,
        )
    except asyncio.CancelledError:
        logger.debug(
            "Runner finally: session state save cancelled (session_id=%s)",
            runtime.session_id,
        )


async def update_chat_during_cleanup(
    owner: Any,
    runtime: _QueryRuntime | None,
    *,
    cleanup_timeout: float,
) -> None:
    """Write a query chat record back during cleanup."""
    if runtime is None or owner._chat_manager is None or runtime.chat is None:
        return
    try:
        await asyncio.wait_for(
            owner._chat_manager.update_chat(runtime.chat),
            timeout=cleanup_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Runner finally: chat update timed out "
            "(session_id=%s, timeout=%.0fs)",
            runtime.session_id,
            cleanup_timeout,
        )
    except asyncio.CancelledError:
        logger.debug(
            "Runner finally: chat update cancelled (session_id=%s)",
            runtime.session_id,
        )


async def cleanup_runtime_mcp(
    runtime: _QueryRuntime | None,
    *,
    cleanup_timeout: float,
    cleanup_mcp: Any = cleanup_mcp_clients,
) -> None:
    """Close MCP clients created for a running query."""
    if runtime is None or not runtime.mcp_clients:
        return
    try:
        await asyncio.wait_for(
            cleanup_mcp(runtime.mcp_clients),
            timeout=cleanup_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Runner finally: MCP cleanup timed out "
            "(session_id=%s, timeout=%.0fs)",
            runtime.session_id,
            cleanup_timeout,
        )
    except asyncio.CancelledError:
        logger.debug(
            "Runner finally: MCP cleanup cancelled (session_id=%s)",
            runtime.session_id,
        )


async def end_skill_detector_during_cleanup(
    runtime: _QueryRuntime | None,
    *,
    cleanup_timeout: float,
) -> None:
    """End the session-level skill detector for a completed query."""
    if runtime is None or runtime.session_skill_detector is None:
        return
    try:
        await asyncio.wait_for(
            runtime.session_skill_detector.on_reasoning_end(),
            timeout=cleanup_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Runner finally: skill detector cleanup timed out "
            "(session_id=%s, timeout=%.0fs)",
            runtime.session_id,
            cleanup_timeout,
        )
    except asyncio.CancelledError:
        logger.debug(
            "Runner finally: skill detector cleanup cancelled "
            "(session_id=%s)",
            runtime.session_id,
        )


class QueryCleanupOwner(Protocol):
    """The ordered cleanup operations owned by ``AgentRunner``."""

    async def _save_state_during_cleanup(
        self,
        *,
        runtime: _QueryRuntime | None,
        session_state_loaded: bool,
    ) -> None: ...

    async def _update_chat_during_cleanup(
        self,
        runtime: _QueryRuntime | None,
    ) -> None: ...

    async def _cleanup_mcp_during_cleanup(
        self,
        runtime: _QueryRuntime | None,
    ) -> None: ...

    async def _end_skill_detector_during_cleanup(
        self,
        runtime: _QueryRuntime | None,
    ) -> None: ...


async def cleanup_query_resources(
    owner: QueryCleanupOwner,
    *,
    runtime: _QueryRuntime | None,
    session_state_loaded: bool,
    session_id: str,
) -> None:
    """Run cleanup concurrently and preserve first-exception propagation."""
    cleanup_results = await asyncio.gather(
        owner._save_state_during_cleanup(
            runtime=runtime,
            session_state_loaded=session_state_loaded,
        ),
        owner._update_chat_during_cleanup(runtime),
        owner._cleanup_mcp_during_cleanup(runtime),
        owner._end_skill_detector_during_cleanup(runtime),
        return_exceptions=True,
    )
    for result in cleanup_results:
        if isinstance(result, BaseException):
            raise result
