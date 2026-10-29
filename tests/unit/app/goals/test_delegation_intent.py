# -*- coding: utf-8 -*-
"""Goal delegation authority is durable and comes only from user input."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
import asyncio

import pytest

from swe.app.goals.models import GoalSnapshot
from swe.app.goals.router import CreateGoalRequest
from swe.app.goals.service import GoalService, InMemoryGoalStore
from swe.app.runner import turn_lifecycle
from swe.app.source_system_config.models import (
    EffectiveSourceSystemConfig,
    SourceSystemConfig,
)
from swe.app.source_system_config.runtime import (
    get_current_source_system_config,
)
from tests.unit.app.goals.test_service import contract, scope


@pytest.mark.asyncio
async def test_goal_creation_persists_structured_intent_and_legacy_defaults():
    store = InMemoryGoalStore()
    service = GoalService(store)
    goal = await service.create_goal(
        scope=scope(),
        contract=contract(),
        enable_subagents=True,
    )
    restored = GoalSnapshot.model_validate_json(goal.model_dump_json())
    assert restored.subagent_delegation_enabled is True
    legacy = goal.model_dump()
    legacy.pop("subagent_delegation_enabled")
    assert (
        GoalSnapshot.model_validate(legacy).subagent_delegation_enabled
        is False
    )
    other = await service.create_goal(
        scope=scope("other-chat"),
        contract=contract("使用子代理"),
    )
    assert other.subagent_delegation_enabled is False


def test_create_request_accepts_optional_structured_delegation():
    body = {"chat_id": "chat-1", "contract": contract().model_dump()}
    assert CreateGoalRequest(**body).enable_subagents is False
    assert (
        CreateGoalRequest(**body, enable_subagents=True).enable_subagents
        is True
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,enabled",
    [("请用子代理", False), ("Continue", True)],
)
async def test_steering_promotes_and_preserves_goal_intent(text, enabled):
    store = InMemoryGoalStore()
    service = GoalService(store)
    goal = await service.create_goal(scope=scope(), contract=contract())
    await service.enqueue_steering(
        goal.goal_id,
        text,
        enable_subagents=enabled,
    )
    restored = GoalService(store)
    assert (
        await restored.get(goal.goal_id)
    ).subagent_delegation_enabled is True
    await restored.enqueue_steering(goal.goal_id, "Continue")
    assert (
        await restored.get(goal.goal_id)
    ).subagent_delegation_enabled is True


@pytest.mark.asyncio
async def test_begin_turn_persists_true_without_downgrading_restored_intent():
    store = InMemoryGoalStore()
    service = GoalService(store)
    goal = await service.create_goal(scope=scope(), contract=contract())
    begun = await service.begin_turn(goal.goal_id, enable_subagents=True)
    assert begun.subagent_delegation_enabled is True
    await service.abandon_turn(goal.goal_id, "restart")
    await service.resume(goal.goal_id)
    restored = await GoalService(store).begin_turn(goal.goal_id)
    assert restored.subagent_delegation_enabled is True


@pytest.mark.asyncio
async def test_prepare_goal_turn_restores_intent_and_refreshes_latest_source():
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(
        scope=scope(),
        contract=contract(),
        enable_subagents=True,
    )
    effective = EffectiveSourceSystemConfig(
        source_id="source-1",
        config=SourceSystemConfig.model_validate({}),
    )
    resolver = SimpleNamespace(
        resolve_config=AsyncMock(return_value=effective),
    )
    refreshed = []
    agent = SimpleNamespace(_request_context={"enable_subagents": False})
    agent.refresh_background_subagent_tools = lambda: refreshed.append(
        (
            agent._request_context["enable_subagents"],
            get_current_source_system_config().source_id,
        ),
    )
    owner = SimpleNamespace(
        _workspace=SimpleNamespace(_source_system_config_service=resolver),
        _build_goal_contract_context=lambda _: "contract",
    )
    await turn_lifecycle._prepare_goal_turn_context(
        owner,
        runtime=SimpleNamespace(agent=agent),
        goal=goal,
    )
    assert refreshed == [(True, "source-1")]
    resolver.resolve_config.assert_awaited_once_with(
        "source-1",
        force_refresh=True,
    )


@pytest.mark.asyncio
async def test_runner_begin_turn_promotes_real_input_and_restore_keeps_it(
    monkeypatch,
):
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(
        scope=scope(),
        contract=contract("subagent"),
    )
    monkeypatch.setattr(
        "swe.app.goals.registry.get_goal_service",
        lambda: service,
    )
    owner = SimpleNamespace(_goal_matches_runtime_scope=lambda *_: True)
    runtime = SimpleNamespace(
        agent=SimpleNamespace(
            _request_context={
                "current_user_text": "请用子代理",
                "msgid": "message-1",
            },
        ),
    )
    _, begun = await turn_lifecycle._begin_goal_turn(
        owner,
        goal_id=goal.goal_id,
        runtime=runtime,
    )
    assert begun.subagent_delegation_enabled is True
    await service.abandon_turn(goal.goal_id, "process restart")
    await service.resume(goal.goal_id)
    runtime.agent._request_context = {"current_user_text": "继续Goal"}
    _, restored = await turn_lifecycle._begin_goal_turn(
        owner,
        goal_id=goal.goal_id,
        runtime=runtime,
    )
    assert restored.subagent_delegation_enabled is True


@pytest.mark.asyncio
async def test_create_route_passes_structured_intent(monkeypatch):
    from swe.app.goals import router as router_module

    service = GoalService(InMemoryGoalStore())
    monkeypatch.setattr(
        router_module,
        "_service",
        AsyncMock(return_value=service),
    )
    monkeypatch.setattr(
        router_module,
        "_chat",
        AsyncMock(return_value=SimpleNamespace(id="chat-1")),
    )
    monkeypatch.setattr(router_module, "_scope", lambda *_a, **_kw: scope())
    created = await router_module.create_goal(
        CreateGoalRequest(
            chat_id="chat-1",
            contract=contract(),
            enable_subagents=True,
        ),
        SimpleNamespace(state=SimpleNamespace()),
        workspace=SimpleNamespace(),
    )
    assert created.subagent_delegation_enabled is True


@pytest.mark.asyncio
async def test_create_route_consumes_server_owned_goal_draft_intent(
    monkeypatch,
):
    from swe.app.goals import router as router_module

    service = GoalService(InMemoryGoalStore())
    chat = SimpleNamespace(
        id="chat-1",
        meta={
            "goal_draft_subagent_delegation_enabled": True,
            "other": "preserved",
        },
    )
    manager = SimpleNamespace(update_chat=AsyncMock())
    monkeypatch.setattr(
        router_module,
        "_service",
        AsyncMock(return_value=service),
    )
    monkeypatch.setattr(router_module, "_chat", AsyncMock(return_value=chat))
    monkeypatch.setattr(router_module, "_scope", lambda *_a, **_kw: scope())
    created = await router_module.create_goal(
        CreateGoalRequest(chat_id="chat-1", contract=contract()),
        SimpleNamespace(state=SimpleNamespace()),
        workspace=SimpleNamespace(chat_manager=manager),
    )
    assert created.subagent_delegation_enabled is True
    assert chat.meta == {"other": "preserved"}
    manager.update_chat.assert_awaited_once_with(chat)


@pytest.mark.asyncio
async def test_goal_json_store_round_trip_preserves_delegation():
    from tests.unit.app.goals.test_store import FakeDb
    from swe.app.goals.store import MySqlGoalStore

    db = FakeDb()
    store = MySqlGoalStore(db)
    goal = await GoalService(store).create_goal(
        scope=scope(),
        contract=contract(),
        enable_subagents=True,
    )
    assert any(
        "subagent_delegation_enabled" in str(params)
        for _, params in db.executed
    )
    db.rows.append({"snapshot_json": goal.model_dump_json()})
    assert (
        await MySqlGoalStore(db).get(goal.goal_id)
    ).subagent_delegation_enabled is True


def test_steering_request_accepts_structured_delegation():
    from swe.app.goals.router import SteeringRequest

    assert SteeringRequest(content="Continue").enable_subagents is False
    assert (
        SteeringRequest(
            content="Continue",
            enable_subagents=True,
        ).enable_subagents
        is True
    )


@pytest.mark.asyncio
async def test_steering_route_passes_structured_intent(monkeypatch):
    from swe.app.goals import router as router_module

    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    monkeypatch.setattr(
        router_module,
        "_service",
        AsyncMock(return_value=service),
    )
    monkeypatch.setattr(
        router_module,
        "_owned_goal",
        AsyncMock(return_value=goal),
    )
    updated = await router_module.enqueue_goal_steering(
        goal.goal_id,
        router_module.SteeringRequest(
            content="Continue",
            enable_subagents=True,
        ),
        SimpleNamespace(),
        workspace=SimpleNamespace(),
        chat_id="chat-1",
    )
    assert updated.subagent_delegation_enabled is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,enabled",
    [("使用子智能体", False), ("Continue", True)],
)
async def test_implicit_steering_promotes_actual_user_intent(
    monkeypatch,
    text,
    enabled,
):
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    monkeypatch.setattr(
        "swe.app.goals.registry.get_goal_service",
        lambda: service,
    )
    runtime = SimpleNamespace(
        chat=SimpleNamespace(id="chat-1"),
        agent=SimpleNamespace(_request_context={"enable_subagents": enabled}),
    )
    result = await turn_lifecycle._resolve_implicit_goal_steering(
        SimpleNamespace(_goal_matches_runtime_scope=lambda *_: True),
        goal_id=None,
        runtime=runtime,
        plan=SimpleNamespace(original_user_message=text),
    )
    assert result is not None
    assert (
        await service.get(goal.goal_id)
    ).subagent_delegation_enabled is True


@pytest.mark.asyncio
async def test_runner_does_not_infer_intent_from_generated_contract(
    monkeypatch,
):
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(
        scope=scope(),
        contract=contract("Use subagent"),
    )
    monkeypatch.setattr(
        "swe.app.goals.registry.get_goal_service",
        lambda: service,
    )
    runtime = SimpleNamespace(
        agent=SimpleNamespace(
            _request_context={
                "current_user_text": "Continue",
                "goal_contract_context": "Use subagent",
            },
        ),
    )
    _, begun = await turn_lifecycle._begin_goal_turn(
        SimpleNamespace(_goal_matches_runtime_scope=lambda *_: True),
        goal_id=goal.goal_id,
        runtime=runtime,
    )
    assert begun.subagent_delegation_enabled is False


@pytest.mark.asyncio
async def test_goal_turn_refresh_reloads_source_config_each_time():
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(
        scope=scope(),
        contract=contract(),
        enable_subagents=True,
    )
    configs = [
        EffectiveSourceSystemConfig(
            source_id="source-1",
            version=version,
            config=SourceSystemConfig.model_validate({}),
        )
        for version in (1, 2)
    ]
    resolver = SimpleNamespace(resolve_config=AsyncMock(side_effect=configs))
    versions = []
    agent = SimpleNamespace(_request_context={})
    agent.refresh_background_subagent_tools = lambda: versions.append(
        get_current_source_system_config().version,
    )
    owner = SimpleNamespace(
        _workspace=SimpleNamespace(_source_system_config_service=resolver),
        _build_goal_contract_context=lambda _: "contract",
    )
    for _ in range(2):
        await turn_lifecycle._prepare_goal_turn_context(
            owner,
            runtime=SimpleNamespace(agent=agent),
            goal=goal,
        )
    assert versions == [1, 2]
    assert resolver.resolve_config.await_count == 2


@pytest.mark.asyncio
async def test_goal_turn_refresh_supports_owner_without_workspace():
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    refreshed = []
    agent = SimpleNamespace(_request_context={})
    agent.refresh_background_subagent_tools = lambda: refreshed.append(True)
    await turn_lifecycle._prepare_goal_turn_context(
        SimpleNamespace(_build_goal_contract_context=lambda _: "contract"),
        runtime=SimpleNamespace(agent=agent),
        goal=goal,
    )
    assert refreshed == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [RuntimeError("Source unavailable"), asyncio.CancelledError()],
)
async def test_goal_context_failure_releases_begun_turn(monkeypatch, error):
    service = GoalService(InMemoryGoalStore())
    goal = await service.create_goal(scope=scope(), contract=contract())
    monkeypatch.setattr(
        "swe.app.goals.registry.get_goal_service",
        lambda: service,
    )
    monkeypatch.setattr(
        turn_lifecycle,
        "_prepare_goal_turn_context",
        AsyncMock(side_effect=error),
    )
    runtime = SimpleNamespace(agent=SimpleNamespace(_request_context={}))
    with pytest.raises(type(error)):
        async for _ in turn_lifecycle._stream_goal_completion_lifecycle(
            SimpleNamespace(_goal_matches_runtime_scope=lambda *_: True),
            request=SimpleNamespace(),
            goal_id=goal.goal_id,
            runtime=runtime,
            plan=SimpleNamespace(),
            outcome=SimpleNamespace(),
        ):
            pass
    restored = await service.get(goal.goal_id)
    assert restored.turn_active is False
    assert restored.state.value == "INTERRUPTED"


@pytest.mark.asyncio
async def test_goal_draft_preserves_initial_intent_across_clarification_and_restart():
    from swe.app.runner.runner import AgentRunner
    from tests.unit.app.test_runner_plan_mode_state import _InMemoryChatRepo
    from swe.app.runner.manager import ChatManager
    from swe.app.runner.models import ChatSpec

    repo = _InMemoryChatRepo()
    manager = ChatManager(repo=repo)
    chat = await manager.create_chat(
        ChatSpec(
            id="chat-1",
            session_id="session-1",
            user_id="user-1",
            channel="console",
        ),
    )
    runner = AgentRunner(agent_id="agent-1")
    runner.set_chat_manager(manager)
    request = SimpleNamespace(channel_meta={"goal_mode_enabled": True})
    await runner._update_goal_draft_delegation(
        {
            "request": request,
            "chat": chat,
            "current_user_text": "请用子代理完成任务",
        },
    )
    restored = await manager.get_chat(chat.id)
    assert restored.meta["goal_draft_subagent_delegation_enabled"] is True
    restarted = AgentRunner(agent_id="agent-1")
    restarted.set_chat_manager(manager)
    await restarted._update_goal_draft_delegation(
        {
            "request": request,
            "chat": restored,
            "current_user_text": "A",
        },
    )
    assert restored.meta["goal_draft_subagent_delegation_enabled"] is True
    restarted.session = SimpleNamespace(_get_save_path=lambda *_: "")
    context = restarted._prepare_query_agent_context(
        {
            "request": request,
            "chat": restored,
            "current_user_text": "A",
            "hook_overlay": SimpleNamespace(model_dump=lambda **_: {}),
        },
    )
    assert context["enable_subagents"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "meta",
    [
        {},
        {"mode": "plan"},
        {"goal_mode_enabled": True, "mode": "plan"},
        {"goal_mode_enabled": True, "selected_expert_id": "expert-1"},
        {"goal_mode_enabled": False},
        {"goal_mode_enabled": True, "goal_id": "goal-1"},
    ],
)
async def test_goal_draft_intent_does_not_escape_to_other_modes(meta):
    from swe.app.runner.runner import AgentRunner

    runner = AgentRunner(agent_id="agent-1")
    manager = SimpleNamespace(update_chat=AsyncMock())
    runner.set_chat_manager(manager)
    chat = SimpleNamespace(
        id="chat-1",
        meta={
            "goal_draft_subagent_delegation_enabled": True,
            "other": "preserved",
        },
    )
    await runner._update_goal_draft_delegation(
        {
            "request": SimpleNamespace(channel_meta=meta),
            "chat": chat,
            "current_user_text": "A",
        },
    )
    assert "goal_draft_subagent_delegation_enabled" not in chat.meta
    assert chat.meta["other"] == "preserved"


def test_goal_draft_excludes_top_level_explicit_expert():
    from swe.app.goals.delegation import is_goal_draft_request

    assert (
        is_goal_draft_request(
            SimpleNamespace(
                channel_meta={"goal_mode_enabled": True},
                selected_expert_id="expert-1",
            ),
        )
        is False
    )


def test_chat_meta_cannot_forge_draft_intent_and_exit_clears_it():
    from fastapi import HTTPException
    from swe.app.runner.api import ChatUpdateRequest, _merge_chat_update
    from swe.app.runner.models import ChatSpec

    chat = ChatSpec(
        session_id="session-1",
        user_id="user-1",
        meta={
            "goal_draft_subagent_delegation_enabled": True,
            "other": "preserved",
        },
    )
    with pytest.raises(HTTPException):
        _merge_chat_update(
            chat,
            ChatUpdateRequest(
                meta={
                    "goal_draft_subagent_delegation_enabled": True,
                },
            ),
        )
    cleared = _merge_chat_update(
        chat,
        ChatUpdateRequest(meta={"goal_mode_enabled": False}),
    )
    assert "goal_draft_subagent_delegation_enabled" not in cleared.meta
    assert cleared.meta["other"] == "preserved"


@pytest.mark.asyncio
async def test_concurrent_settlement_does_not_overwrite_steering_authority():
    class PausedSettlementStore(InMemoryGoalStore):
        def __init__(self):
            super().__init__()
            self.settlement_started = asyncio.Event()
            self.release_settlement = asyncio.Event()

        async def save(self, snapshot):
            if snapshot.turns_used == 1 and not snapshot.steering:
                self.settlement_started.set()
                await self.release_settlement.wait()
            return await super().save(snapshot)

    store = PausedSettlementStore()
    service = GoalService(store)
    goal = await service.create_goal(scope=scope(), contract=contract())
    await service.begin_turn(goal.goal_id)
    settlement = asyncio.create_task(
        service.settle_turn(
            goal.goal_id,
            decision="continue",
            next_focus="Continue",
        ),
    )
    await store.settlement_started.wait()
    steering = asyncio.create_task(
        service.enqueue_steering(
            goal.goal_id,
            "请用子代理继续",
        ),
    )
    await asyncio.sleep(0)
    store.release_settlement.set()
    await asyncio.gather(settlement, steering)
    restored = await service.get(goal.goal_id)
    assert restored.subagent_delegation_enabled is True
    assert len(restored.steering) == 1


@pytest.mark.asyncio
async def test_stale_snapshot_cannot_downgrade_in_memory_delegation():
    store = InMemoryGoalStore()
    service = GoalService(store)
    old = await service.create_goal(scope=scope(), contract=contract())
    await service.enqueue_steering(old.goal_id, "使用子代理")
    saved = await store.save(old)
    assert saved.subagent_delegation_enabled is True
    assert (await store.get(old.goal_id)).subagent_delegation_enabled is True
    assert old.subagent_delegation_enabled is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "existing_enabled,incoming_enabled",
    [(True, False), (False, True), (False, False)],
)
async def test_mysql_save_locks_and_preserves_monotonic_delegation(
    existing_enabled,
    incoming_enabled,
):
    import json
    from swe.app.goals.store import MySqlGoalStore
    from tests.unit.app.goals.test_store import FakeDb

    db = FakeDb()
    old = await GoalService(InMemoryGoalStore()).create_goal(
        scope=scope(),
        contract=contract(),
        enable_subagents=incoming_enabled,
    )
    persisted = old.model_copy(
        update={"subagent_delegation_enabled": existing_enabled},
    )
    db.rows.append({"snapshot_json": persisted.model_dump_json()})
    saved = await MySqlGoalStore(db).save(old)
    expected = existing_enabled or incoming_enabled
    assert saved.subagent_delegation_enabled is expected
    assert "FOR UPDATE" in db.executed[0][0]
    writes = [
        (query, params)
        for query, params in db.executed
        if query.lstrip().startswith("INSERT INTO swe_goals")
    ]
    assert (
        json.loads(writes[0][1][-1])["subagent_delegation_enabled"] is expected
    )
    assert db.transactions == 1
