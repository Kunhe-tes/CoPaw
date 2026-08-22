from __future__ import annotations

import pytest

from swe.app.goals.models import CompletionCriterion, GoalContract, GoalScope, GoalState
from swe.app.goals.runtime import (
    GoalRuntime,
    GoalTurnResolution,
    VerificationPending,
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
            )
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
async def test_completion_proposal_requires_independent_verification_before_complete() -> (
    None
):
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    runtime = GoalRuntime(
        service, verifier=lambda _: {"criterion-1": (True, "pytest passed")}
    )

    result = await runtime.settle(
        goal.goal_id,
        GoalTurnResolution(
            decision="propose_completion",
            summary="done",
            next_focus=None,
            evidence_refs=["pytest passed"],
            completion_proposal="Report is ready for verification",
        ),
    )

    assert result.state == GoalState.COMPLETE
    assert result.criteria[0].verified


@pytest.mark.asyncio
async def test_non_completion_resolution_keeps_the_goal_active_for_next_turn() -> None:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    runtime = GoalRuntime(service, verifier=lambda _: {})

    result = await runtime.settle(
        goal.goal_id,
        GoalTurnResolution(
            decision="continue", summary="working", next_focus="write tests"
        ),
    )

    assert result.state == GoalState.ACTIVE
    assert result.next_focus == "write tests"


@pytest.mark.asyncio
async def test_pending_edit_discards_old_completion_proposal_before_verification() -> (
    None
):
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    await service.begin_turn(goal.goal_id)
    await service.request_edit(goal.goal_id, contract())
    verifier_calls = 0

    def verifier(_):
        nonlocal verifier_calls
        verifier_calls += 1
        return {"criterion-1": (True, "stale pass")}

    result = await GoalRuntime(service, verifier=verifier).settle(
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
    assert verifier_calls == 0


@pytest.mark.asyncio
async def test_begin_turn_makes_a_direct_edit_pending_until_settlement() -> None:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    await service.begin_turn(goal.goal_id)

    pending = await service.request_edit(goal.goal_id, contract())

    assert pending.revision == 1
    assert pending.control_commands[-1].status == "pending"


@pytest.mark.asyncio
async def test_affected_criteria_are_verified_before_the_next_continuation() -> None:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    runtime = GoalRuntime(
        service,
        verifier=lambda _: {"criterion-1": (True, "focused verification")},
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
async def test_incremental_verification_only_invokes_the_affected_criteria() -> None:
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
    goal = await service.create_goal(scope=scope(), contract=two_criteria_contract)
    observed_criteria: list[str] = []

    def verifier(snapshot):
        observed_criteria.extend(item.criterion_id for item in snapshot.criteria)
        return {"criterion-1": (True, "focused verification")}

    result = await GoalRuntime(service, verifier=verifier).settle(
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
async def test_verification_approval_waits_without_counting_a_failure() -> None:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    runtime = GoalRuntime(
        service,
        verifier=lambda _: {
            "criterion-1": VerificationPending(
                request_id="approval-1",
                reason="verification command requires tool approval",
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


@pytest.mark.asyncio
async def test_approved_verification_retries_without_another_main_agent_turn() -> None:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    calls = 0

    def verifier(_):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "criterion-1": VerificationPending(
                    request_id="approval-1",
                    reason="verification command requires tool approval",
                ),
            }
        return {"criterion-1": (True, "approved verification passed")}

    runtime = GoalRuntime(service, verifier=verifier)
    waiting = await runtime.settle(
        goal.goal_id,
        GoalTurnResolution(
            decision="propose_completion",
            summary="Ready for verification",
            completion_proposal="Verify the change",
        ),
    )
    await service.wake(goal.goal_id, "Tool approval approved")

    result = await runtime.retry_pending_verification(goal.goal_id)

    assert waiting.state == GoalState.WAITING
    assert result.state == GoalState.COMPLETE
    assert calls == 2


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
    goal = await service.create_goal(scope=scope(), contract=two_criteria_contract)
    observed: list[str] = []

    def verifier(snapshot):
        observed.extend(item.criterion_id for item in snapshot.criteria)
        return {item.criterion_id: (True, "verified") for item in snapshot.criteria}

    result = await GoalRuntime(service, verifier=verifier).settle(
        goal.goal_id,
        GoalTurnResolution(decision="continue", summary="Changed files"),
        environment_changed=True,
    )

    assert observed == ["criterion-1", "criterion-2"]
    assert all(item.verified for item in result.criteria)
