"""Goal turn settlement and deterministic verification coordination."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import Field

from .models import GoalSnapshot, GoalState, GoalTurnDecision, StrictGoalModel
from .service import GoalService

VerificationResult = tuple[bool, str | None]
Verifier = Callable[[GoalSnapshot], dict[str, VerificationResult] | Awaitable[dict[str, VerificationResult]]]


class GoalTurnResolution(StrictGoalModel):
    """The validated Main Agent output consumed at a Goal turn boundary."""

    decision: GoalTurnDecision
    summary: str = Field(min_length=1)
    next_focus: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    wake_conditions: list[str] = Field(default_factory=list)
    completion_proposal: str | None = None
    blocker: str | None = None
    affected_criteria: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: object) -> None:
        if self.decision == "wait" and not self.wake_conditions:
            raise ValueError("wait requires at least one wake condition")
        if self.decision == "blocked" and not (self.blocker or "").strip():
            raise ValueError("blocked requires a blocker")
        if self.decision == "propose_completion" and not (
            self.completion_proposal or ""
        ).strip():
            raise ValueError("propose_completion requires a completion proposal")


class GoalRuntime:
    """Host-side coordinator; it never grants tools or asks an LLM to judge."""

    def __init__(self, service: GoalService, *, verifier: Verifier) -> None:
        self._service = service
        self._verifier = verifier

    async def settle(
        self,
        goal_id: str,
        resolution: GoalTurnResolution,
        *,
        wake_from_steering: bool = False,
    ) -> GoalSnapshot:
        """Persist the Main Agent result, then run contract-bound verification."""
        before = await self._service.get(goal_id)
        if not before.turn_active:
            before = await self._service.begin_turn(goal_id)
        goal = await self._service.settle_turn(
            goal_id,
            decision=resolution.decision,
            next_focus=resolution.next_focus,
            blocker=resolution.blocker,
            defer_budget_limit=resolution.decision == "propose_completion",
            wake_from_steering=wake_from_steering,
        )
        if goal.state != GoalState.ACTIVE:
            return goal
        if goal.revision != before.revision:
            # A Direct Goal Edit won this settlement boundary. The completed
            # old turn is evidence only for the prior Revision and must not
            # verify or complete the newly activated Contract.
            return goal
        if resolution.decision != "propose_completion":
            if resolution.affected_criteria:
                goal = await self._verify(
                    goal, before.revision, resolution.affected_criteria,
                )
                if goal.state != GoalState.ACTIVE:
                    return goal
            return await self._service.enforce_budget_limit(goal_id)
        requested = set(resolution.affected_criteria) | {
            item.criterion_id for item in goal.criteria if not item.verified
        }
        goal = await self._verify(goal, before.revision, requested)
        if goal.state == GoalState.BLOCKED:
            return goal
        if all(criterion.verified for criterion in goal.criteria):
            goal.state = GoalState.COMPLETE
            goal.state_reason = None
            return await self._service.persist(goal)
        return await self._service.enforce_budget_limit(goal_id)

    async def _verify(
        self,
        goal: GoalSnapshot,
        revision: int,
        requested: set[str] | list[str],
    ) -> GoalSnapshot:
        results = self._verifier(goal)
        if inspect.isawaitable(results):
            results = await results
        requested = set(requested)
        criterion_ids = {item.criterion_id for item in goal.criteria}
        if requested and not requested.issubset(criterion_ids):
            raise ValueError("affected_criteria contains an unknown criterion")
        for criterion in goal.criteria:
            if criterion.criterion_id not in requested:
                continue
            passed, evidence = results.get(
                criterion.criterion_id,
                (False, "verification result missing"),
            )
            goal = await self._service.record_verification(
                goal.goal_id,
                criterion.criterion_id,
                passed=passed,
                evidence_ref=evidence,
                expected_revision=revision,
            )
            if goal.state == GoalState.BLOCKED:
                return goal
        return goal
