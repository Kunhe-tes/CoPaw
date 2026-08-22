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
from swe.app.goals.service import (
    GoalConflictError,
    GoalService,
    InMemoryGoalStore,
)


def contract(objective: str = "Deliver the report") -> GoalContract:
    return GoalContract(
        objective=objective,
        completion_criteria=[
            CompletionCriterion(
                requirement="The report exists",
                observable_assertion="report.md is present",
                verification_method="Read report.md",
                expected_outcome="The file has non-empty content",
            ),
        ],
        constraints={
            "must_preserve": ["existing customer data"],
            "must_not_do": ["delete customer data"],
        },
        autonomy_boundary="Ask before external publication.",
    )


def scope(chat_id: str = "chat-1") -> GoalScope:
    return GoalScope(
        tenant_id="tenant-1",
        source_id="source-1",
        agent_profile_id="agent-1",
        chat_id=chat_id,
        effective_model="model-1",
    )


@pytest.mark.asyncio
async def test_create_goal_rejects_a_second_non_terminal_goal_for_chat() -> None:
    service = GoalService(InMemoryGoalStore(), turn_budget=2)
    created = await service.create_goal(scope=scope(), contract=contract())

    assert created.state == GoalState.ACTIVE
    assert created.turn_budget == 2
    with pytest.raises(GoalConflictError, match="non-terminal"):
        await service.create_goal(scope=scope(), contract=contract("Other"))


@pytest.mark.asyncio
async def test_concurrent_goal_creation_keeps_one_non_terminal_goal_per_chat() -> None:
    class YieldingStore(InMemoryGoalStore):
        async def latest_for_chat(self, chat_id: str):
            await asyncio.sleep(0)
            return await super().latest_for_chat(chat_id)

        async def create(self, snapshot):
            await asyncio.sleep(0)
            return await super().create(snapshot)

    service = GoalService(YieldingStore())
    results = await asyncio.gather(
        service.create_goal(scope=scope(), contract=contract()),
        service.create_goal(scope=scope(), contract=contract("Other")),
        return_exceptions=True,
    )

    assert sum(not isinstance(item, Exception) for item in results) == 1
    assert sum(isinstance(item, GoalConflictError) for item in results) == 1


@pytest.mark.asyncio
async def test_settlement_applies_cancel_before_edit_and_pause() -> None:
    service = GoalService(InMemoryGoalStore(), turn_budget=2)
    goal = await service.create_goal(scope=scope(), contract=contract())
    await service.begin_turn(goal.goal_id)
    await service.request_control(goal.goal_id, GoalControlAction.PAUSE)
    await service.request_edit(goal.goal_id, contract("Edited"))
    await service.request_control(goal.goal_id, GoalControlAction.CANCEL)

    settled = await service.settle_turn(
        goal.goal_id,
        decision="continue",
        next_focus="Continue",
    )

    assert settled.state == GoalState.CANCELLED
    assert settled.revision == 1
    assert [command.status for command in settled.control_commands] == [
        "superseded",
        "superseded",
        "applied",
    ]


@pytest.mark.asyncio
async def test_edit_activates_new_revision_and_clears_evidence_without_resetting_budget() -> (
    None
):
    service = GoalService(InMemoryGoalStore(), turn_budget=3)
    goal = await service.create_goal(scope=scope(), contract=contract())
    await service.record_verification(goal.goal_id, "criterion-1", passed=True)
    await service.settle_turn(
        goal.goal_id,
        decision="continue",
        next_focus="finish",
    )
    await service.begin_turn(goal.goal_id)
    await service.request_edit(goal.goal_id, contract("Edited"))

    edited = await service.settle_turn(
        goal.goal_id,
        decision="continue",
        next_focus="ignored old resolution",
    )

    assert edited.revision == 2
    assert edited.contract.objective == "Edited"
    assert edited.turns_used == 2
    assert not edited.criteria[0].verified
    assert edited.next_focus is None


@pytest.mark.asyncio
async def test_resume_from_limited_resets_only_the_budget_cycle() -> None:
    service = GoalService(InMemoryGoalStore(), turn_budget=1)
    goal = await service.create_goal(scope=scope(), contract=contract())

    limited = await service.settle_turn(
        goal.goal_id,
        decision="continue",
        next_focus="more work",
    )
    assert limited.state == GoalState.LIMITED
    assert limited.turns_used == 1

    resumed = await service.resume(goal.goal_id)

    assert resumed.state == GoalState.ACTIVE
    assert resumed.budget_cycle == 2
    assert resumed.turns_used == 0
    assert resumed.revision == 1


@pytest.mark.asyncio
async def test_three_consecutive_failures_for_one_criterion_blocks_goal() -> None:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())

    for _ in range(3):
        goal = await service.record_verification(
            goal.goal_id,
            "criterion-1",
            passed=False,
            evidence_ref="test failure",
        )

    assert goal.state == GoalState.BLOCKED
    assert goal.criteria[0].consecutive_failures == 3


@pytest.mark.asyncio
async def test_edit_without_running_turn_applies_immediately_and_wakes_waiting_goal() -> (
    None
):
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    waiting = await service.settle_turn(
        goal.goal_id, decision="wait", next_focus="approval"
    )

    edited = await service.request_edit(waiting.goal_id, contract("Edited"))

    assert edited.revision == 2
    assert edited.state == GoalState.ACTIVE
    assert edited.contract.objective == "Edited"


@pytest.mark.asyncio
async def test_pause_without_running_turn_applies_immediately() -> None:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())

    paused = await service.request_control(goal.goal_id, GoalControlAction.PAUSE)

    assert paused.state == GoalState.PAUSED
    assert paused.control_commands[-1].status == "applied"


@pytest.mark.asyncio
async def test_terminal_goal_cannot_be_mutated_by_later_controls_or_edits() -> None:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    cancelled = await service.request_control(goal.goal_id, GoalControlAction.CANCEL)

    with pytest.raises(GoalConflictError, match="terminal"):
        await service.request_control(cancelled.goal_id, GoalControlAction.PAUSE)
    with pytest.raises(GoalConflictError, match="terminal"):
        await service.request_edit(cancelled.goal_id, contract("Changed"))


@pytest.mark.asyncio
async def test_steering_wakes_waiting_goal_and_is_consumed_in_order() -> None:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    await service.settle_turn(goal.goal_id, decision="wait", next_focus="approval")
    await service.enqueue_steering(goal.goal_id, "Use the approved endpoint")
    await service.enqueue_steering(goal.goal_id, "Keep existing data")

    current, messages = await service.consume_steering(goal.goal_id)

    assert current.state == GoalState.ACTIVE
    assert messages == ["Use the approved endpoint", "Keep existing data"]
    assert all(item.consumed for item in current.steering)


@pytest.mark.asyncio
async def test_steering_arriving_during_a_turn_prevents_a_stale_wait_state() -> None:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    await service.begin_turn(goal.goal_id)
    await service.enqueue_steering(goal.goal_id, "Continue with the new priority")

    settled = await service.settle_turn(
        goal.goal_id,
        decision="wait",
        next_focus="Wait for approval",
        wake_from_steering=await service.has_pending_steering(goal.goal_id),
    )

    assert settled.state == GoalState.ACTIVE
    assert settled.next_focus == "Wait for approval"
