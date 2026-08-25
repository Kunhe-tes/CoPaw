# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from swe.agents.hook_runtime.models import (
    CommandHookHandlerConfig,
    EffectiveHookPlan,
    HookConfig,
    HookContext,
    HookEventName,
    HookMatcherConfig,
    HookMatcherGroupConfig,
    HookOverlayEntry,
    HookSessionState,
    HookSessionOverlay,
    PromptHookHandlerConfig,
    LoadedSkillHookSource,
    PROMPT_HANDLER_BLOCKABLE_EVENTS,
)
from swe.agents.hook_runtime.resolver import HookResolver


def _handler(handler_id: str, **kwargs) -> CommandHookHandlerConfig:
    return CommandHookHandlerConfig(
        id=handler_id,
        command="python -c 'print({})'",
        **kwargs,
    )


def _prompt_handler(
    handler_id: str,
    prompt: str,
    **kwargs,
) -> PromptHookHandlerConfig:
    return PromptHookHandlerConfig(
        id=handler_id,
        prompt=prompt,
        **kwargs,
    )


def _context(event: HookEventName, **kwargs) -> HookContext:
    return HookContext(
        session_id="session-1",
        transcript_path="/tmp/transcript.json",
        cwd="/tmp/tenant/workspace",
        hook_event_name=event,
        tenant_id="tenant-a",
        effective_tenant_id="tenant-a",
        user_id="user-1",
        agent_id="agent-1",
        channel="console",
        **kwargs,
    )


def test_hook_context_rejects_unbounded_permission_and_effort() -> None:
    with pytest.raises(ValidationError):
        HookContext(
            session_id="session-1",
            transcript_path="/tmp/transcript.json",
            cwd="/tmp/tenant/workspace",
            hook_event_name=HookEventName.USER_PROMPT_SUBMIT,
            tenant_id="tenant-a",
            effective_tenant_id="tenant-a",
            user_id="user-1",
            agent_id="agent-1",
            channel="console",
            permission_mode="root",
        )

    with pytest.raises(ValidationError):
        HookContext(
            session_id="session-1",
            transcript_path="/tmp/transcript.json",
            cwd="/tmp/tenant/workspace",
            hook_event_name=HookEventName.USER_PROMPT_SUBMIT,
            tenant_id="tenant-a",
            effective_tenant_id="tenant-a",
            user_id="user-1",
            agent_id="agent-1",
            channel="console",
            effort={"level": "extreme"},
        )


def test_unsupported_handler_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        HookConfig.model_validate(
            {
                "enabled": True,
                "events": {
                    "UserPromptSubmit": [
                        {
                            "matcher": {},
                            "hooks": [
                                {
                                    "id": "bad",
                                    "type": "mcp_tool",
                                    "command": "echo nope",
                                },
                            ],
                        },
                    ],
                },
            },
        )


def test_resolver_returns_empty_plan_when_hooks_disabled() -> None:
    plan = HookResolver(
        tenant_config=HookConfig(enabled=False),
    ).resolve_event_plan(
        _context(HookEventName.USER_PROMPT_SUBMIT, prompt="hello"),
    )

    assert isinstance(plan, EffectiveHookPlan)
    assert plan.event_name == HookEventName.USER_PROMPT_SUBMIT
    assert plan.handlers == ()


def test_resolver_filters_by_tool_matcher_if_condition_and_deduplicates() -> (
    None
):
    duplicate = _handler("audit")
    config = HookConfig(
        enabled=True,
        events={
            HookEventName.PRE_TOOL_USE: [
                HookMatcherGroupConfig(
                    id="shells",
                    matcher=HookMatcherConfig(tools=["execute_shell_command"]),
                    hooks=[
                        duplicate,
                        duplicate,
                        _handler("skipped-tool"),
                    ],
                ),
                HookMatcherGroupConfig(
                    id="prompt-only",
                    matcher=HookMatcherConfig(),
                    hooks=[
                        _handler(
                            "conditional",
                            if_condition="tool_name == 'execute_shell_command'",
                        ),
                        _handler(
                            "falsey",
                            if_condition="tool_name == 'read_file'",
                        ),
                    ],
                ),
            ],
        },
    )

    plan = HookResolver(tenant_config=config).resolve_event_plan(
        _context(
            HookEventName.PRE_TOOL_USE,
            tool_name="execute_shell_command",
            tool_input={"cmd": "pwd"},
        ),
    )

    assert [item.handler.id for item in plan.handlers] == [
        "audit",
        "skipped-tool",
        "conditional",
    ]


