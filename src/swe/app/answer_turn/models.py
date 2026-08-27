# -*- coding: utf-8 -*-
"""Value objects for the Console answer-turn lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar


class TurnStatus(str, Enum):
    ADMITTING = "admitting"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


TERMINAL_STATUSES = frozenset(
    {TurnStatus.COMPLETED, TurnStatus.CANCELLED, TurnStatus.FAILED},
)


@dataclass(frozen=True, slots=True)
class TurnIdentity:
    chat_id: str
    msgid: str

    @classmethod
    def create(cls, chat_id: str, msgid: str | None = None) -> "TurnIdentity":
        from uuid import uuid4

        return cls(chat_id, msgid or f"turn-{uuid4().hex}")


@dataclass(frozen=True, slots=True)
class TurnOutcome:
    status: TurnStatus
    identity: TurnIdentity | None = None
    result: Any = None
    error: BaseException | str | None = None
    assistant_text: str | None = None

    _TERMINAL: ClassVar[frozenset[TurnStatus]] = TERMINAL_STATUSES

    def __post_init__(self) -> None:
        status = self.status
        if not isinstance(status, TurnStatus):
            object.__setattr__(self, "status", TurnStatus(status))
        if self.status not in self._TERMINAL:
            raise ValueError(f"outcome must be terminal, got {self.status}")

    @classmethod
    def completed(
        cls,
        identity_or_result: TurnIdentity | Any = None,
        *,
        assistant_text: str | None = None,
        result: Any = None,
    ) -> "TurnOutcome":
        identity = (
            identity_or_result
            if isinstance(identity_or_result, TurnIdentity)
            else None
        )
        if identity is None and result is None:
            result = identity_or_result
        return cls(
            TurnStatus.COMPLETED,
            identity,
            result,
            None,
            assistant_text,
        )

    @classmethod
    def cancelled(
        cls,
        identity_or_result: TurnIdentity | Any = None,
        *,
        result: Any = None,
    ) -> "TurnOutcome":
        identity = (
            identity_or_result
            if isinstance(identity_or_result, TurnIdentity)
            else None
        )
        if identity is None and result is None:
            result = identity_or_result
        return cls(TurnStatus.CANCELLED, identity, result=result)

    @classmethod
    def failed(
        cls,
        identity: TurnIdentity | None,
        error: BaseException | str,
    ) -> "TurnOutcome":
        return cls(TurnStatus.FAILED, identity, error=error)


@dataclass(frozen=True, slots=True)
class TurnLease:
    identity: TurnIdentity
    queue: Any
    is_new_run: bool


@dataclass(frozen=True, slots=True)
class StopClaim:
    accepted: bool
    identity: TurnIdentity | None = None
    status: TurnStatus | None = None
