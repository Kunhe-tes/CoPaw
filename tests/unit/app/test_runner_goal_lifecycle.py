# -*- coding: utf-8 -*-
"""Runner-level Goal stream lifecycle regression tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from agentscope.message import Msg

from swe.agents.react_agent import SWEAgent as RealSWEAgent
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
async def test_explicit_goal_request_reports_when_goal_cannot_start_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, goal_id = await _goal_service()
    goal = await service.get(goal_id)
    goal.state = GoalState.PAUSED
    await service.persist(goal)
    monkeypatch.setattr("swe.app.goals.registry.get_goal_service", lambda: service)
    runner = AgentRunner(agent_id="agent-1", tenant_id="tenant-1")
    agent = SimpleNamespace(
        _request_context={"source_id": "source-1"},
    )
    runtime = SimpleNamespace(agent=agent, chat=SimpleNamespace(id="chat-1"))

    async def unexpected_turn(**_kwargs):
        raise AssertionError("a paused Goal must not begin a Main Agent turn")
        yield

    monkeypatch.setattr(runner, "_stream_agent_turns", unexpected_turn)
    events = [
        event
        async for event in runner._stream_completion_lifecycle(
            request=SimpleNamespace(channel_meta={"goal_id": goal_id}),
            runtime=runtime,
            plan=_TurnPlan(original_user_message="Continue Goal", turn_msgs=[]),
            outcome=_QueryTurnOutcome(),
        )
    ]

    assert [last for _, last in events] == [True]
    assert "PAUSED" in events[0][0].content
    assert "resume" in events[0][0].content.lower()
    assert (await service.get(goal_id)).state == GoalState.PAUSED


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
    captured: dict[str, Any] = {}

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


def test_goal_completion_judge_agent_is_restricted_and_model_frozen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = AgentRunner(agent_id="agent-1", tenant_id="tenant-1")
    captured: dict[str, Any] = {}
    frozen_provider = object()

    class FakeAgent:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    class FakeProviderManager:
        def get_provider(self, provider_id: str) -> object:
            assert provider_id == "provider-1"
            return frozen_provider

    monkeypatch.setattr("swe.app.runner.runner.SWEAgent", FakeAgent)
    monkeypatch.setattr(
        "swe.providers.provider_manager.ProviderManager.get_instance",
        lambda _tenant_id: FakeProviderManager(),
    )
    runtime = SimpleNamespace(
        agent=SimpleNamespace(
            _request_context={"chat_id": "chat-1", "turn_id": "turn-1"},
            _resolved_model_slot={"provider_id": "provider-1", "model": "model-1"},
        ),
        agent_config="agent-config",
    )

    created = runner._create_goal_completion_judge_agent(
        runtime=runtime,
        goal=SimpleNamespace(),
    )

    assert isinstance(created, FakeAgent)
    assert captured["request_context"] == {
        "chat_id": "chat-1",
        "turn_id": "turn-1",
        "agent_role": "completion_judge",
    }
    assert captured["enable_memory_manager"] is False
    assert captured["memory_manager"] is None
    assert captured["mcp_clients"] == []
    assert captured["enable_workspace_skills"] is False
    assert captured["task_tracker"] is None
    assert captured["source_tool_versions"] == ()
    assert captured["model_slot_override"].provider_id == "provider-1"
    assert captured["model_slot_override"].model == "model-1"
    assert captured["model_provider_override"] is frozen_provider
    prompt = captured["system_prompt_override"]
    assert '"reviews"' in prompt
    assert "one entry for every supplied criterion" in prompt.lower()
    assert "missing evidence" in prompt.lower()

    judge = object.__new__(RealSWEAgent)
    judge._agent_config = SimpleNamespace()
    judge._request_context = captured["request_context"]
    judge._workspace_dir = None
    assert set(judge._create_toolkit().tools) == {
        "read_file",
        "grep_search",
        "glob_search",
        "get_current_time",
    }


def test_goal_completion_judge_rejects_missing_frozen_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = AgentRunner(agent_id="agent-1", tenant_id="tenant-1")
    created = False

    class FakeAgent:
        def __init__(self, **_kwargs) -> None:
            nonlocal created
            created = True

    monkeypatch.setattr("swe.app.runner.runner.SWEAgent", FakeAgent)
    runtime = SimpleNamespace(
        agent=SimpleNamespace(
            _request_context={},
            _resolved_model_slot={"provider_id": "provider-1"},
        ),
        agent_config="agent-config",
    )

    with pytest.raises(RuntimeError, match="frozen model is unavailable"):
        runner._create_goal_completion_judge_agent(
            runtime=runtime,
            goal=SimpleNamespace(),
        )

    assert created is False


@pytest.mark.asyncio
async def test_goal_completion_reviewer_parses_hidden_judge_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, goal_id = await _goal_service()
    goal = await service.get(goal_id)
    runner = AgentRunner(agent_id="agent-1", tenant_id="tenant-1")
    captured: dict[str, Any] = {}

    class FakeJudge:
        def __call__(self, messages):
            captured["messages"] = messages

            async def run() -> None:
                return None

            return run()

    async def fake_stream_printing_messages(**kwargs):
        kwargs["coroutine_task"].close()
        yield Msg(
            name="Judge",
            role="assistant",
            content=(
                '{"reviews":[{"criterion_id":"criterion-1",'
                '"decision":"accept","reason":"Observed output",'
                '"evidence_refs":["tool-1"]}]}'
            ),
        ), True

    async def fake_enforce(stream, **_kwargs):
        async for item in stream:
            yield item

    monkeypatch.setattr(
        runner,
        "_create_goal_completion_judge_agent",
        lambda **_kwargs: FakeJudge(),
    )
    monkeypatch.setattr(
        "swe.app.runner.runner.stream_printing_messages",
        fake_stream_printing_messages,
    )
    monkeypatch.setattr(runner, "_enforce_query_timeout", fake_enforce)
    runtime = SimpleNamespace(
        agent=SimpleNamespace(
            _request_context={
                "_goal_turn_tool_observations": [
                    {"tool_name": "read_file", "output": "observed"},
                ],
            },
        ),
        session_id="session-1",
        chat=SimpleNamespace(id="chat-1"),
    )
    resolution = SimpleNamespace(
        completion_proposal="The result is ready",
        evidence_refs=["main-agent-evidence"],
    )

    reviewer = runner._create_goal_completion_reviewer(
        runtime=runtime,
        resolution=resolution,
    )
    result = await reviewer(goal)

    assert result == {"criterion-1": (True, "tool-1")}
    package = captured["messages"][0].content
    assert "The result is ready" in package
    assert "main-agent-evidence" in package
    assert "read_file" in package


def test_completion_judge_has_no_bootstrap_and_respects_profile_tools(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    (tmp_path / "BOOTSTRAP.md").write_text("bootstrap", encoding="utf-8")
    monkeypatch.setattr(
        "swe.config.config._default_builtin_tools",
        lambda: {
            "execute_shell_command": SimpleNamespace(
                enabled=True,
                async_execution=False,
            ),
            "read_file": SimpleNamespace(enabled=True),
        },
    )
    judge = object.__new__(RealSWEAgent)
    judge._agent_config = SimpleNamespace(tools=None)
    judge._request_context = {"agent_role": "completion_judge"}
    judge._workspace_dir = tmp_path
    judge._language = "en"
    judge._enable_memory_manager = False
    judge.memory_manager = None
    registered_hooks: list[dict[str, object]] = []
    judge.register_instance_hook = lambda **kwargs: registered_hooks.append(kwargs)

    judge._register_hooks()

    assert registered_hooks == []
    assert not (tmp_path / ".bootstrap_completed").exists()
    assert set(judge._create_toolkit().tools) == {"read_file"}


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