def test_prompt_handler_identity_includes_prompt_digest() -> None:
    first = _prompt_handler("policy", "Reject secrets.")
    second = _prompt_handler("policy", "Reject secrets with more detail.")

    assert first.target_identity() != second.target_identity()


def test_prompt_handler_default_fail_policy_is_block() -> None:
    handler = _prompt_handler("policy", "Reject secrets.")

    assert handler.fail_policy == "block"


def test_handler_conversation_snapshot_config_defaults_and_limit() -> None:
    handler = _handler("audit", includeConversationSnapshot=True)

    assert handler.include_conversation_snapshot is True
    assert handler.conversation_snapshot_limit == 50

    custom = _handler(
        "audit-large",
        includeConversationSnapshot=True,
        conversationSnapshotLimit=200,
    )

    assert custom.conversation_snapshot_limit == 200


def test_handler_conversation_snapshot_limit_is_bounded() -> None:
    with pytest.raises(ValidationError):
        _handler(
            "too-large",
            includeConversationSnapshot=True,
            conversationSnapshotLimit=201,
        )


def test_stop_is_blockable_and_before_stop_is_rejected() -> None:
    assert HookEventName.STOP in PROMPT_HANDLER_BLOCKABLE_EVENTS
    with pytest.raises(ValueError, match="BeforeStop"):
        HookEventName("BeforeStop")

    config = HookConfig(
        enabled=True,
        events={
            HookEventName.STOP: [
                HookMatcherGroupConfig(
                    id="stop-policy",
                    hooks=[
                        _prompt_handler(
                            "policy",
                            "只允许完成前检查通过后停止。",
                        ),
                    ],
                ),
            ],
        },
    )

    assert config.events[HookEventName.STOP][0].hooks[0].type == ("prompt")


def test_output_transform_is_valid_only_for_non_once_stop_handlers() -> None:
    config = HookConfig(
        enabled=True,
        events={
            HookEventName.STOP: [
                HookMatcherGroupConfig(
                    hooks=[_handler("format", outputTransform=True)],
                ),
            ],
        },
    )

    assert config.events[HookEventName.STOP][0].hooks[0].output_transform

    with pytest.raises(ValidationError, match="outputTransform"):
        HookConfig(
            enabled=True,
            events={
                HookEventName.PRE_TOOL_USE: [
                    HookMatcherGroupConfig(
                        hooks=[_handler("bad-event", outputTransform=True)],
                    ),
                ],
            },
        )

    with pytest.raises(ValidationError, match="once"):
        HookConfig(
            enabled=True,
            events={
                HookEventName.STOP: [
                    HookMatcherGroupConfig(
                        hooks=[
                            _handler(
                                "bad-once",
                                outputTransform=True,
                                once=True,
                            ),
                        ],
                    ),
                ],
            },
        )


def test_stop_transformers_with_matching_ids_are_not_deduplicated_across_sources() -> (
    None
):
    transformer = _handler("format", outputTransform=True)
    runtime = HookResolver(
        tenant_config=HookConfig(
            enabled=True,
            events={
                HookEventName.STOP: [
                    HookMatcherGroupConfig(
                        id="formatters",
                        hooks=[transformer],
                    ),
                ],
            },
        ),
        agent_config=HookConfig(
            enabled=True,
            events={
                HookEventName.STOP: [
                    HookMatcherGroupConfig(
                        id="formatters",
                        hooks=[transformer],
                    ),
                ],
            },
        ),
    )

    plan = runtime.resolve_stop_transformer_plan(
        _context(HookEventName.STOP, assistant_response="candidate"),
    )

    assert [item.source for item in plan.handlers] == ["tenant", "agent"]


@pytest.mark.parametrize(
    "event_name",
    [HookEventName.POST_TOOL_USE, HookEventName.POST_TOOL_USE_FAILURE],
)
def test_post_tool_events_accept_prompt_handlers(
    event_name: HookEventName,
) -> None:
    assert event_name in PROMPT_HANDLER_BLOCKABLE_EVENTS

    config = HookConfig(
        enabled=True,
        events={
            event_name: [
                HookMatcherGroupConfig(
                    id="post-tool-policy",
                    hooks=[
                        _prompt_handler(
                            "policy",
                            "Stop after the tool event.",
                        ),
                    ],
                ),
            ],
        },
    )

    assert config.events[event_name][0].hooks[0].type == "prompt"


