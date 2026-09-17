# -*- coding: utf-8 -*-
"""Deep query-execution seam used by the ``AgentRunner`` facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol

from agentscope.message import Msg
from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest


@dataclass(frozen=True)
class QueryInvocation:
    """Immutable input accepted by one complete query execution."""

    request: AgentRequest
    msgs: tuple[Any, ...]


@dataclass(frozen=True)
class QueryFrame:
    """One ordered message frame emitted by query execution."""

    message: Msg
    last: bool


class QueryExecutionAdapter(Protocol):
    """Implementation seam for live and test query execution adapters."""

    def stream(
        self,
        invocation: QueryInvocation,
    ) -> AsyncIterator[QueryFrame]:
        """Yield frames in the established query order."""


class QueryExecution:
    """Expose one streaming Interface while hiding execution details."""

    def __init__(self, adapter: QueryExecutionAdapter) -> None:
        self._adapter = adapter

    async def stream(
        self,
        invocation: QueryInvocation,
    ) -> AsyncIterator[QueryFrame]:
        """Yield the adapter's frames without buffering or reordering."""
        async for frame in self._adapter.stream(invocation):
            yield frame
