# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio

import pytest

from swe.app.goals.models import (
    CompletionCriterion,
    GoalContract,
    GoalControlAction,
    GoalScope,
    GoalState,
)
from swe.app.goals.runtime import (
    CompletionReviewResult,
    CompletionReviewPending,
    GoalRuntime,
    GoalTurnResolution,
)
from swe.app.goals.service import GoalService, InMemoryGoalStore


def contract() -> GoalContract:
    return GoalContract(
        objective="Implement runtime",
        completion_criteria=[
            CompletionCriterion(
                requirement="Tests pass",
                observable_assertion="pytest exits 0",
                verification_method="Run pytest",
                expected_outcome="exit code 0",
            ),
        ],
        constraints={"must_preserve": [], "must_not_do": []},
        autonomy_boundary="No deploy",
    )


def scope() -> GoalScope:
    return GoalScope(
        tenant_id="tenant",
        source_id="source",
        agent_profile_id="agent",
        chat_id="chat",
        effective_model="model",
    )


@pytest.mark.asyncio
async def test_completion_proposal_requires_independent_review_before_complete() -> (
    None
):
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    runtime = GoalRuntime(
        service,
        reviewer=lambda _: {"criterion-1": (True, "pytest passed")},
    )

    result = await runtime.settle(
        goal.goal_id,
        GoalTurnResolution(
            decision="propose_completion",
            summary="done",
            next_focus=None,
            evidence_refs=["pytest passed"],
            completion_proposal="Report is ready for review",
        ),
    )

    assert result.state == GoalState.COMPLETE
    assert result.criteria[0].verified


@pytest.mark.asyncio
async def test_completion_proposal_completes_only_after_reviewer_accepts() -> (
    None
):
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())

    def reviewer(_: object) -> dict[str, CompletionReviewResult]:
        return {"criterion-1": (True, "Observed pytest output")}

    runtime = GoalRuntime(
        service,
        reviewer=reviewer,
    )

    result = await runtime.settle(
        goal.goal_id,
        GoalTurnResolution(
            decision="propose_completion",
            summary="done",
            completion_proposal="The test command passed",
        ),
    )

    assert result.state == GoalState.COMPLETE
    assert result.criteria[0].verified


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "expected_state"),
    [
        (GoalControlAction.CANCEL, GoalState.CANCELLED),
        (GoalControlAction.PAUSE, GoalState.PAUSED),
    ],
)
async def test_control_during_async_completion_review_wins_over_acceptance(
    action: GoalControlAction,
    expected_state: GoalState,
) -> None:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    reviewer_started = asyncio.Event()
    release_reviewer = asyncio.Event()

    async def reviewer(_: object) -> dict[str, CompletionReviewResult]:
        reviewer_started.set()
        await release_reviewer.wait()
        return {"criterion-1": (True, "Observed pytest output")}

    settlement = asyncio.create_task(
        GoalRuntime(service, reviewer=reviewer).settle(
            goal.goal_id,
            GoalTurnResolution(
                decision="propose_completion",
                summary="done",
                completion_proposal="The test command passed",
            ),
        ),
    )
    await reviewer_started.wait()

    await service.request_control(goal.goal_id, action)
    release_reviewer.set()
    result = await settlement

    assert result.state == expected_state
    assert not result.criteria[0].verified
    assert result.criteria[0].evidence_refs == []


@pytest.mark.asyncio
async def test_reviewer_rejections_block_after_three_attempts() -> None:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    runtime = GoalRuntime(
        service,
        reviewer=lambda _: {"criterion-1": (False, "Missing test output")},
    )
    resolution = GoalTurnResolution(
        decision="propose_completion",
        summary="done",
        completion_proposal="The test command passed",
    )

    first = await runtime.settle(goal.goal_id, resolution)
    assert first.state == GoalState.ACTIVE
    assert first.state_reason == "review rejected: Missing test output"
    assert first.criteria[0].evidence_refs == []

    await runtime.settle(goal.goal_id, resolution)
    result = await runtime.settle(goal.goal_id, resolution)

    assert result.state == GoalState.BLOCKED
    assert "review rejected" in (result.state_reason or "")
    assert "Missing test output" in (result.state_reason or "")
    assert result.criteria[0].evidence_refs == []


@pytest.mark.asyncio
async def test_budget_limit_preserves_completion_review_rejection_reason() -> (
    None
):
    service = GoalService(InMemoryGoalStore(), turn_budget=1)
    goal = await service.create_goal(scope=scope(), contract=contract())
    runtime = GoalRuntime(
        service,
        reviewer=lambda _: {"criterion-1": (False, "Missing test output")},
    )

    result = await runtime.settle(
        goal.goal_id,
        GoalTurnResolution(
            decision="propose_completion",
            summary="done",
            completion_proposal="The test command passed",
        ),
    )

    assert result.state == GoalState.LIMITED
    assert "review rejected: Missing test output" in (
        result.state_reason or ""
    )
    assert "budget exhausted" in (result.state_reason or "")