def test_resolver_loads_stop_prompt_handlers_from_all_levels() -> None:
    tenant = HookConfig(
        enabled=True,
        events={
            HookEventName.STOP: [
                HookMatcherGroupConfig(
                    id="tenant-stop",
                    hooks=[_prompt_handler("tenant-policy", "tenant")],
                ),
            ],
        },
    )
    agent = HookConfig(
        enabled=True,
        events={
            HookEventName.STOP: [
                HookMatcherGroupConfig(
                    id="agent-stop",
                    hooks=[_prompt_handler("agent-policy", "agent")],
                ),
            ],
        },
    )
    state = HookSessionState(
        loaded_skill_sources=[
            LoadedSkillHookSource(
                source_id="skill:qa",
                skill_name="qa",
                skill_root="/workspace/skills/qa",
                source_path="/workspace/skills/qa/hooks/hooks.json",
                hook_config=HookConfig(
                    enabled=True,
                    events={
                        HookEventName.STOP: [
                            HookMatcherGroupConfig(
                                id="skill:qa:stop",
                                hooks=[
                                    _prompt_handler(
                                        "skill:qa:policy",
                                        "skill",
                                    ),
                                ],
                            ),
                        ],
                    },
                ),
            ),
        ],
    )

    plan = HookResolver(
        tenant_config=tenant,
        agent_config=agent,
        session_overlay=state,
    ).resolve_event_plan(
        _context(
            HookEventName.STOP,
            prompt="原始提示词",
            assistant_response="候选回复",
        ),
    )

    assert [item.handler.id for item in plan.handlers] == [
        "tenant-policy",
        "agent-policy",
        "skill:qa:policy",
    ]
    assert plan.context.prompt == "原始提示词"
    assert plan.context.assistant_response == "候选回复"


def test_stop_transformers_use_source_order_and_defer_if_evaluation() -> None:
    tenant = HookConfig(
        enabled=True,
        events={
            HookEventName.STOP: [
                HookMatcherGroupConfig(
                    id="tenant-stop",
                    hooks=[_handler("tenant-format", outputTransform=True)],
                ),
            ],
        },
    )
    agent = HookConfig(
        enabled=True,
        events={
            HookEventName.STOP: [
                HookMatcherGroupConfig(
                    id="agent-stop",
                    hooks=[
                        _handler(
                            "agent-format",
                            outputTransform=True,
                            if_condition="assistant_response == 'candidate'",
                        ),
                    ],
                ),
            ],
        },
    )

    def _skill_source(name: str) -> LoadedSkillHookSource:
        return LoadedSkillHookSource(
            source_id=f"skill:{name}",
            skill_name=name,
            skill_root=f"/workspace/skills/{name}",
            source_path=f"/workspace/skills/{name}/hooks/hooks.json",
            hook_config=HookConfig(
                enabled=True,
                events={
                    HookEventName.STOP: [
                        HookMatcherGroupConfig(
                            id=f"skill:{name}:stop",
                            hooks=[
                                _handler(
                                    f"skill:{name}:format",
                                    outputTransform=True,
                                ),
                            ],
                        ),
                    ],
                },
            ),
        )

    resolver = HookResolver(
        tenant_config=tenant,
        agent_config=agent,
        session_overlay=HookSessionOverlay(
            loaded_skill_sources=[
                _skill_source("zebra"),
                _skill_source("alpha"),
            ],
        ),
    )
    pending_context = _context(HookEventName.STOP)

    assert resolver.requires_stop_output_buffer(pending_context) is True
    assert [
        item.source
        for item in resolver.resolve_stop_transformer_plan(
            pending_context,
            evaluate_if=False,
        ).handlers
    ] == ["tenant", "agent", "skill:alpha", "skill:zebra"]
    assert [
        item.handler.id
        for item in resolver.resolve_stop_transformer_plan(
            pending_context,
        ).handlers
    ] == ["tenant-format", "skill:alpha:format", "skill:zebra:format"]

    eligible_context = pending_context.model_copy(
        update={"assistant_response": "candidate"},
    )
    assert [
        item.handler.id
        for item in resolver.resolve_stop_transformer_plan(
            eligible_context,
        ).handlers
    ] == [
        "tenant-format",
        "agent-format",
        "skill:alpha:format",
        "skill:zebra:format",
    ]


