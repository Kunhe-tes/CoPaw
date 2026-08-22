"""Runner-level Goal stream lifecycle regression tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from agentscope.message import Msg

from swe.app.goals.models import CompletionCriterion, GoalContract, GoalScope
from swe.app.goals.service import GoalService, InMemoryGoalStore
from swe.app.runner.runner import AgentRunner, _QueryTurnOutcome, _TurnPlan


def _contract() -> GoalContract:
    return GoalContract(
        objective="Finish the change",
        completion_criteria=[
            CompletionCriterion(
                requirement="Tests pass",
                observable_assertion="pytest succeeds",
                verification_method="command: pytest -q",
                expected_outcome="exit 0",
            ),
        ],
        constraints={"must_preserve": [], "must_not_do": []},
        autonomy_boundary="No deployment",
    )


async def _goal_service() -> tuple[GoalService, str]:
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(
        scope=GoalScope(
            tenant_id="tenant-1",
            source_id="source-1",
            agent_profile_id="agent-1",
            chat_id="chat-1",
            effective_model="model-1",
        ),
        contract=_contract(),
    )
    return service, goal.goal_id


@pytest.mark.asyncio
async def test_goal_stream_keeps_intermediate_turns_open_and_wakes_from_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, goal_id = await _goal_service()
    monkeypatch.setattr("swe.app.goals.registry.get_goal_service", lambda: service)
    runner = AgentRunner()
    resolutions = [
        {
            "decision": "wait",
            "summary": "Waiting for user input",
            "wake_conditions": ["user steering"],
        },
        {
            "decision": "propose_completion",
            "summary": "Completed after wake",
            "completion_proposal": "Verify the completed change",
        },
    ]
    agent = SimpleNamespace(
        _request_context={
            "goal_verifier": lambda _goal: {"criterion-1": (True, "passed")},
        },
    )
    runtime = SimpleNamespace(agent=agent)
    calls = 0

    async def fake_stream_agent_turns(**_kwargs):
        nonlocal calls
        agent._request_context["goal_turn_resolution"] = resolutions[calls]
        calls += 1
        yield Msg(name="Friday", role="assistant", content=f"turn-{calls}"), True

    async def fake_wait_for_goal_wake(waiting_goal_id: str) -> None:
        assert waiting_goal_id == goal_id
        await service.wake(goal_id, "User steering received")

    monkeypatch.setattr(runner, "_stream_agent_turns", fake_stream_agent_turns)
    monkeypatch.setattr(
        "swe.app.goals.wakeup.wait_for_goal_wake",
        fake_wait_for_goal_wake,
    )

    events = [
        event
        async for event in runner._stream_completion_lifecycle(
            request=SimpleNamespace(channel_meta={"goal_id": goal_id}),
            runtime=runtime,
            plan=_TurnPlan(original_user_message="Start Goal", turn_msgs=[]),
            outcome=_QueryTurnOutcome(),
        )
    ]

    assert calls == 2
    assert [last for _, last in events] == [False, False, True]
    assert events[-1][0].content.startswith("Goal verification passed")
