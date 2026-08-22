from __future__ import annotations

import pytest

from swe.app.goals.models import CompletionCriterion, GoalContract, GoalScope, GoalState
from swe.app.goals.runtime import GoalRuntime, GoalTurnResolution
from swe.app.goals.service import GoalService, InMemoryGoalStore


def contract() -> GoalContract:
    return GoalContract(
        objective="Implement runtime",
        completion_criteria=[CompletionCriterion(
            requirement="Tests pass", observable_assertion="pytest exits 0",
            verification_method="Run pytest", expected_outcome="exit code 0",
        )], constraints={"must_preserve": [], "must_not_do": []}, autonomy_boundary="No deploy",
    )


def scope() -> GoalScope:
    return GoalScope(tenant_id="tenant", source_id="source", agent_profile_id="agent", chat_id="chat", effective_model="model")


@pytest.mark.asyncio
async def test_completion_proposal_requires_independent_verification_before_complete() -> None:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    runtime = GoalRuntime(service, verifier=lambda _: {"criterion-1": (True, "pytest passed")})

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

    result = await runtime.settle(goal.goal_id, GoalTurnResolution(decision="continue", summary="working", next_focus="write tests"))

    assert result.state == GoalState.ACTIVE
    assert result.next_focus == "write tests"


@pytest.mark.asyncio
async def test_pending_edit_discards_old_completion_proposal_before_verification() -> None:
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