def test_resolver_does_not_dedupe_prompt_handlers_with_different_rules() -> (
    None
):
    config = HookConfig(
        enabled=True,
        events={
            HookEventName.PRE_TOOL_USE: [
                HookMatcherGroupConfig(
                    id="policy",
                    hooks=[
                        _prompt_handler("shared", "Reject rm -rf."),
                        _prompt_handler("shared", "Reject writes to secrets."),
                    ],
                ),
            ],
        },
    )

    plan = HookResolver(tenant_config=config).resolve_event_plan(
        _context(
            HookEventName.PRE_TOOL_USE,
            tool_name="execute_shell_command",
            tool_input={"cmd": "pwd"},
        ),
    )

    assert [item.handler.target_identity() for item in plan.handlers] == [
        config.events[HookEventName.PRE_TOOL_USE][0]
        .hooks[0]
        .target_identity(),
        config.events[HookEventName.PRE_TOOL_USE][0]
        .hooks[1]
        .target_identity(),
    ]


def test_resolver_applies_overlay_disable_expiration_and_once_scope() -> None:
    config = HookConfig(
        enabled=True,
        events={
            HookEventName.USER_PROMPT_SUBMIT: [
                HookMatcherGroupConfig(
                    id="prompts",
                    hooks=[
                        _handler("enabled"),
                        _handler("disabled"),
                        _handler("expired"),
                        _handler("once", once=True),
                    ],
                ),
            ],
        },
    )
    now = datetime.now(timezone.utc)
    overlay = HookSessionOverlay(
        entries=[
            HookOverlayEntry(hook_id="disabled", enabled=False),
            HookOverlayEntry(
                hook_id="expired",
                enabled=False,
                expires_at=now - timedelta(seconds=1),
            ),
        ],
        once_executed={
            "tenant-a:user-1:session-1:UserPromptSubmit:once": True,
        },
    )

    plan = HookResolver(
        tenant_config=config,
        session_overlay=overlay,
        now=now,
    ).resolve_event_plan(
        _context(HookEventName.USER_PROMPT_SUBMIT, prompt="hello"),
    )

    assert [item.handler.id for item in plan.handlers] == [
        "enabled",
        "expired",
    ]


def test_resolver_revalidates_event_constraints_after_overlay_override() -> (
    None
):
    config = HookConfig(
        enabled=True,
        events={
            HookEventName.PRE_TOOL_USE: [
                HookMatcherGroupConfig(hooks=[_handler("policy")]),
            ],
        },
    )
    overlay = HookSessionOverlay(
        entries=[
            HookOverlayEntry(
                hook_id="policy",
                overrides={"outputTransform": True},
            ),
        ],
    )

    with pytest.raises(ValueError, match="outputTransform"):
        HookResolver(
            tenant_config=config,
            session_overlay=overlay,
        ).resolve_event_plan(_context(HookEventName.PRE_TOOL_USE))


def test_legacy_session_state_loads_with_empty_skill_sources() -> None:
    state = HookSessionState.model_validate(
        {
            "entries": [
                {
                    "hookId": "tenant-hook",
                    "enabled": False,
                },
            ],
            "once_executed": {
                "tenant-a:user-1:session-1:PreToolUse:tenant-hook": True,
            },
        },
    )

    assert state.loaded_skill_sources == []
    assert state.entries[0].hook_id == "tenant-hook"
    assert state.once_executed == {
        "tenant-a:user-1:session-1:PreToolUse:tenant-hook": True,
    }


def test_session_state_serializes_loaded_skill_source() -> None:
    loaded_at = datetime.now(timezone.utc)
    state = HookSessionState(
        loaded_skill_sources=[
            LoadedSkillHookSource(
                source_id="skill:xlsx",
                skill_name="xlsx",
                skill_root="/workspace/skills/xlsx",
                source_path="/workspace/skills/xlsx/hooks/hooks.json",
                loaded_at=loaded_at,
                hook_config=HookConfig(
                    enabled=True,
                    events={
                        HookEventName.PRE_TOOL_USE: [
                            HookMatcherGroupConfig(
                                id="skill:xlsx:shell",
                                hooks=[
                                    _handler("skill:xlsx:validate"),
                                ],
                            ),
                        ],
                    },
                ),
                metadata={"format": "hooks.json"},
            ),
        ],
    )

    data = state.model_dump(mode="json", by_alias=True)

    assert data["loadedSkillSources"][0]["sourceId"] == "skill:xlsx"
    assert (
        data["loadedSkillSources"][0]["hookConfig"]["events"]["PreToolUse"][0][
            "hooks"
        ][0]["id"]
        == "skill:xlsx:validate"
    )


