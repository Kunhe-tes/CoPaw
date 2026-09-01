# -*- coding: utf-8 -*-
"""Narrow async ports used by :mod:`answer_turn.coordinator`."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

from .models import TurnIdentity, TurnOutcome

Producer = Callable[[TurnIdentity, Any], Awaitable[Any]]


class TurnStreamPort(Protocol):
    async def attach_or_start(
        self,
        identity: TurnIdentity,
        payload: Any,
        producer: Producer,
        *,
        before_start: Any | None = None,
    ) -> Any:
        pass

    async def stream(self, identity: TurnIdentity, queue: Any):
        pass

    async def close(self, identity: TurnIdentity) -> None:
        pass


class TurnExecutionPort(Protocol):
    async def request_cooperative_stop(self, identity: TurnIdentity) -> None:
        pass

    async def hard_cancel(self, identity: TurnIdentity) -> None:
        pass


class TurnSessionPort(Protocol):
    async def persist_outcome(
        self,
        outcome: TurnOutcome,
    ) -> None:
        pass


class TurnGoalPort(Protocol):
    async def interrupt_if_matches(
        self,
        identity: TurnIdentity,
        reason: str,
    ) -> None:
        pass


class TurnSubAgentPort(Protocol):
    async def cancel_for_turn(self, identity: TurnIdentity) -> None:
        pass


class TurnApprovalPort(Protocol):
    async def supersede_for_turn(self, identity: TurnIdentity) -> None:
        pass


StreamPort = TurnStreamPort
ExecutionPort = TurnExecutionPort
SessionPort = TurnSessionPort
GoalPort = TurnGoalPort
SubagentPort = TurnSubAgentPort
ApprovalPort = TurnApprovalPort
