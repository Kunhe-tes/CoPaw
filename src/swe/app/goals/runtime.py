# -*- coding: utf-8 -*-
"""Goal turn settlement and completion review coordination."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import Literal

from pydantic import Field

from .models import GoalSnapshot, GoalState, GoalTurnDecision, StrictGoalModel
from .service import GoalService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompletionReviewPending:
    """A completion review is waiting for the existing approval flow."""

    request_id: str
    reason: str


CompletionReviewResult = tuple[bool, str | None] | CompletionReviewPending
CompletionReviewer = Callable[
    [GoalSnapshot],
    dict[str, CompletionReviewResult]
    | Awaitable[dict[str, CompletionReviewResult]],
]

# Keep the command-verification adapter working until it is replaced by the
# completion-judge integration. These names are not persisted in Goal snapshots.
VerificationPending = CompletionReviewPending
VerificationResult = CompletionReviewResult
Verifier = CompletionReviewer


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
        if (
            self.decision == "propose_completion"
            and not (self.completion_proposal or "").strip()
        ):
            raise ValueError(
                "propose_completion requires a completion proposal",
            )


class GoalRuntime:
    """Host-side coordinator; it delegates completion reviews to a reviewer."""

    def __init__(
        self,
        service: GoalService,
        *,
        reviewer: CompletionReviewer | None = None,
        verifier: Verifier | None = None,
    ) -> None:
        if reviewer is not None:
            if verifier is not None:
                raise ValueError("provide exactly one of reviewer or verifier")
            resolved_reviewer = reviewer
        else:
            if verifier is None:
                raise ValueError("provide exactly one of reviewer or verifier")
            resolved_reviewer = verifier
        self._service = service
        # ``verifier`` is a deprecated compatibility alias for existing callers.
        self._reviewer: CompletionReviewer = resolved_reviewer

    async def settle(
        self,
        goal_id: str,
        resolution: GoalTurnResolution,
        *,
        wake_from_steering: bool = False,
        environment_changed: bool = False,
    ) -> GoalSnapshot:
        """Persist the Main Agent result, then run completion review."""
        before = await self._service.get(goal_id)
        logger.info(
            "goal_turn_resolution goal_id=%s revision=%s decision=%s affected_criteria=%s",
            goal_id,
            before.revision,
            resolution.decision,
            resolution.affected_criteria,
        )
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
            # review or complete the newly activated Contract.
            return goal
        if resolution.decision != "propose_completion":
            affected = set(resolution.affected_criteria)
            if environment_changed and not affected:
                affected = {item.criterion_id for item in goal.criteria}
            if affected:
                goal = await self._review(
                    goal,
                    before.revision,
                    affected,
                )
                if goal.state != GoalState.ACTIVE:
                    return goal
            return await self._service.enforce_budget_limit(goal_id)
        requested = set(resolution.affected_criteria) | {
            item.criterion_id for item in goal.criteria if not item.verified
        }
        goal = await self._review(goal, before.revision, requested)
        if goal.state == GoalState.BLOCKED:
            return goal
        if all(criterion.verified for criterion in goal.criteria):
            goal.state = GoalState.COMPLETE
            goal.state_reason = None
            return await self._service.persist(goal)
        return await self._service.enforce_budget_limit(goal_id)

    async def retry_pending_completion_review(
        self,
        goal_id: str,
    ) -> GoalSnapshot:
        """Resume an approval-gated Completion Review without spending a turn."""
        goal = await self._service.get(goal_id)
        pending = {
            item.criterion_id
            for item in goal.criteria
            if item.verification_request_id
        }
        if goal.state != GoalState.ACTIVE or not pending:
            return goal
        goal = await self._review(goal, goal.revision, pending)
        if goal.state == GoalState.BLOCKED:
            return goal
        if all(criterion.verified for criterion in goal.criteria):
            goal.state = GoalState.COMPLETE
            goal.state_reason = None
            return await self._service.persist(goal)
        return goal

    async def _review(
        self,
        goal: GoalSnapshot,
        revision: int,
        requested: set[str] | list[str],
    ) -> GoalSnapshot:
        requested = set(requested)
        criterion_ids = {item.criterion_id for item in goal.criteria}
        if requested and not requested.issubset(criterion_ids):
            raise ValueError("affected_criteria contains an unknown criterion")
        review_goal = goal.model_copy(deep=True)
        review_goal.criteria = [
            item
            for item in review_goal.criteria
            if item.criterion_id in requested
        ]
        results = self._reviewer(review_goal)
        if inspect.isawaitable(results):
            results = await results
        for criterion in goal.criteria:
            if criterion.criterion_id not in requested:
                continue
            result = results.get(
                criterion.criterion_id,
                (False, "completion review result missing"),
            )
            if isinstance(result, CompletionReviewPending):
                logger.info(
                    "goal_completion_review_pending goal_id=%s revision=%s criterion_id=%s request_id=%s",
                    goal.goal_id,
                    revision,
                    criterion.criterion_id,
                    result.request_id,
                )
                goal = await self._service.wait_for_completion_review_approval(
                    goal.goal_id,
                    criterion.criterion_id,
                    request_id=result.request_id,
                    reason=result.reason,
                    expected_revision=revision,
                )
                return goal
            passed, evidence = result
            logger.info(
                "goal_completion_review_result goal_id=%s revision=%s criterion_id=%s accepted=%s",
                goal.goal_id,
                revision,
                criterion.criterion_id,
                passed,
            )
            goal = await self._service.record_completion_review(
                goal.goal_id,
                criterion.criterion_id,
                passed=passed,
                evidence_ref=evidence,
                expected_revision=revision,
            )
            if goal.state == GoalState.BLOCKED:
                return goal
        return goal

    async def retry_pending_verification(self, goal_id: str) -> GoalSnapshot:
        """Compatibility alias for the pre-review runtime API."""
        return await self.retry_pending_completion_review(goal_id)
