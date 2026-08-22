"""Strict domain models for the first Goal Runtime phase."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    """Return a timezone-aware timestamp for durable Goal records."""
    return datetime.now(timezone.utc)


class GoalState(StrEnum):
    ACTIVE = "ACTIVE"
    WAITING = "WAITING"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    LIMITED = "LIMITED"
    INTERRUPTED = "INTERRUPTED"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"


TERMINAL_GOAL_STATES = frozenset({GoalState.COMPLETE, GoalState.CANCELLED})


class GoalControlAction(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    EDIT = "edit"


GoalTurnDecision = Literal["continue", "wait", "propose_completion", "blocked"]


class StrictGoalModel(BaseModel):
    """Goal contracts and snapshots do not accept undeclared semantics."""

    model_config = ConfigDict(extra="forbid")


class CompletionCriterion(StrictGoalModel):
    """One mandatory, deterministically verifiable completion condition."""

    requirement: str = Field(min_length=1, max_length=4000)
    observable_assertion: str = Field(min_length=1, max_length=4000)
    verification_method: str = Field(min_length=1, max_length=4000)
    expected_outcome: str = Field(min_length=1, max_length=4000)

    @field_validator(
        "requirement",
        "observable_assertion",
        "verification_method",
        "expected_outcome",
    )
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class GoalConstraints(StrictGoalModel):
    must_preserve: list[str] = Field(default_factory=list)
    must_not_do: list[str] = Field(default_factory=list)


class GoalContract(StrictGoalModel):
    """User-confirmed acceptance and autonomy boundary for one Revision."""

    objective: str = Field(min_length=1, max_length=4000)
    completion_criteria: list[CompletionCriterion] = Field(min_length=1)
    constraints: GoalConstraints
    autonomy_boundary: str = Field(min_length=1, max_length=4000)

    @field_validator("objective", "autonomy_boundary")
    @classmethod
    def reject_blank_contract_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class GoalScope(StrictGoalModel):
    """Frozen Goal execution identity and owning Chat."""

    tenant_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    agent_profile_id: str = Field(min_length=1, max_length=128)
    chat_id: str = Field(min_length=1, max_length=255)
    effective_model: str = Field(min_length=1, max_length=255)


class GoalCriterionStatus(StrictGoalModel):
    criterion_id: str
    criterion: CompletionCriterion
    verified: bool = False
    consecutive_failures: int = Field(default=0, ge=0)
    evidence_refs: list[str] = Field(default_factory=list)


class GoalControlCommand(StrictGoalModel):
    command_id: str = Field(default_factory=lambda: f"goal-command-{uuid4().hex}")
    action: GoalControlAction
    contract: GoalContract | None = None
    status: Literal["pending", "applied", "superseded"] = "pending"
    created_at: datetime = Field(default_factory=utc_now)


class GoalSteering(StrictGoalModel):
    """One ordered ordinary user message accepted by an active Goal."""

    sequence_no: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=16000)
    consumed: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class GoalSnapshot(StrictGoalModel):
    """The authoritative persistent state for an individual Goal."""

    goal_id: str = Field(default_factory=lambda: f"goal-{uuid4().hex}")
    scope: GoalScope
    state: GoalState = GoalState.ACTIVE
    revision: int = Field(default=1, ge=1)
    contract: GoalContract
    criteria: list[GoalCriterionStatus]
    turn_budget: int = Field(gt=0)
    budget_cycle: int = Field(default=1, ge=1)
    turns_used: int = Field(default=0, ge=0)
    turn_active: bool = False
    next_focus: str | None = None
    state_reason: str | None = None
    control_commands: list[GoalControlCommand] = Field(default_factory=list)
    steering: list[GoalSteering] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_GOAL_STATES
