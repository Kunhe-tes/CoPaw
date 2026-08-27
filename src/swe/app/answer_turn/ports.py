# -*- coding: utf-8 -*-
"""Narrow async ports used by :mod:`answer_turn.coordinator`."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

from .models import TurnIdentity, TurnOutcome

Producer = Callable[[TurnIdentity, Any], Awaitable[Any]]


class StreamPort(Protocol):
    async def start(
        self,
        identity: TurnIdentity,
        payload: Any,
        producer: Producer,
    ) -> Any:
        pass

    async def attach(self, identity: TurnIdentity) -> Any | None:
        pass

    async def close(self, identity: TurnIdentity) -> None:
        pass


class ExecutionPort(Protocol):
    async def request_cooperative_stop(self, identity: TurnIdentity) -> None:
        pass

    async def hard_cancel(self, identity: TurnIdentity) -> None:
        pass


class SessionPort(Protocol):
    async def persist(
        self,
        identity: TurnIdentity,
        outcome: TurnOutcome,
    ) -> None:
        pass


class GoalPort(Protocol):
    async def interrupt(self, identity: TurnIdentity) -> None:
        pass


class SubagentPort(Protocol):
    async def cancel(self, identity: TurnIdentity) -> None:
        pass


class ApprovalPort(Protocol):
    async def supersede(self, identity: TurnIdentity) -> None:
        pass