@pytest.mark.asyncio
async def test_non_completion_resolution_keeps_the_goal_active_for_next_turn() -> (
    None
):
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    runtime = GoalRuntime(service, reviewer=lambda _: {})

    result = await runtime.settle(
        goal.goal_id,
        GoalTurnResolution(
            decision="continue",
            summary="working",
            next_focus="write tests",
        ),
    )

    assert result.state == GoalState.ACTIVE
    assert result.next_focus == "write tests"


@pytest.mark.asyncio
async def test_pending_edit_discards_old_completion_proposal_before_review() -> (
    None
):
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    await service.begin_turn(goal.goal_id)
    await service.request_edit(goal.goal_id, contract())
    reviewer_calls = 0

    def reviewer(_):
        nonlocal reviewer_calls
        reviewer_calls += 1
        return {"criterion-1": (True, "stale pass")}

    result = await GoalRuntime(service, reviewer=reviewer).settle(
        goal.goal_id,
        GoalTurnResolution(
            decision="propose_completion",
            summary="old completion",
            evidence_refs=["old evidence"],
            completion_proposal="Old revision completion",
        ),
    )

    assert result.revision == 2
    assert result.state == GoalState.ACTIVE
    assert reviewer_calls == 0


@pytest.mark.asyncio
async def test_direct_edit_supersedes_pending_completion_review_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    await service.wait_for_completion_review_approval(
        goal.goal_id,
        "criterion-1",
        request_id="approval-1",
        reason="Judge tool approval is pending",
    )
    superseded: list[tuple[str, tuple[str, ...]]] = []

    class ApprovalService:
        async def supersede_goal_review_approvals(
            self,
            goal_id: str,
            request_ids: tuple[str, ...],
        ) -> int:
            superseded.append((goal_id, request_ids))
            return len(request_ids)

    monkeypatch.setattr(
        "swe.app.approvals.get_approval_service",
        ApprovalService,
    )

    edited = await service.request_edit(goal.goal_id, contract())

    assert edited.revision == 2
    assert superseded == [(goal.goal_id, ("approval-1",))]


@pytest.mark.asyncio
async def test_begin_turn_makes_a_direct_edit_pending_until_settlement() -> (
    None
):
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    await service.begin_turn(goal.goal_id)

    pending = await service.request_edit(goal.goal_id, contract())

    assert pending.revision == 1
    assert pending.control_commands[-1].status == "pending"


@pytest.mark.asyncio
async def test_affected_criteria_are_reviewed_before_the_next_continuation() -> (
    None
):
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    runtime = GoalRuntime(
        service,
        reviewer=lambda _: {"criterion-1": (True, "focused review")},
    )

    result = await runtime.settle(
        goal.goal_id,
        GoalTurnResolution(
            decision="continue",
            summary="Changed the checked output",
            affected_criteria=["criterion-1"],
        ),
    )

    assert result.state == GoalState.ACTIVE
    assert result.criteria[0].verified


@pytest.mark.asyncio
async def test_incremental_review_only_invokes_the_affected_criteria() -> None:
    service = GoalService(InMemoryGoalStore())
    two_criteria_contract = GoalContract(
        objective="Implement runtime",
        completion_criteria=[
            CompletionCriterion(
                requirement="First check",
                observable_assertion="first state",
                verification_method="command: first",
                expected_outcome="exit 0",
            ),
            CompletionCriterion(
                requirement="Second check",
                observable_assertion="second state",
                verification_method="command: second",
                expected_outcome="exit 0",
            ),
        ],
        constraints={"must_preserve": [], "must_not_do": []},
        autonomy_boundary="No deploy",
    )
    goal = await service.create_goal(
        scope=scope(),
        contract=two_criteria_contract,
    )
    observed_criteria: list[str] = []

    def reviewer(snapshot):
        observed_criteria.extend(
            item.criterion_id for item in snapshot.criteria
        )
        return {"criterion-1": (True, "focused review")}

    result = await GoalRuntime(service, reviewer=reviewer).settle(
        goal.goal_id,
        GoalTurnResolution(
            decision="continue",
            summary="Changed the first output",
            affected_criteria=["criterion-1"],
        ),
    )

    assert observed_criteria == ["criterion-1"]
    assert result.criteria[0].verified
    assert not result.criteria[1].verified


@pytest.mark.asyncio
async def test_completion_review_approval_waits_without_counting_a_failure() -> (
    None
):
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    runtime = GoalRuntime(
        service,
        reviewer=lambda _: {
            "criterion-1": CompletionReviewPending(
                request_id="approval-1",
                reason="completion review requires tool approval",
            ),
        },
    )

    result = await runtime.settle(
        goal.goal_id,
        GoalTurnResolution(
            decision="propose_completion",
            summary="Ready for verification",
            completion_proposal="Verify the change",
        ),
    )

    assert result.state == GoalState.WAITING
    assert result.criteria[0].consecutive_failures == 0
    assert result.criteria[0].verification_request_id == "approval-1"
    assert result.pending_review_criteria == ["criterion-1"]


