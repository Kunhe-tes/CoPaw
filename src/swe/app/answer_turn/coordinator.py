# -*- coding: utf-8 -*-
"""Authoritative state machine for Console answer turns."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .models import (
    TERMINAL_STATUSES,
    StopClaim,
    TurnIdentity,
    TurnLease,
    TurnOutcome,
    TurnStatus,
)
from .ports import (
    ApprovalPort,
    ExecutionPort,
    GoalPort,
    Producer,
    SessionPort,
    StreamPort,
    SubagentPort,
)


@dataclass
class _TurnState:
    identity: TurnIdentity
    status: TurnStatus
    outcome: TurnOutcome | None = None
    stop_effects_started: bool = False
    hard_cancel_watcher_started: bool = False
    settlement_started: bool = False


class AnswerTurnCoordinator:
    """Own admission, stop claims, terminal settlement, and active identity."""

    def __init__(
        self,
        *,
        stream: StreamPort,
        execution: ExecutionPort,
        session: SessionPort,
        goal: GoalPort,
        subagent: SubagentPort,
        approval: ApprovalPort,
        hard_cancel_delay: float = 5.0,
    ) -> None:
        self.stream = stream
        self.execution = execution
        self.session = session
        self.goal = goal
        self.subagent = subagent
        self.approval = approval
        self.hard_cancel_delay = hard_cancel_delay
        self._turns: dict[str, _TurnState] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def _chat_lock(self, chat_id: str) -> asyncio.Lock:
        async with self._global_lock:
            return self._locks.setdefault(chat_id, asyncio.Lock())

    async def start_or_attach(
        self,
        chat_id: str,
        payload: Any,
        producer: Producer,
        *,
        msgid: str | None = None,
    ) -> TurnLease:
        lock = await self._chat_lock(chat_id)
        async with lock:
            state = self._turns.get(chat_id)
            if state is not None and state.status not in TERMINAL_STATUSES:
                queue = await self.stream.attach(state.identity)
                if queue is not None:
                    return TurnLease(state.identity, queue, False)
                raise RuntimeError(
                    "live answer turn has no attachable stream; refusing a "
                    "second producer",
                )

            identity = TurnIdentity.create(
                chat_id=chat_id,
                msgid=msgid or f"msg-{uuid4().hex}",
            )
            self._turns[chat_id] = _TurnState(identity, TurnStatus.ADMITTING)
            queue = await self.stream.start(identity, payload, producer)
            self._turns[chat_id].status = TurnStatus.RUNNING
            return TurnLease(identity, queue, True)

    async def status(
        self,
        identity: TurnIdentity | str,
    ) -> TurnStatus | None:
        if isinstance(identity, str):
            lock = await self._chat_lock(identity)
            async with lock:
                state = self._turns.get(identity)
                return state.status if state is not None else None
        lock = await self._chat_lock(identity.chat_id)
        async with lock:
            state = self._turns.get(identity.chat_id)
            if state is None or state.identity != identity:
                return None
            return state.status

    async def claim_stop(
        self,
        identity: TurnIdentity | str,
        *,
        msgid: str | None = None,
    ) -> StopClaim:
        if isinstance(identity, str):
            async with self._global_lock:
                current = self._turns.get(identity)
            if current is None:
                return StopClaim(False, status=None)
            identity = current.identity
        lock = await self._chat_lock(identity.chat_id)
        run_effects = False
        start_watcher = False
        async with lock:
            state = self._turns.get(identity.chat_id)
            if state is None or state.identity != identity:
                return StopClaim(False, identity=None, status=None)
            if msgid is not None and msgid != identity.msgid:
                return StopClaim(False, identity=identity, status=state.status)
            if state.status in TERMINAL_STATUSES:
                return StopClaim(False, identity=identity, status=state.status)
            if state.status == TurnStatus.STOPPING:
                return StopClaim(True, identity=identity, status=state.status)
            state.status = TurnStatus.STOPPING
            if not state.stop_effects_started:
                state.stop_effects_started = True
                run_effects = True
            if not state.hard_cancel_watcher_started:
                state.hard_cancel_watcher_started = True
                start_watcher = True
        if run_effects:
            await self._run_stop_effects(identity)
            await self.execution.request_cooperative_stop(identity)
        if start_watcher:
            asyncio.create_task(self._hard_cancel_watch(identity))
        return StopClaim(True, identity=identity, status=TurnStatus.STOPPING)

    async def _run_stop_effects(self, identity: TurnIdentity) -> None:
        await self.approval.supersede(identity)
        await self.goal.interrupt(identity)
        await self.subagent.cancel(identity)

    async def _hard_cancel_watch(self, identity: TurnIdentity) -> None:
        await asyncio.sleep(self.hard_cancel_delay)
        lock = await self._chat_lock(identity.chat_id)
        async with lock:
            state = self._turns.get(identity.chat_id)
            if state is None or state.identity != identity:
                return
            if state.status in TERMINAL_STATUSES:
                return
        lock = await self._chat_lock(identity.chat_id)
        async with lock:
            state = self._turns.get(identity.chat_id)
            if state is None or state.identity != identity:
                return
            if state.status in TERMINAL_STATUSES:
                return
            await self.execution.hard_cancel(identity)

    async def settle(
        self,
        identity: TurnIdentity | TurnOutcome,
        outcome: TurnOutcome | None = None,
    ) -> bool:
        if isinstance(identity, TurnOutcome):
            outcome = identity
            identity = outcome.identity
        if outcome is None:
            raise TypeError("settle requires an outcome")
        if outcome.identity != identity:
            raise ValueError("outcome identity must match settled turn")
        lock = await self._chat_lock(identity.chat_id)
        async with lock:
            state = self._turns.get(identity.chat_id)
            if state is None or state.identity != identity:
                return False
            if state.settlement_started:
                return False
            state.settlement_started = True
            state.status = outcome.status
            state.outcome = outcome
        await self.session.persist(identity, outcome)
        await self.stream.close(identity)
        lock = await self._chat_lock(identity.chat_id)
        async with lock:
            state = self._turns.get(identity.chat_id)
            if state is not None and state.identity == identity:
                self._turns.pop(identity.chat_id, None)
        return True