def test_session_state_rejects_duplicate_loaded_skill_sources() -> None:
    source = LoadedSkillHookSource(
        source_id="skill:xlsx",
        skill_name="xlsx",
        skill_root="/workspace/skills/xlsx",
        source_path="/workspace/skills/xlsx/hooks/hooks.json",
        hook_config=HookConfig(
            enabled=True,
            events={
                HookEventName.PRE_TOOL_USE: [
                    HookMatcherGroupConfig(
                        id="skill:xlsx:shell",
                        hooks=[_handler("skill:xlsx:validate")],
                    ),
                ],
            },
        ),
    )

    with pytest.raises(ValidationError):
        HookSessionState(
            loaded_skill_sources=[source, source],
        )


def test_session_state_validates_skill_overlay_references() -> None:
    source = LoadedSkillHookSource(
        source_id="skill:xlsx",
        skill_name="xlsx",
        skill_root="/workspace/skills/xlsx",
        source_path="/workspace/skills/xlsx/hooks/hooks.json",
        hook_config=HookConfig(
            enabled=True,
            events={
                HookEventName.PRE_TOOL_USE: [
                    HookMatcherGroupConfig(
                        id="skill:xlsx:shell",
                        hooks=[_handler("skill:xlsx:validate")],
                    ),
                ],
            },
        ),
    )

    state = HookSessionState(
        loaded_skill_sources=[source],
        entries=[
            HookOverlayEntry(hook_id="skill:xlsx:validate", enabled=False),
        ],
    )
    assert state.entries[0].hook_id == "skill:xlsx:validate"

    with pytest.raises(ValidationError):
        HookSessionState(
            loaded_skill_sources=[source],
            entries=[
                HookOverlayEntry(
                    hook_id="skill:xlsx:missing",
                    enabled=False,
                ),
            ],
        )


def test_resolver_merges_tenant_agent_and_loaded_skill_sources_in_order() -> (
    None
):
    tenant = HookConfig(
        enabled=True,
        events={
            HookEventName.PRE_TOOL_USE: [
                HookMatcherGroupConfig(
                    id="tenant",
                    hooks=[_handler("tenant-hook")],
                ),
            ],
        },
    )
    agent = HookConfig(
        enabled=True,
        events={
            HookEventName.PRE_TOOL_USE: [
                HookMatcherGroupConfig(
                    id="agent",
                    hooks=[_handler("agent-hook")],
                ),
            ],
        },
    )
    state = HookSessionState(
        loaded_skill_sources=[
            LoadedSkillHookSource(
                source_id="skill:xlsx",
                skill_name="xlsx",
                skill_root="/workspace/skills/xlsx",
                source_path="/workspace/skills/xlsx/hooks/hooks.json",
                hook_config=HookConfig(
                    enabled=True,
                    events={
                        HookEventName.PRE_TOOL_USE: [
                            HookMatcherGroupConfig(
                                id="skill:xlsx:shell",
                                hooks=[_handler("skill:xlsx:skill-hook")],
                            ),
                        ],
                    },
                ),
            ),
        ],
    )

    plan = HookResolver(
        tenant_config=tenant,
        agent_config=agent,
        session_overlay=state,
    ).resolve_event_plan(
        _context(
            HookEventName.PRE_TOOL_USE,
            tool_name="execute_shell_command",
        ),
    )

    assert [item.handler.id for item in plan.handlers] == [
        "tenant-hook",
        "agent-hook",
        "skill:xlsx:skill-hook",
    ]


def test_resolver_allows_overlay_to_disable_loaded_skill_hook() -> None:
    state = HookSessionState(
        loaded_skill_sources=[
            LoadedSkillHookSource(
                source_id="skill:xlsx",
                skill_name="xlsx",
                skill_root="/workspace/skills/xlsx",
                source_path="/workspace/skills/xlsx/hooks/hooks.json",
                hook_config=HookConfig(
                    enabled=True,
                    events={
                        HookEventName.STOP: [
                            HookMatcherGroupConfig(
                                id="skill:xlsx:stop",
                                hooks=[_handler("skill:xlsx:stop-hook")],
                            ),
                        ],
                    },
                ),
            ),
        ],
        entries=[
            HookOverlayEntry(
                hook_id="skill:xlsx:stop-hook",
                enabled=False,
            ),
        ],
    )

    plan = HookResolver(session_overlay=state).resolve_event_plan(
        _context(HookEventName.STOP, prompt="done"),
    )

    assert plan.handlers == ()