@pytest.mark.asyncio
async def test_direct_edit_discards_a_pending_completion_review() -> None:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    reviewer_calls = 0

    def reviewer(_):
        nonlocal reviewer_calls
        reviewer_calls += 1
        return {
            "criterion-1": CompletionReviewPending(
                request_id="approval-1",
                reason="completion review requires tool approval",
            ),
        }

    runtime = GoalRuntime(service, reviewer=reviewer)
    await runtime.settle(
        goal.goal_id,
        GoalTurnResolution(
            decision="propose_completion",
            summary="Ready for review",
            completion_proposal="Verify the change",
        ),
    )
    edited = await service.request_edit(goal.goal_id, contract())

    result = await runtime.retry_pending_completion_review(goal.goal_id)

    assert edited.revision == 2
    assert result.state == GoalState.ACTIVE
    assert result.criteria[0].verified is False
    assert result.pending_review_criteria == []
    assert reviewer_calls == 1


@pytest.mark.asyncio
async def test_concurrent_pending_review_retries_record_one_rejection() -> (
    None
):
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    reviewer_calls = 0
    retry_started = asyncio.Event()
    allow_retry = asyncio.Event()

    async def reviewer(_):
        nonlocal reviewer_calls
        reviewer_calls += 1
        if reviewer_calls == 1:
            return {
                "criterion-1": CompletionReviewPending(
                    request_id="approval-1",
                    reason="completion review requires tool approval",
                ),
            }
        retry_started.set()
        await allow_retry.wait()
        return {"criterion-1": (False, "Completion Judge approval denied")}

    runtime = GoalRuntime(service, reviewer=reviewer)
    await runtime.settle(
        goal.goal_id,
        GoalTurnResolution(
            decision="propose_completion",
            summary="Ready for review",
            completion_proposal="Verify the change",
        ),
    )
    await service.wake(goal.goal_id, "Tool approval denied")

    first_retry = asyncio.create_task(
        runtime.retry_pending_completion_review(goal.goal_id),
    )
    await retry_started.wait()
    await runtime.retry_pending_completion_review(goal.goal_id)
    allow_retry.set()
    result = await first_retry

    assert reviewer_calls == 2
    assert result.criteria[0].consecutive_failures == 1


@pytest.mark.asyncio
async def test_approved_review_retries_without_another_main_agent_turn() -> (
    None
):
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    calls = 0

    def reviewer(_):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "criterion-1": CompletionReviewPending(
                    request_id="approval-1",
                    reason="completion review requires tool approval",
                ),
            }
        return {"criterion-1": (True, "approved review accepted")}

    runtime = GoalRuntime(service, reviewer=reviewer)
    waiting = await runtime.settle(
        goal.goal_id,
        GoalTurnResolution(
            decision="propose_completion",
            summary="Ready for review",
            completion_proposal="Verify the change",
        ),
    )
    await service.wake(goal.goal_id, "Tool approval approved")

    result = await runtime.retry_pending_completion_review(goal.goal_id)

    assert waiting.state == GoalState.WAITING
    assert result.state == GoalState.COMPLETE
    assert calls == 2


@pytest.mark.asyncio
async def test_denied_review_approval_records_a_rejection() -> None:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    calls = 0

    def reviewer(_):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "criterion-1": CompletionReviewPending(
                    request_id="approval-1",
                    reason="completion review requires tool approval",
                ),
            }
        return {"criterion-1": (False, "Completion Judge approval denied")}

    runtime = GoalRuntime(service, reviewer=reviewer)
    await runtime.settle(
        goal.goal_id,
        GoalTurnResolution(
            decision="propose_completion",
            summary="Ready for review",
            completion_proposal="Verify the change",
        ),
    )
    await service.wake(goal.goal_id, "Tool approval denied")

    result = await runtime.retry_pending_completion_review(goal.goal_id)

    assert result.state == GoalState.ACTIVE
    assert result.criteria[0].consecutive_failures == 1
    assert (
        result.state_reason
        == "review rejected: Completion Judge approval denied"
    )


@pytest.mark.asyncio
async def test_environment_write_without_declared_criteria_rechecks_all_criteria() -> (
    None
):
    service = GoalService(InMemoryGoalStore())
    two_criteria_contract = GoalContract(
        objective="Implement runtime",
        completion_criteria=[
            CompletionCriterion(
                requirement="First check",
                observable_assertion="first state",
                verification_method="command: first",
                expected_outcome="exit 0",
            ),
            CompletionCriterion(
                requirement="Second check",
                observable_assertion="second state",
                verification_method="command: second",
                expected_outcome="exit 0",
            ),
        ],
        constraints={"must_preserve": [], "must_not_do": []},
        autonomy_boundary="No deploy",
    )
    goal = await service.create_goal(
        scope=scope(),
        contract=two_criteria_contract,
    )
    observed: list[str] = []

    def reviewer(snapshot):
        observed.extend(item.criterion_id for item in snapshot.criteria)
        return {
            item.criterion_id: (True, "accepted") for item in snapshot.criteria
        }

    result = await GoalRuntime(service, reviewer=reviewer).settle(
        goal.goal_id,
        GoalTurnResolution(decision="continue", summary="Changed files"),
        environment_changed=True,
    )

    assert observed == ["criterion-1", "criterion-2"]
    assert all(item.verified for item in result.criteria)
