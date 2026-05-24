# -*- coding: utf-8 -*-
"""Focused tests for SubAgent definition, registry, policy, and run records."""

from __future__ import annotations

from pathlib import Path

import pytest

from swe.app.subagents import (
    AgentRegistry,
    AgentResult,
    DefinitionValidationError,
    DelegationSpec,
    InMemoryDefinitionProvider,
    InMemorySubAgentRunStore,
    LocalJsonSubAgentRunStore,
    PermissionPolicy,
    SubAgentDefinition,
    builtin_definition_provider,
    compose_effective_policy,
    validate_tool_call,
)


def test_builtin_definitions_are_valid_and_readonly() -> None:
    """Built-ins resolve with immutable source metadata and readonly tools."""
    registry = AgentRegistry([builtin_definition_provider()])

    names = {definition.name for definition in registry.list()}

    assert names == {
        "plan-researcher",
        "risk-reviewer",
        "test-surface-analyzer",
    }
    definition = registry.resolve("plan-researcher")
    assert definition.source == "builtin"
    assert definition.owner_scope == "builtin"
    assert definition.model.behavior == "inherit"
    assert definition.isolation.context == "fresh"
    assert definition.isolation.workspace == "shared"
    assert definition.isolation.memory == "none"
    assert definition.lifecycle.allow_nested_delegation is False
    assert set(definition.tools.allow) <= {
        "read_file",
        "grep_search",
        "glob_search",
        "execute_shell_command",
        "get_current_time",
    }


def test_definition_validation_rejects_unsupported_mvp_capabilities() -> None:
    """Custom definitions use the same validator and cannot widen MVP scope."""
    with pytest.raises(DefinitionValidationError) as exc_info:
        SubAgentDefinition.model_validate(
            {
                "name": "unsafe",
                "version": "1.0.0",
                "description": "Unsafe worker",
                "prompt": {"system": "Inspect code"},
                "source": "user",
                "owner_scope": "tenant/source/workspace",
                "tools": {
                    "allow": ["read_file", "write_file", "mcp:server.tool"],
                },
                "isolation": {
                    "context": "fork",
                    "workspace": "worktree",
                    "memory": "project",
                },
                "lifecycle": {"allow_nested_delegation": True},
            },
        )

    message = str(exc_info.value)
    assert "nested delegation" in message
    assert "unsupported context isolation" in message
    assert "unsupported workspace isolation" in message
    assert "persistent memory" in message
    assert "MCP" in message
    assert "mutating tool" in message


def test_definition_validation_rejects_unsafe_permission_overrides() -> None:
    """User definitions cannot widen readonly policy via permission config."""
    with pytest.raises(DefinitionValidationError) as exc_info:
        SubAgentDefinition.model_validate(
            {
                "name": "unsafe-permission",
                "version": "1.0.0",
                "description": "Unsafe permission worker",
                "prompt": {"system": "Inspect code"},
                "source": "user",
                "owner_scope": "tenant/source/workspace",
                "permission": {
                    "tools": {
                        "allow": [
                            "read_file",
                            "write_file",
                            "mcp:server.tool",
                        ],
                    },
                    "shell": {
                        "allowed_commands": ["pwd", "python"],
                    },
                },
            },
        )

    message = str(exc_info.value)
    assert "permission" in message
    assert "MCP" in message
    assert "mutating tool" in message
    assert "python" in message


def test_registry_rejects_duplicate_and_builtin_shadowing() -> None:
    """A user provider cannot silently replace a built-in definition."""
    builtin = builtin_definition_provider().list_definitions()[0]
    user_shadow = builtin.model_copy(update={"source": "user"})

    with pytest.raises(DefinitionValidationError) as exc_info:
        AgentRegistry(
            [
                builtin_definition_provider(),
                InMemoryDefinitionProvider([user_shadow]),
            ],
        )

    assert "duplicate" in str(exc_info.value)
    assert "plan-researcher" in str(exc_info.value)


def test_registry_rejects_user_definition_shadowing_builtin_name() -> None:
    """A user provider cannot supersede a built-in with another version."""
    builtin = builtin_definition_provider().list_definitions()[0]
    user_shadow = builtin.model_copy(
        update={"source": "user", "version": "9.0.0"},
    )

    with pytest.raises(DefinitionValidationError) as exc_info:
        AgentRegistry(
            [
                builtin_definition_provider(),
                InMemoryDefinitionProvider([user_shadow]),
            ],
        )

    assert "shadow builtin" in str(exc_info.value)
    assert "plan-researcher" in str(exc_info.value)


def test_registry_supports_user_provider_filtering_and_version_lookup() -> (
    None
):
    """Extension providers can be injected without public CRUD/API support."""
    user_definition = SubAgentDefinition.model_validate(
        {
            "name": "local-reader",
            "version": "1.0.0",
            "description": "Local readonly worker",
            "prompt": {"system": "Read files and summarize evidence."},
            "source": "user",
            "owner_scope": "tenant-a/source-b/default",
            "tools": {"allow": ["read_file"]},
        },
    )
    registry = AgentRegistry(
        [
            builtin_definition_provider(),
            InMemoryDefinitionProvider([user_definition]),
        ],
    )

    assert registry.resolve("local-reader").owner_scope == (
        "tenant-a/source-b/default"
    )
    assert registry.get("local-reader", "1.0.0") == user_definition
    assert registry.list(source="user") == [user_definition]
    assert registry.list(owner_scope="tenant-a/source-b/default") == [
        user_definition,
    ]


