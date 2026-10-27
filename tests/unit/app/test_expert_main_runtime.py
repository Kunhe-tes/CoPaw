# -*- coding: utf-8 -*-
"""Trusted expert main runtime assembly and capability boundaries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from swe.agents.react_agent import SWEAgent
from swe.app.runner.runner import AgentRunner
from swe.app.subagents.models import BudgetConfig, PermissionPolicy
from swe.config.config import AgentProfileConfig


@pytest.fixture
def prepared(tmp_path):
    from swe.agents.skill_runtime_snapshot import (
        ManifestStat,
        WorkspaceSkillSnapshot,
    )

    return SimpleNamespace(
        expert_id="expert-a",
        expert_name="专家 A",
        binding_revision=3,
        instruction="Act as the expert.",
        permission=PermissionPolicy.readonly(),
        budget=BudgetConfig(max_turns=2, max_tool_calls=1, timeout_ms=1000),
        skill_snapshot_dirs=(),
        mcp_configs={},
        model_slot=None,
        cleanup=Mock(),
        workspace_skill_snapshot=WorkspaceSkillSnapshot(
            workspace_dir=tmp_path,
            generation=0,
            manifest_stat=ManifestStat(0, 0, 0),
            skills={},
        ),
    )


def runner_for_test(tmp_path):
    runner = object.__new__(AgentRunner)
    runner.workspace_dir = tmp_path
    runner.agent_id = "agent"
    runner.tenant_id = "tenant"
    runner.memory_manager = Mock()
    runner._task_tracker = None
    runner.session = SimpleNamespace()
    return runner


def request_for_token(token, **changes):
    metadata = {
        "chat_id": "chat",
        "source_id": "source",
        "msgid": "turn",
        "_expert_main_execution_token": token,
    }
    metadata.update(changes)
    return SimpleNamespace(
        user_id="user",
        channel="console",
        channel_meta=metadata,
    )


def register(runner, prepared):
    return runner.register_expert_main_execution(
        prepared,
        chat_id="chat",
        user_id="user",
        source_id="source",
        turn_id="turn",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["execution", "pending", "approval"])
async def test_expert_main_cleanup_runs_on_runtime_worker(
    tmp_path,
    prepared,
    kind,
):
    import threading

    runner = runner_for_test(tmp_path)
    token = register(runner, prepared)
    loop_thread = threading.get_ident()
    cleanup_threads = []
    prepared.cleanup.side_effect = lambda: cleanup_threads.append(
        threading.get_ident(),
    )
    if kind == "execution":
        await runner.discard_expert_main_execution(token)
    else:
        lease = runner._get_expert_main_execution(request_for_token(token))
        lease.approval_id = "pending"
        if kind == "pending":
            await runner.discard_expert_main_pending(
                chat_id="chat",
                user_id="user",
                source_id="source",
            )
        else:
            await runner._discard_expert_main_approval(
                "pending",
                SimpleNamespace(channel_meta={}),
            )
    assert token not in runner._expert_main_registry().leases
    assert len(cleanup_threads) == 1
    assert cleanup_threads[0] != loop_thread


@pytest.mark.asyncio
async def test_expert_main_cancelled_cleanup_waits_for_worker_capacity(
    tmp_path,
    prepared,
    monkeypatch,
):
    import asyncio
    import threading
    from swe import runtime_workers

    slots = threading.BoundedSemaphore(1)
    # Hold capacity across cancellation, then release before awaiting cleanup.
    slots.acquire()  # pylint: disable=consider-using-with
    monkeypatch.setattr(runtime_workers, "_SLOTS", slots)
    runner = runner_for_test(tmp_path)
    token = register(runner, prepared)
    cleanup = asyncio.create_task(runner.discard_expert_main_execution(token))
    await asyncio.sleep(0)
    assert token not in runner._expert_main_registry().leases
    cleanup.cancel()
    await asyncio.sleep(0)
    assert not cleanup.done()
    prepared.cleanup.assert_not_called()
    slots.release()
    with pytest.raises(asyncio.CancelledError):
        await cleanup
    prepared.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_expert_main_query_cancellation_waits_for_snapshot_cleanup(
    tmp_path,
    prepared,
):
    import asyncio
    import threading

    runner = runner_for_test(tmp_path)
    token = register(runner, prepared)
    runner._prepare_query_handler_context = Mock(
        return_value=SimpleNamespace(identity=None),
    )
    started = asyncio.Event()
    cleanup_started = threading.Event()
    cleanup_release = threading.Event()

    def cleanup():
        cleanup_started.set()
        assert cleanup_release.wait(timeout=2)

    prepared.cleanup.side_effect = cleanup

    async def frames(*args):
        started.set()
        await asyncio.Event().wait()
        yield None, True

    runner._stream_query_handler_frames = frames

    async def consume():
        async for _ in runner.query_handler([], request_for_token(token)):
            pass

    query = asyncio.create_task(consume())
    await started.wait()
    query.cancel()
    while not cleanup_started.is_set():
        await asyncio.sleep(0)
    query.cancel()
    await asyncio.sleep(0)
    assert token not in runner._expert_main_registry().leases
    assert not query.done()
    cleanup_release.set()
    with pytest.raises(asyncio.CancelledError):
        await query
    prepared.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_expert_main_registry_rejects_forged_or_cross_scope_tokens(
    tmp_path,
    prepared,
):
    runner = runner_for_test(tmp_path)
    token = register(runner, prepared)
    assert (
        runner._get_expert_main_execution(request_for_token(token)).prepared
        is prepared
    )
    for request in [
        request_for_token("forged"),
        request_for_token(token, chat_id="other"),
        request_for_token(token, source_id="other"),
        request_for_token(token, msgid="old"),
    ]:
        with pytest.raises(ValueError, match="expert main"):
            runner._get_expert_main_execution(request)
    await runner.discard_expert_main_execution(token)
    prepared.cleanup.assert_called_once()


def test_expert_main_ignores_client_execution_identity(tmp_path):
    runner = runner_for_test(tmp_path)
    assert (
        runner._get_expert_main_execution(
            SimpleNamespace(channel_meta={"expert_main_execution": True}),
        )
        is None
    )


def test_expert_main_pending_resume_retains_original_snapshot(
    tmp_path,
    prepared,
):
    runner = runner_for_test(tmp_path)
    token = register(runner, prepared)
    lease = runner._get_expert_main_execution(request_for_token(token))
    lease.approval_id = "approval-a"
    assert (
        runner.resume_expert_main_execution(
            chat_id="chat",
            user_id="user",
            source_id="source",
            approval_id="approval-a",
            turn_id="next",
        )
        == token
    )
    assert (
        runner._get_expert_main_execution(
            request_for_token(token, msgid="next"),
        ).prepared
        is prepared
    )
    assert (
        runner.resume_expert_main_execution(
            chat_id="other",
            user_id="user",
            source_id="source",
            approval_id="approval-a",
            turn_id="next",
        )
        is None
    )


def test_expert_main_cannot_reenable_delegation_from_user_or_skill_intent():
    agent = object.__new__(SWEAgent)
    agent._agent_config = SimpleNamespace(id="agent")
    context = {
        "agent_role": "main",
        "expert_main_execution": True,
        "enable_subagents": True,
        "selected_expert_id": "expert",
        "current_user_text": "use subagent",
    }
    assert agent._background_subagent_role_blocked(context) is True


def test_expert_main_replaces_profile_role_and_keeps_source_rules(
    tmp_path,
    monkeypatch,
):
    from swe.agents import react_agent

    monkeypatch.setattr(react_agent, "build_multimodal_hint", lambda: "")
    (tmp_path / "SOUL.md").write_text("DEFAULT ROLE MUST DISAPPEAR")
    agent = object.__new__(SWEAgent)
    agent._workspace_dir = tmp_path
    agent._agent_config = AgentProfileConfig(id="agent", name="Default")
    agent._request_context = {
        "expert_main_execution": True,
        "expert_main_instruction": "EXPERT ROLE",
    }
    agent._env_context = "SOURCE PUBLIC RULES"
    agent._system_prompt_override = None
    prompt = agent._build_sys_prompt()
    assert "EXPERT ROLE" in prompt
    assert "SOURCE PUBLIC RULES" in prompt
    assert "System Prompt Protection" in prompt
    assert "DEFAULT ROLE MUST DISAPPEAR" not in prompt


@pytest.mark.asyncio
async def test_expert_main_tool_budget_and_policy_apply_to_main_identity(
    prepared,
):
    from swe.agents.tool_guard_mixin import (
        ToolGuardMixin,
        PreToolUseTerminalStop,
    )

    agent = object.__new__(SWEAgent)
    agent._request_context = {
        "agent_role": "main",
        "expert_main_execution": True,
        "expert_main_policy": prepared.permission.model_dump(),
        "expert_main_budget": prepared.budget.model_dump(),
        "_expert_main_usage": {},
    }
    agent._resolve_mcp_server = lambda _: None
    agent.print = AsyncMock()
    agent.memory = SimpleNamespace(add=AsyncMock())
    denied = await ToolGuardMixin._acting_policy_denial(
        agent,
        {"id": "x"},
        "start_subagent",
        {},
        include_budget=True,
    )
    assert denied is True
    assert (
        await agent._acting_policy_denial(
            {"id": "a"},
            "read_file",
            {"file_path": "a"},
            include_budget=True,
        )
        is False
    )
    with pytest.raises(PreToolUseTerminalStop, match="budget"):
        await agent._acting_policy_denial(
            {"id": "b"},
            "read_file",
            {"file_path": "b"},
            include_budget=True,
        )


def test_expert_main_agent_assembly_has_no_forced_subagent_or_profile_memory(
    tmp_path,
    prepared,
    monkeypatch,
):
    from swe.app.runner import runner as module
    from swe.agents.hook_runtime.models import HookSessionOverlay

    runner = runner_for_test(tmp_path)
    token = register(runner, prepared)
    request = request_for_token(token, selected_expert_id="malicious")
    runner._apply_selected_expert_context = Mock(
        side_effect=AssertionError("must not force a subagent"),
    )
    runner._source_tool_versions = lambda _: ()
    capture = Mock(return_value=SimpleNamespace())
    monkeypatch.setattr(module, "SWEAgent", capture)
    runner._create_agent_for_query(
        agent_config=AgentProfileConfig(id="agent", name="Default"),
        env_context="source",
        mcp_clients=[],
        request=request,
        session_id="session",
        user_id="user",
        channel="console",
        chat=SimpleNamespace(id="chat"),
        turn_id="actual-turn",
        hook_overlay=HookSessionOverlay(),
        auth_token=None,
        approved_tool_call=None,
    )
    kwargs = capture.call_args.kwargs
    assert kwargs["enable_memory_manager"] is False
    assert kwargs["memory_manager"] is None
    assert kwargs["enable_workspace_skills"] is False
    assert kwargs["request_context"]["agent_role"] == "main"
    assert "forced_tool_call_json" not in kwargs["request_context"]


@pytest.mark.asyncio
async def test_real_expert_agent_has_no_profile_role_memory_or_bootstrap(
    tmp_path,
    prepared,
    monkeypatch,
):
    from agentscope.formatter import OpenAIChatFormatter
    from reme.memory.file_based.reme_in_memory_memory import ReMeInMemoryMemory
    from agentscope.message import Msg
    from agentscope.model import ChatModelBase
    from swe.agents import agent_runtime_builder, react_agent
    from swe.agents.hook_runtime.models import HookSessionOverlay
    from swe.app.runner.expert_main_runtime import restricted_expert_config

    class UncalledModel(ChatModelBase):
        async def __call__(self, *args, **kwargs):
            raise AssertionError("assembly must not call the external model")

    model = UncalledModel("test-model", stream=False)
    monkeypatch.setattr(
        agent_runtime_builder,
        "create_model_and_formatter",
        lambda **_: (model, OpenAIChatFormatter()),
    )
    monkeypatch.setattr(react_agent, "build_multimodal_hint", lambda: "")
    monkeypatch.setattr(
        SWEAgent,
        "_active_model_prompt_token",
        staticmethod(lambda: None),
    )
    (tmp_path / "SOUL.md").write_text("PROFILE ROLE MUST NOT APPEAR")
    (tmp_path / "BOOTSTRAP.md").write_text("DEFINE PROFILE IDENTITY")
    runner = runner_for_test(tmp_path)
    chat_memory = ReMeInMemoryMemory(token_counter=Mock())
    chat_memory._long_term_memory = "PROFILE LONG TERM MUST NOT APPEAR"
    runner.memory_manager.create_request_memory.return_value = chat_memory
    token = register(runner, prepared)
    lease = runner._get_expert_main_execution(request_for_token(token))
    config = restricted_expert_config(
        AgentProfileConfig(id="agent", name="Default"),
        lease,
    )
    agent = runner._create_agent_for_query(
        agent_config=config,
        env_context="SOURCE PUBLIC RULES",
        mcp_clients=[],
        request=request_for_token(token),
        session_id="session",
        user_id="user",
        channel="console",
        chat=SimpleNamespace(id="chat"),
        turn_id="actual-turn",
        hook_overlay=HookSessionOverlay(),
        auth_token=None,
        approved_tool_call=None,
    )
    assert type(agent) is SWEAgent
    assert agent.model is model
    assert agent.memory is chat_memory
    assert agent.memory._long_term_memory == ""
    assert agent.memory_manager is None
    assert not agent._enable_memory_manager
    assert set(agent.toolkit.tools) <= set(prepared.permission.tools.allow)
    assert prepared.instruction in agent.sys_prompt
    assert "SOURCE PUBLIC RULES" in agent.sys_prompt
    assert "PROFILE ROLE MUST NOT APPEAR" not in agent.sys_prompt
    assert "bootstrap_hook" not in agent._instance_pre_reasoning_hooks
    assert "memory_compact_hook" in agent._instance_pre_reasoning_hooks
    message = Msg("user", "hello expert", "user")
    await agent.memory.add(message)
    for hook in agent._instance_pre_reasoning_hooks.values():
        await hook(agent, {})
    assert message.get_text_content() == "hello expert"
    assert not (tmp_path / ".bootstrap_completed").exists()


@pytest.mark.asyncio
async def test_expert_main_hard_timeout_stops_a_silent_model(
    tmp_path,
    prepared,
):
    import asyncio

    runner = runner_for_test(tmp_path)
    lease = runner._get_expert_main_execution(
        request_for_token(register(runner, prepared)),
    )
    prepared.budget.timeout_ms = 10
    agent = SimpleNamespace(
        _request_context=lease.context(),
        interrupt=AsyncMock(),
    )

    async def silent_stream():
        await asyncio.sleep(1)
        yield SimpleNamespace(role="assistant", content="too late"), True

    output = [
        item
        async for item in runner._enforce_query_timeout(
            silent_stream(),
            "session",
            agent=agent,
        )
    ]
    assert agent.interrupt.await_count == 1
    assert output[-1][0].metadata["termination_reason"] == "timeout"


@pytest.mark.asyncio
async def test_expert_main_finishing_preserves_pending_and_cleans_terminal(
    tmp_path,
    prepared,
):
    runner = runner_for_test(tmp_path)
    token = register(runner, prepared)
    request = request_for_token(token)
    lease = runner._get_expert_main_execution(request)
    lease.agent = SimpleNamespace(
        _tool_guard_pending_info={"request_id": "pending"},
    )
    await runner._finish_expert_main_execution(request)
    assert lease.approval_id == "pending"
    prepared.cleanup.assert_not_called()
    lease.agent._tool_guard_pending_info = None
    await runner._finish_expert_main_execution(request)
    prepared.cleanup.assert_called_once()


def test_expert_main_toolkit_has_only_effectively_allowed_builtins(
    tmp_path,
    prepared,
):
    from swe.app.runner.expert_main_runtime import restricted_expert_config

    runner = runner_for_test(tmp_path)
    lease = runner._get_expert_main_execution(
        request_for_token(register(runner, prepared)),
    )
    agent = object.__new__(SWEAgent)
    agent._agent_config = restricted_expert_config(
        AgentProfileConfig(id="agent", name="Default"),
        lease,
    )
    agent._request_context = lease.context()
    agent._workspace_dir = tmp_path
    agent._normalize_registered_tool_functions = lambda *_: None
    assert set(agent._create_toolkit().tools) <= set(
        prepared.permission.tools.allow,
    )


@pytest.mark.asyncio
async def test_expert_main_approval_replay_does_not_spend_tool_budget_twice(
    tmp_path,
    prepared,
):
    runner = runner_for_test(tmp_path)
    lease = runner._get_expert_main_execution(
        request_for_token(register(runner, prepared)),
    )
    agent = object.__new__(SWEAgent)
    agent._request_context = lease.context()
    agent._resolve_mcp_server = lambda _: None
    agent.print = AsyncMock()
    agent.memory = SimpleNamespace(add=AsyncMock())
    call = {
        "id": "approved-call",
        "name": "read_file",
        "input": {"file_path": "a"},
    }
    assert not await agent._acting_policy_denial(
        call,
        "read_file",
        call["input"],
        include_budget=True,
    )
    agent._request_context["_expert_main_approved_tool_call"] = call
    assert not await agent._acting_policy_denial(
        call,
        "read_file",
        call["input"],
        include_budget=True,
    )
    assert lease.usage["tool_calls"] == 1


@pytest.mark.asyncio
async def test_expert_main_ask_uses_main_approval_with_guard_disabled(
    prepared,
):
    agent = object.__new__(SWEAgent)
    agent._request_context = {
        "agent_role": "main",
        "expert_main_execution": True,
        "expert_main_policy": {"tools": {"ask": ["read_file"]}},
    }
    agent._tool_guard_engine = SimpleNamespace(enabled=False)
    agent._consume_preapproval = AsyncMock(return_value=False)
    action = await agent._decide_guard_action(
        {"id": "call", "name": "read_file", "input": {}},
    )
    assert action.kind == "needs_approval"
    agent._acting_with_approval = AsyncMock()
    await agent._execute_guard_action(action, {"id": "call"})
    agent._acting_with_approval.assert_awaited_once()


@pytest.mark.asyncio
async def test_expert_main_cancellation_cleans_pending_snapshot(
    tmp_path,
    prepared,
):
    runner = runner_for_test(tmp_path)
    token = register(runner, prepared)
    lease = runner._get_expert_main_execution(request_for_token(token))
    lease.agent = SimpleNamespace(
        _tool_guard_pending_info={"request_id": "pending"},
    )
    await runner._finish_expert_main_execution(
        request_for_token(token),
        completed=False,
    )
    prepared.cleanup.assert_called_once()


def test_expert_main_resume_clears_previous_agent(tmp_path, prepared):
    runner = runner_for_test(tmp_path)
    token = register(runner, prepared)
    lease = runner._get_expert_main_execution(request_for_token(token))
    lease.agent = SimpleNamespace(
        _tool_guard_pending_info={"request_id": "pending"},
    )
    lease.approval_id = "pending"
    runner.resume_expert_main_execution(
        chat_id="chat",
        user_id="user",
        source_id="source",
        approval_id="pending",
        turn_id="next",
    )
    assert lease.agent is None


def test_expert_main_filters_profile_skill_hook_state(tmp_path, prepared):
    from swe.agents.hook_runtime.models import HookSessionOverlay
    from swe.app.runner.expert_main_runtime import restrict_expert_hook_overlay

    overlay = HookSessionOverlay(
        once_executed={"skill:old:hook": True, "global-hook": True},
    )
    narrowed = restrict_expert_hook_overlay(overlay)
    assert narrowed.once_executed == {"global-hook": True}
    assert overlay.once_executed["skill:old:hook"] is True


@pytest.mark.asyncio
async def test_expert_main_history_load_preserves_current_expert_prompt(
    tmp_path,
    prepared,
    monkeypatch,
):
    from swe.app.runner import session_lifecycle

    runner = runner_for_test(tmp_path)
    agent = SimpleNamespace(
        _request_context={"expert_main_execution": True},
        _sys_prompt="CURRENT EXPERT",
    )

    async def restore(*args, **kwargs):
        agent._sys_prompt = "OLD DEFAULT PROFILE"
        return True

    monkeypatch.setattr(session_lifecycle, "get_state_loaded", restore)
    assert await runner.get_state_loaded(
        agent,
        "session",
        False,
        False,
        "user",
    )
    assert agent._sys_prompt == "CURRENT EXPERT"


def test_expert_main_skill_detector_uses_only_copied_skill_roots(
    tmp_path,
    prepared,
    monkeypatch,
):
    from swe.app.runner import runner as module
    from swe.agents.hook_runtime.models import HookSessionOverlay

    skill = tmp_path / "frozen" / "private-skill"
    skill.mkdir(parents=True)
    prepared.skill_snapshot_dirs = (str(skill),)
    runner = runner_for_test(tmp_path)
    token = register(runner, prepared)
    lease = runner._get_expert_main_execution(request_for_token(token))
    runtime = SimpleNamespace(
        agent=SimpleNamespace(
            _request_context=lease.context(),
            _workspace_skill_snapshot=None,
            get_runtime_skills=lambda: ["private-skill"],
            get_skill_runtime_profiles=lambda: {},
        ),
        hook_overlay=HookSessionOverlay(),
        user_id="user",
        session_id="session",
        channel="console",
    )
    factory = Mock(return_value=SimpleNamespace())
    monkeypatch.setattr(module, "_create_session_skill_detector", factory)
    runner._attach_session_skill_detector(
        runtime=runtime,
        request=request_for_token(token),
    )
    assert factory.call_args.kwargs["skill_dirs"] == {"private-skill": skill}


@pytest.mark.asyncio
async def test_expert_main_tags_terminal_output_before_history_save(
    tmp_path,
    prepared,
):
    from agentscope.message import Msg

    runner = runner_for_test(tmp_path)
    token = register(runner, prepared)
    runner._prepare_query_handler_context = Mock(
        return_value=SimpleNamespace(identity=None),
    )
    runner._settle_query_handler_outcome = AsyncMock()
    message = Msg("Friday", "budget limit", "assistant")

    async def frames(*args):
        yield message, True

    runner._stream_query_handler_frames = frames
    output = [
        item
        async for item in runner.query_handler([], request_for_token(token))
    ]
    assert output[0][0].metadata["execution_identity"]["kind"] == "expert_main"
    assert message.metadata["execution_identity"]["expert_id"] == "expert-a"
    prepared.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_expert_main_pending_cleanup_is_scope_bound_and_keeps_active_runs(
    tmp_path,
    prepared,
):
    runner = runner_for_test(tmp_path)
    token = register(runner, prepared)
    lease = runner._get_expert_main_execution(request_for_token(token))
    await runner.discard_expert_main_pending(
        chat_id="chat",
        user_id="user",
        source_id="source",
    )
    prepared.cleanup.assert_not_called()
    lease.approval_id = "pending"
    await runner.discard_expert_main_pending(
        chat_id="other",
        user_id="user",
        source_id="source",
    )
    prepared.cleanup.assert_not_called()
    await runner.discard_expert_main_pending(
        chat_id="chat",
        user_id="user",
        source_id="source",
    )
    prepared.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_expert_main_finalize_never_prepares_profile_long_term_memory(
    tmp_path,
    prepared,
):
    from swe.app.runner import query_runtime

    runner = runner_for_test(tmp_path)
    token = register(runner, prepared)
    runner.memory_manager.prepare_request_memory = AsyncMock()
    agent = SimpleNamespace(
        register_mcp_clients=AsyncMock(),
        set_console_output_enabled=Mock(),
    )
    runner._create_agent_for_query_async = AsyncMock(return_value=agent)
    runner._attach_session_skill_detector = Mock()
    inputs = SimpleNamespace(
        workspace_skill_snapshot=prepared.workspace_skill_snapshot,
        agent_config=AgentProfileConfig(id="agent", name="Default"),
        session_id="session",
        user_id="user",
        channel="console",
        hook_overlay=None,
        auth_token=None,
        tenant_hooks=None,
        skip_history=False,
        selected_context_directives=[],
        session_execution=None,
    )
    runtime = await query_runtime.finalize_query_runtime(
        runner,
        request=request_for_token(token),
        query="hello",
        msgs=[],
        preflight=SimpleNamespace(approved_tool_call=None),
        inputs=inputs,
        resources=SimpleNamespace(
            chat=SimpleNamespace(id="chat"),
            env_context="source",
            turn_id="actual-turn",
        ),
        mcp_clients=[],
        get_last_user_text=lambda _: "",
        debug_log=Mock(),
    )
    assert runtime.agent is agent
    runner.memory_manager.prepare_request_memory.assert_not_awaited()
    assert (
        runner._create_agent_for_query_async.call_args.kwargs[
            "workspace_skill_snapshot"
        ]
        is prepared.workspace_skill_snapshot
    )


@pytest.mark.asyncio
async def test_expert_main_ask_preapproval_replays_without_a_new_request():
    agent = object.__new__(SWEAgent)
    agent._request_context = {
        "expert_main_execution": True,
        "expert_main_policy": {"tools": {"ask": ["read_file"]}},
    }
    agent._tool_guard_engine = SimpleNamespace(enabled=False)
    agent._consume_preapproval = AsyncMock(return_value=True)
    agent._cleanup_tool_guard_denied_messages = AsyncMock()
    action = await agent._decide_guard_action(
        {"name": "read_file", "input": {}},
    )
    assert action.kind == "preapproved"


@pytest.mark.asyncio
async def test_expert_main_reasoning_budget_cannot_reset_across_retry(
    tmp_path,
    prepared,
):
    from swe.app.runner.expert_main_runtime import consume_expert_reasoning
    from swe.agents.tool_guard_mixin import PreToolUseTerminalStop

    runner = runner_for_test(tmp_path)
    lease = runner._get_expert_main_execution(
        request_for_token(register(runner, prepared)),
    )
    consume_expert_reasoning(lease.context())
    consume_expert_reasoning(lease.context())
    with pytest.raises(PreToolUseTerminalStop, match="budget"):
        consume_expert_reasoning(lease.context())


def test_expert_main_approval_extra_keeps_frozen_identity(tmp_path, prepared):
    runner = runner_for_test(tmp_path)
    lease = runner._get_expert_main_execution(
        request_for_token(register(runner, prepared)),
    )
    agent = object.__new__(SWEAgent)
    agent._request_context = lease.context()
    agent._extract_sibling_tool_calls = lambda: []
    extra = agent._build_approval_extra(
        {"id": "call", "name": "read_file", "input": {}},
        "tool_guard",
        None,
        None,
    )
    assert extra["execution_identity"]["kind"] == "expert_main"
    assert extra["execution_identity"]["expert_id"] == "expert-a"
    agent._request_context["execution_identity"]["expert_name"] = "changed"
    assert extra["execution_identity"]["expert_name"] == "专家 A"


@pytest.mark.asyncio
async def test_expert_main_denied_approval_releases_original_snapshot(
    tmp_path,
    prepared,
    monkeypatch,
):
    import time
    from swe.app import approvals
    from swe.app.runner import runner as module

    runner = runner_for_test(tmp_path)
    token = register(runner, prepared)
    runner._get_expert_main_execution(request_for_token(token)).approval_id = (
        "approval"
    )
    pending = SimpleNamespace(
        request_id="approval",
        created_at=time.time(),
        tool_name="read_file",
        extra={"execution_identity": {"kind": "expert_main"}},
    )
    service = SimpleNamespace(resolve_request=AsyncMock(return_value=pending))
    monkeypatch.setattr(approvals, "get_approval_service", lambda: service)
    monkeypatch.setattr(
        module,
        "_select_pending_approval",
        AsyncMock(return_value=pending),
    )
    monkeypatch.setattr(
        module,
        "_external_approval_submission",
        lambda _: None,
    )
    monkeypatch.setattr(
        module,
        "_build_denial_response_msg",
        lambda *_: "denied",
    )
    runner._notify_console_approval_result = AsyncMock()
    response, consumed, call = await runner._resolve_pending_approval(
        "session",
        "new message",
        SimpleNamespace(channel_meta={}),
    )
    assert consumed and response == "denied" and call is None
    prepared.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_expert_main_low_budget_approval_replay_counts_only_model_calls(
    tmp_path,
    prepared,
    monkeypatch,
):
    from contextlib import nullcontext
    from agentscope.agent import ReActAgent
    from agentscope.message import Msg
    from swe.agents import react_agent
    from swe.agents.tool_guard_mixin import PreToolUseTerminalStop

    runner = runner_for_test(tmp_path)
    token = register(runner, prepared)
    lease = runner._get_expert_main_execution(request_for_token(token))
    agent = object.__new__(SWEAgent)
    agent.name = "Expert"
    agent._request_context = lease.context()
    agent.agent_phase = lambda *args, **kwargs: nullcontext()
    agent._agent_phase_context = lambda *args, **kwargs: nullcontext()
    agent.print = AsyncMock()
    agent.memory = SimpleNamespace(add=AsyncMock())
    agent._resolved_model_slot = {}
    agent._consume_plan_interaction_turn_boundary = lambda: False
    agent._reason_about_replay_done = AsyncMock(return_value=None)
    agent._last_tool_response_is_denied = Mock(return_value=False)
    agent._get_pending_info_for_display = AsyncMock(
        return_value={
            "request_id": "approval",
            "tool_name": "read_file",
        },
    )
    agent._run_reasoning_with_internal_context = (
        SWEAgent._run_reasoning_with_internal_context.__wrapped__.__get__(
            agent,
        )
    )
    model = AsyncMock(return_value=Msg("Expert", "model output", "assistant"))
    monkeypatch.setattr(ReActAgent, "_reasoning", model)
    monkeypatch.setattr(
        react_agent,
        "get_active_model_supports_multimodal",
        lambda: True,
    )
    reason = SWEAgent._reasoning.__wrapped__.__get__(agent)

    await reason()
    agent._last_tool_response_is_denied.return_value = True
    waiting = await reason()
    assert waiting.metadata["approval_action"]["requestId"] == "approval"
    assert lease.usage["turns"] == 1
    agent._request_context["forced_tool_call_json"] = (
        '{"id":"approved-call","name":"read_file","input":{}}'
    )
    replay = await reason()
    assert replay.content[0]["id"] == "approved-call"
    assert lease.usage["turns"] == 1
    agent._last_tool_response_is_denied.return_value = False
    await reason()
    assert lease.usage["turns"] == 2
    assert model.await_count == 2
    with pytest.raises(PreToolUseTerminalStop, match="reasoning budget"):
        await reason()
    assert model.await_count == 2


@pytest.mark.asyncio
async def test_expert_main_media_retry_consumes_another_model_turn(
    tmp_path,
    prepared,
    monkeypatch,
):
    from contextlib import nullcontext
    from agentscope.agent import ReActAgent
    from agentscope.message import Msg
    from swe.agents import react_agent

    runner = runner_for_test(tmp_path)
    lease = runner._get_expert_main_execution(
        request_for_token(register(runner, prepared)),
    )
    agent = object.__new__(SWEAgent)
    agent.name = "Expert"
    agent._request_context = lease.context()
    agent.agent_phase = lambda *args, **kwargs: nullcontext()
    agent._agent_phase_context = lambda *args, **kwargs: nullcontext()
    agent._consume_plan_interaction_turn_boundary = lambda: False
    agent._reason_about_replay_done = AsyncMock(return_value=None)
    agent._last_tool_response_is_denied = lambda: False
    agent._run_reasoning_with_internal_context = (
        SWEAgent._run_reasoning_with_internal_context.__wrapped__.__get__(
            agent,
        )
    )
    agent._is_bad_request_or_media_error = lambda _: True
    agent._strip_media_blocks_from_memory = Mock(return_value=1)
    monkeypatch.setattr(
        react_agent,
        "get_active_model_supports_multimodal",
        lambda: True,
    )
    model = AsyncMock(
        side_effect=[
            ValueError("unsupported image"),
            Msg("Expert", "retry succeeded", "assistant"),
        ],
    )
    monkeypatch.setattr(ReActAgent, "_reasoning", model)
    await SWEAgent._reasoning.__wrapped__(agent)
    assert model.await_count == 2
    assert lease.usage["turns"] == 2
