# -*- coding: utf-8 -*-
# flake8: noqa: E704
"""Query finally-stage resource cleanup orchestration."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from .query_contracts import _QueryRuntime


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