def test_effective_policy_uses_intersection_and_deny_precedence() -> None:
    """The effective policy cannot exceed parent/sub/runtime/workspace inputs."""
    parent = PermissionPolicy.readonly(
        allow_tools=["read_file", "grep_search", "execute_shell_command"],
        deny_tools=["grep_search"],
    )
    subagent = PermissionPolicy.readonly(
        allow_tools=["read_file", "execute_shell_command"],
    )
    runtime = PermissionPolicy.readonly(
        allow_tools=["read_file", "glob_search", "execute_shell_command"],
    )
    workspace = PermissionPolicy.readonly(
        allow_tools=["read_file", "grep_search", "execute_shell_command"],
        deny_tools=["execute_shell_command"],
    )

    effective = compose_effective_policy(parent, subagent, runtime, workspace)

    assert effective.tools.allow == ["read_file"]
    assert sorted(effective.tools.deny) == [
        "execute_shell_command",
        "grep_search",
    ]
    assert validate_tool_call(effective, "read_file", {"path": "x"}).allowed
    assert not validate_tool_call(
        effective,
        "execute_shell_command",
        {"command": "git status"},
    ).allowed


@pytest.mark.parametrize(
    ("command", "allowed"),
    [
        ("pwd", True),
        ("ls src/swe", True),
        ("rg SubAgent src tests", True),
        ("git status --short", True),
        ("git show HEAD -- src/swe/app.py", True),
        ("pytest tests/unit", False),
        ("rg --pre 'touch /tmp/subagent-mutates' SubAgent src", False),
        ("git diff --ext-diff", False),
        ("git checkout -- file.py", False),
        ("git status --short && touch /tmp/subagent-mutates", False),
        ("git status --short & touch /tmp/subagent-mutates", False),
        ("git status --short | sh", False),
        ("git diff --output=/tmp/subagent-mutates", False),
        ("git log --output /tmp/subagent-mutates", False),
        ("sed -i bak s/a/b/ file.txt", False),
        ("sed --in-place=.bak s/a/b/ file.txt", False),
        ("sed 's/a/b/w/tmp/subagent-mutates' file.txt", False),
        ("sed 's/a/date/e' file.txt", False),
        ("sed -n '1,10w /tmp/subagent-mutates' file.txt", False),
        ("sed -n '1e touch /tmp/subagent-mutates' file.txt", False),
        ("sed -f readonly-script.sed file.txt", False),
        ("sed -freadonly-script.sed file.txt", False),
        ("sed --file readonly-script.sed file.txt", False),
        ("sed --file=readonly-script.sed file.txt", False),
        ("sed -n '1,10p' a.py > out.txt", False),
        ("python -m black src", False),
        ("deploy production", False),
    ],
)
def test_readonly_shell_authorization(command: str, allowed: bool) -> None:
    """Readonly shell permits conservative inspection commands only."""
    policy = PermissionPolicy.readonly()

    decision = validate_tool_call(
        policy,
        "execute_shell_command",
        {"command": command},
    )

    assert decision.allowed is allowed


@pytest.mark.asyncio
async def test_run_stores_record_status_result_and_errors(
    tmp_path: Path,
) -> None:
    """Run stores keep lifecycle state in app workspace state."""
    spec = DelegationSpec(
        task_id="task-1",
        parent_thread_id="thread-1",
        agent_name="plan-researcher",
        objective="Inspect the repo",
    )
    definition = AgentRegistry([builtin_definition_provider()]).resolve(
        "plan-researcher",
    )
    policy = PermissionPolicy.readonly()
    result = AgentResult(
        task_id="task-1",
        agent_run_id="placeholder",
        agent_name="plan-researcher",
        status="completed",
        summary="done",
    )

    memory_store = InMemorySubAgentRunStore()
    record = await memory_store.create(spec, definition, policy)
    await memory_store.mark_running(record.run_id)
    await memory_store.finish(record.run_id, result)

    saved = await memory_store.get(record.run_id)
    assert saved is not None
    assert saved.status == "completed"
    assert saved.result is not None
    assert saved.definition_source == "builtin"

    local_store = LocalJsonSubAgentRunStore(tmp_path / "app-state")
    failed = await local_store.create(spec, definition, policy)
    await local_store.mark_running(failed.run_id)
    await local_store.fail(failed.run_id, "boom")

    assert (tmp_path / "app-state" / "subagent_runs.json").exists()
    saved_failed = await local_store.get(failed.run_id)
    assert saved_failed is not None
    assert saved_failed.status == "failed"
    assert saved_failed.errors[0].message == "boom"
