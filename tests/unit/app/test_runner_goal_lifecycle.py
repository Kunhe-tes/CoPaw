"""Runner-level Goal stream lifecycle regression tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from agentscope.message import Msg

from swe.app.goals.models import CompletionCriterion, GoalContract, GoalScope, GoalState
from swe.app.goals.service import GoalService, InMemoryGoalStore
from swe.app.runner.runner import (
    AgentRunner,
    _QueryTurnOutcome,
    _TurnPlan,
    _build_goal_contract_context,
)


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
    runner = AgentRunner(agent_id="agent-1", tenant_id="tenant-1")
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
            "source_id": "source-1",
        },
    )
    runtime = SimpleNamespace(agent=agent, chat=SimpleNamespace(id="chat-1"))
    calls = 0

    async def fake_stream_agent_turns(**_kwargs):
        nonlocal calls
        agent._request_context["goal_turn_resolution"] = resolutions[calls]
        calls += 1
        yield Msg(name="Friday", role="assistant", content=f"turn-{calls}"), True

    async def fake_wait_for_goal_wake(waiting_goal_id: str) -> None:
        assert waiting_goal_id == goal_id
        await service.wake(goal_id, "User steering received")

    async def fake_finalization_turn(**_kwargs):
        yield Msg(
            name="Friday",
            role="assistant",
            content="Formal completion delivery from the Main Agent.",
        ), True

    monkeypatch.setattr(runner, "_stream_agent_turns", fake_stream_agent_turns)
    monkeypatch.setattr(
        "swe.app.goals.wakeup.wait_for_goal_wake",
        fake_wait_for_goal_wake,
    )
    monkeypatch.setattr(runner, "_stream_goal_finalization_turn", fake_finalization_turn)

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
    assert events[-1][0].content == "Formal completion delivery from the Main Agent."


@pytest.mark.asyncio
async def test_goal_finalization_falls_back_when_model_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, goal_id = await _goal_service()
    monkeypatch.setattr("swe.app.goals.registry.get_goal_service", lambda: service)
    runner = AgentRunner(agent_id="agent-1", tenant_id="tenant-1")
    goal = await service.get(goal_id)
    goal.state = GoalState.COMPLETE
    await service.persist(goal)

    def fail_to_create_agent(**_kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(runner, "_create_goal_finalization_agent", fail_to_create_agent)
    events = [
        event
        async for event in runner._stream_goal_finalization_turn(
            runtime=SimpleNamespace(
                agent=SimpleNamespace(_request_context={}),
                agent_config=None,
                session_id="session-1",
                chat=SimpleNamespace(id="chat-1"),
            ),
            goal=goal,
        )
    ]
    assert len(events) == 1
    assert events[0][1] is True
    assert "Goal verification passed" in events[0][0].content


@pytest.mark.asyncio
async def test_goal_finalization_persists_the_final_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, goal_id = await _goal_service()
    goal = await service.get(goal_id)
    goal.state = GoalState.COMPLETE
    await service.persist(goal)
    runner = AgentRunner(agent_id="agent-1", tenant_id="tenant-1")
    persisted: list[Msg] = []

    class Memory:
        async def add(self, msg: Msg) -> None:
            persisted.append(msg)

    class FinalizationAgent:
        async def __call__(self, _msgs):
            return None

    async def fake_stream_printing_messages(**kwargs):
        kwargs["coroutine_task"].close()
        yield Msg(name="Friday", role="assistant", content="Final delivery") , True

    async def fake_enforce(stream, **_kwargs):
        async for event in stream:
            yield event

    monkeypatch.setattr(
        runner,
        "_create_goal_finalization_agent",
        lambda **_kwargs: FinalizationAgent(),
    )
    monkeypatch.setattr(
        "swe.app.runner.runner.stream_printing_messages",
        fake_stream_printing_messages,
    )
    monkeypatch.setattr(runner, "_enforce_query_timeout", fake_enforce)

    events = [
        event
        async for event in runner._stream_goal_finalization_turn(
            runtime=SimpleNamespace(
                agent=SimpleNamespace(_request_context={}, memory=Memory()),
                agent_config=None,
                session_id="session-1",
                chat=SimpleNamespace(id="chat-1"),
            ),
            goal=goal,
        )
    ]

    assert [msg.content for msg in persisted] == ["Final delivery"]
    assert events[-1][1] is True


@pytest.mark.asyncio
async def test_interrupted_goal_after_wake_does_not_finalize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, goal_id = await _goal_service()
    monkeypatch.setattr("swe.app.goals.registry.get_goal_service", lambda: service)
    runner = AgentRunner(agent_id="agent-1", tenant_id="tenant-1")
    agent = SimpleNamespace(
        _request_context={"goal_verifier": lambda _goal: {}, "source_id": "source-1"},
    )
    runtime = SimpleNamespace(agent=agent, chat=SimpleNamespace(id="chat-1"))

    async def fake_stream_agent_turns(**_kwargs):
        agent._request_context["goal_turn_resolution"] = {
            "decision": "wait",
            "summary": "Waiting",
            "wake_conditions": ["manual wake"],
        }
        yield Msg(name="Friday", role="assistant", content="waiting"), True

    async def fake_wait_for_goal_wake(_goal_id: str) -> None:
        goal = await service.get(goal_id)
        goal.state = GoalState.INTERRUPTED
        await service.persist(goal)

    async def unexpected_finalization(**_kwargs):
        raise AssertionError("INTERRUPTED must not start Finalization Turn")
        yield

    monkeypatch.setattr(runner, "_stream_agent_turns", fake_stream_agent_turns)
    monkeypatch.setattr(
        "swe.app.goals.wakeup.wait_for_goal_wake",
        fake_wait_for_goal_wake,
    )
    monkeypatch.setattr(runner, "_stream_goal_finalization_turn", unexpected_finalization)

    events = [
        event
        async for event in runner._stream_completion_lifecycle(
            request=SimpleNamespace(channel_meta={"goal_id": goal_id}),
            runtime=runtime,
            plan=_TurnPlan(original_user_message="Start Goal", turn_msgs=[]),
            outcome=_QueryTurnOutcome(),
        )
    ]

    assert [last for _, last in events] == [False]


def test_goal_finalization_agent_is_tool_free(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = AgentRunner(agent_id="agent-1", tenant_id="tenant-1")
    captured: dict[str, object] = {}

    class FakeAgent:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("swe.app.runner.runner.SWEAgent", FakeAgent)
    runtime = SimpleNamespace(
        agent=SimpleNamespace(
            _request_context={
                "session_id": "session-1",
                "user_id": "user-1",
                "channel": "console",
                "chat_id": "chat-1",
                "turn_id": "turn-1",
            },
        ),
        agent_config="agent-config",
    )
    created = runner._create_goal_finalization_agent(
        runtime=runtime,
        goal=SimpleNamespace(),
    )

    assert isinstance(created, FakeAgent)
    assert captured["enable_memory_manager"] is False
    assert captured["mcp_clients"] == []
    assert captured["source_tool_versions"] == ()
    assert captured["request_context"]["goal_finalization"] is True
    assert "only the final concise user-facing response" in captured[
        "system_prompt_override"
    ]


@pytest.mark.asyncio
async def test_goal_stream_rejects_a_goal_from_another_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, goal_id = await _goal_service()
    monkeypatch.setattr("swe.app.goals.registry.get_goal_service", lambda: service)
    runner = AgentRunner(agent_id="agent-1", tenant_id="tenant-1")
    agent = SimpleNamespace(
        _request_context={
            "goal_verifier": lambda _goal: {"criterion-1": (True, "passed")},
            "source_id": "source-1",
        },
    )
    runtime = SimpleNamespace(agent=agent, chat=SimpleNamespace(id="other-chat"))

    async def unexpected_turn(**_kwargs):
        raise AssertionError("foreign Goal must not begin a Main Agent turn")
        yield

    monkeypatch.setattr(runner, "_stream_agent_turns", unexpected_turn)
    events = [
        event
        async for event in runner._stream_completion_lifecycle(
            request=SimpleNamespace(channel_meta={"goal_id": goal_id}),
            runtime=runtime,
            plan=_TurnPlan(original_user_message="Start Goal", turn_msgs=[]),
            outcome=_QueryTurnOutcome(),
        )
    ]

    assert [last for _, last in events] == [True]
    assert "not available" in events[0][0].content


@pytest.mark.asyncio
async def test_goal_continuation_context_includes_the_full_active_contract() -> None:
    service, goal_id = await _goal_service()
    goal = await service.get(goal_id)

    context = _build_goal_contract_context(goal)

    assert "Requirement: Tests pass" in context
    assert "Observable assertion: pytest succeeds" in context
    assert "Verification method: command: pytest -q" in context
    assert "Expected outcome: exit 0" in context
    assert "must_preserve: none" in context
    assert "must_not_do: none" in context
    assert "Autonomy boundary: No deployment" in context


@pytest.mark.asyncio
async def test_goal_stream_retries_approved_verification_before_next_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, goal_id = await _goal_service()
    monkeypatch.setattr("swe.app.goals.registry.get_goal_service", lambda: service)
    runner = AgentRunner(agent_id="agent-1", tenant_id="tenant-1")
    verifier_calls = 0

    async def verifier(_goal):
        nonlocal verifier_calls
        verifier_calls += 1
        if verifier_calls == 1:
            from swe.app.goals.runtime import VerificationPending

            return {
                "criterion-1": VerificationPending(
                    request_id="approval-1",
                    reason="verification command requires tool approval",
                ),
            }
        return {"criterion-1": (True, "approved verification passed")}

    agent = SimpleNamespace(
        _request_context={"goal_verifier": verifier, "source_id": "source-1"},
    )
    runtime = SimpleNamespace(agent=agent, chat=SimpleNamespace(id="chat-1"))
    turns = 0

    async def fake_stream_agent_turns(**_kwargs):
        nonlocal turns
        turns += 1
        agent._request_context["goal_turn_resolution"] = {
            "decision": "propose_completion",
            "summary": "Ready for verification",
            "completion_proposal": "Verify the result",
        }
        yield Msg(name="Friday", role="assistant", content="turn"), True

    async def fake_wait_for_goal_wake(waiting_goal_id: str) -> None:
        assert waiting_goal_id == goal_id
        await service.wake(goal_id, "Tool approval approved")

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

    assert turns == 1
    assert verifier_calls == 2
    assert events[-1][0].content.startswith("Goal verification passed")


@pytest.mark.asyncio
async def test_interrupted_goal_does_not_emit_a_finalization_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, goal_id = await _goal_service()
    monkeypatch.setattr("swe.app.goals.registry.get_goal_service", lambda: service)
    runner = AgentRunner(agent_id="agent-1", tenant_id="tenant-1")
    agent = SimpleNamespace(
        _request_context={"goal_verifier": lambda _: {}, "source_id": "source-1"},
    )
    runtime = SimpleNamespace(agent=agent, chat=SimpleNamespace(id="chat-1"))
    outcome = _QueryTurnOutcome(pre_tool_terminal_stop=True)

    async def fake_stream_agent_turns(**_kwargs):
        yield Msg(name="Friday", role="assistant", content="partial"), True

    monkeypatch.setattr(runner, "_stream_agent_turns", fake_stream_agent_turns)
    events = [
        event
        async for event in runner._stream_completion_lifecycle(
            request=SimpleNamespace(channel_meta={"goal_id": goal_id}),
            runtime=runtime,
            plan=_TurnPlan(original_user_message="Start Goal", turn_msgs=[]),
            outcome=outcome,
        )
    ]

    assert [event[0].content for event in events] == ["partial"]
    assert (await service.get(goal_id)).state.value == "INTERRUPTED"
