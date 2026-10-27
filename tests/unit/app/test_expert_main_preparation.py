# -*- coding: utf-8 -*-
"""Preparation captures one main expert's identity and bounded resources."""

from dataclasses import FrozenInstanceError
import json

import pytest

from swe.app.subagents.agent_definitions import AgentOwnedDefinitionRepository
from swe.app.subagents.models import BudgetConfig, PermissionPolicy
from swe.config.config import AgentProfileConfig
from swe.providers.models import ModelSlotConfig

CHAT_ID = "00000000-0000-0000-0000-000000000302"


def _module():
    from swe.app.runner import expert_main

    return expert_main


def _definition(workspace, *, community=False):
    repository = AgentOwnedDefinitionRepository(
        workspace / "agents", owner_scope="agent:tenant:profile"
    )
    payload = {
        "name": "reviewer",
        "description": "Review",
        "instruction": "Expert role",
        "skills": [],
        "mcps": [],
        "tools": {"inherit": False, "allow": ["read_file", "write_file"]},
        "budget": {"max_turns": 8, "max_tool_calls": 9, "timeout_ms": 10000},
    }
    if community:
        payload["community"] = {
            "item_id": "one",
            "version": "1",
            "content_fingerprint": "one",
        }
    package = repository.create(payload)
    package = repository.enable(
        package.definition_id, expected_revision=package.revision
    )
    if community:
        (
            workspace / "agents" / f"{package.definition_id}.dependencies"
        ).mkdir()
    return repository, package.definition


def _prepare(workspace, definition, **overrides):
    module = _module()
    config = AgentProfileConfig(id="profile", name="Profile")
    config.running.max_iters = 6
    kwargs = {
        "definition": definition,
        "context": module.ExpertMainPreparationContext(
            workspace_dir=workspace,
            chat_id=CHAT_ID,
            binding_revision=4,
            tenant_id="tenant",
        ),
        "parent_agent_config": config,
        "parent_policy": PermissionPolicy.readonly(
            allow_tools=["read_file", "write_file"]
        ),
        "workspace_policy": PermissionPolicy.readonly(
            allow_tools=["read_file"]
        ),
        "chat_model_slot": ModelSlotConfig(
            provider_id="chat", model="chat-model"
        ),
        "main_budget": BudgetConfig(
            max_turns=10, max_tool_calls=5, timeout_ms=20000
        ),
    }
    kwargs.update(overrides)
    return module.prepare_expert_main_execution(**kwargs)


def test_preparation_captures_identity_policy_and_strict_per_message_budget(
    tmp_path,
):
    _, definition = _definition(tmp_path)
    prepared = _prepare(tmp_path, definition)
    assert (
        prepared.expert_id,
        prepared.expert_name,
        prepared.binding_revision,
    ) == (definition.agent_owned.definition_id, "reviewer", 4)
    assert prepared.instruction == "Expert role"
    assert prepared.permission.tools.allow == ["read_file"]
    assert prepared.budget == BudgetConfig(
        max_turns=6, max_tool_calls=5, timeout_ms=10000
    )
    assert prepared.model_slot == ModelSlotConfig(
        provider_id="chat", model="chat-model"
    )
    with pytest.raises(FrozenInstanceError):
        prepared.instruction = "changed"
    definition.instruction = "changed upstream"
    assert prepared.instruction == "Expert role"
    prepared.cleanup()


@pytest.mark.parametrize(
    ("global_seconds", "effective_ms"), [(1.25, 1250), (20, 10000)]
)
def test_admission_preparation_snapshots_global_timeout_limit(
    tmp_path, monkeypatch, global_seconds, effective_ms
):
    from types import SimpleNamespace
    from swe import constant
    from swe.app.runner import expert_main_admission
    from swe.providers import ProviderManager

    _, definition = _definition(tmp_path)
    monkeypatch.setattr(constant, "QUERY_TIMEOUT_SECONDS", global_seconds)
    monkeypatch.setattr(
        ProviderManager,
        "get_instance",
        lambda tenant: SimpleNamespace(get_active_model=lambda: None),
    )
    workspace = SimpleNamespace(
        config=AgentProfileConfig(id="profile", name="Profile"),
        tenant_id="tenant",
        workspace_dir=tmp_path,
    )
    prepared = expert_main_admission._prepare(
        workspace,
        SimpleNamespace(id=CHAT_ID),
        SimpleNamespace(revision=1),
        definition,
    )
    assert prepared.budget.timeout_ms == effective_ms
    assert prepared.budget.max_tool_calls == definition.budget.max_tool_calls
    prepared.cleanup()


def test_unresolvable_expert_model_keeps_current_chat_model(
    tmp_path, monkeypatch
):
    _, definition = _definition(tmp_path)
    module = _module()
    monkeypatch.setattr(
        module, "resolve_skill_owned_model_slot", lambda *_: None
    )
    prepared = _prepare(tmp_path, definition)
    assert prepared.model_slot.provider_id == "chat"
    prepared.cleanup()


def test_usable_expert_model_wins_without_provider_credentials(
    tmp_path, monkeypatch
):
    _, definition = _definition(tmp_path)
    module = _module()
    slot = ModelSlotConfig(provider_id="expert", model="expert-model")
    monkeypatch.setattr(
        module, "resolve_skill_owned_model_slot", lambda *_: slot
    )
    prepared = _prepare(tmp_path, definition)
    assert prepared.model_slot == slot
    assert set(prepared.model_slot.model_dump()) == {"provider_id", "model"}
    prepared.cleanup()


@pytest.mark.parametrize("state", ["disabled", "deleted", "broken"])
def test_invalid_current_definition_blocks_then_same_identity_can_recover(
    tmp_path, state
):
    repository, definition = _definition(tmp_path)
    path = tmp_path / "agents" / f"{definition.agent_owned.definition_id}.toml"
    original = path.read_text()
    if state == "disabled":
        package = repository.get(definition.agent_owned.definition_id)
        repository.disable(
            package.definition_id, expected_revision=package.revision
        )
    elif state == "deleted":
        path.unlink()
    else:
        path.write_text("invalid TOML [[")
    with pytest.raises(_module().ExpertMainPreparationError):
        _prepare(tmp_path, definition)
    path.write_text(original)
    prepared = _prepare(tmp_path, definition)
    assert prepared.expert_id == definition.agent_owned.definition_id
    prepared.cleanup()


def test_private_mcps_are_independent_and_cleanup_keeps_other_message(
    tmp_path,
):
    _, definition = _definition(tmp_path, community=True)
    metadata = definition.agent_owned
    path = tmp_path / "agents" / f"{metadata.definition_id}.toml"
    path.write_text(
        path.read_text().replace("mcps = []", 'mcps = ["private"]')
    )
    definition.agent_owned.declared_mcps = ["private"]
    root = tmp_path / "agents" / f"{metadata.definition_id}.dependencies/mcp"
    root.mkdir()
    (root / "config.json").write_text(
        json.dumps(
            {
                "private": {
                    "name": "private",
                    "command": "offline-server",
                    "env": {"KEY": "value"},
                }
            }
        )
    )
    first = _prepare(tmp_path, definition)
    second = _prepare(tmp_path, definition)
    assert first.mcp_configs["private"].command == "offline-server"
    first.mcp_configs["private"].env["KEY"] = "mutated"
    assert second.mcp_configs["private"].env["KEY"] == "value"
    assert first.snapshot_root != second.snapshot_root
    first.cleanup()
    assert second.snapshot_root.is_dir()
    assert not (tmp_path / "active_skills").exists()
    assert not list(tmp_path.glob("**/.*.mcp.json"))
    second.cleanup()


def test_preparation_inherited_policy_still_denies_delegation(tmp_path):
    repository, definition = _definition(tmp_path)
    package = repository.get(definition.agent_owned.definition_id)
    package = repository.update(
        package.definition_id,
        {"tools": {"inherit": True, "allow": []}},
        expected_revision=package.revision,
    )
    definition = package.definition
    broad = PermissionPolicy.readonly(allow_tools=["read_file", "write_file"])
    broad.tools.allow.append("start_subagent")
    prepared = _prepare(
        tmp_path, definition, parent_policy=broad, workspace_policy=broad
    )
    assert prepared.permission.tools.allow == ["read_file", "write_file"]
    assert "start_subagent" not in prepared.permission.tools.allow
    prepared.cleanup()


def test_main_preparation_freezes_v1_and_next_message_uses_complete_v2(
    tmp_path,
):
    repository, definition = _definition(tmp_path, community=True)
    definition_id = definition.agent_owned.definition_id

    def write_version(version):
        payload = repository.get(definition_id).raw_payload
        payload.update(
            {
                "instruction": f"instruction {version}",
                "skills": [f"skill-{version}"],
                "mcps": [f"mcp-{version}"],
                "community": {
                    "item_id": "one",
                    "version": version,
                    "content_fingerprint": version,
                },
            }
        )
        root = tmp_path / "agents" / f"{definition_id}.dependencies"
        import shutil

        shutil.rmtree(root)
        skill = root / "skills" / f"skill-{version}"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"skill {version}")
        (root / "mcp").mkdir()
        (root / "mcp/config.json").write_text(
            json.dumps(
                {
                    f"mcp-{version}": {
                        "name": f"mcp-{version}",
                        "command": f"server-{version}",
                    }
                }
            )
        )
        package = repository._package_from_payload(definition_id, payload)
        repository._write(package)
        return package.definition

    from pathlib import Path

    first = _prepare(tmp_path, write_version("1"))
    second = _prepare(tmp_path, write_version("2"))
    assert (
        first.instruction,
        first.community_version,
        set(first.mcp_configs),
    ) == ("instruction 1", "1", {"mcp-1"})
    assert (
        second.instruction,
        second.community_version,
        set(second.mcp_configs),
    ) == ("instruction 2", "2", {"mcp-2"})
    assert (
        Path(first.skill_snapshot_dirs[0], "SKILL.md").read_text() == "skill 1"
    )
    assert (
        Path(second.skill_snapshot_dirs[0], "SKILL.md").read_text()
        == "skill 2"
    )
    first.cleanup()
    assert Path(second.skill_snapshot_dirs[0], "SKILL.md").is_file()
    second.cleanup()


def test_unreadable_mcp_capture_fails_closed_and_cleans_message_files(
    tmp_path, monkeypatch
):
    _, definition = _definition(tmp_path, community=True)
    module = _module()
    metadata = definition.agent_owned
    path = tmp_path / "agents" / f"{metadata.definition_id}.toml"
    path.write_text(
        path.read_text().replace("mcps = []", 'mcps = ["private"]')
    )
    definition.agent_owned.declared_mcps = ["private"]
    root = tmp_path / "agents" / f"{metadata.definition_id}.dependencies/mcp"
    root.mkdir()
    (root / "config.json").write_text(
        json.dumps({"private": {"name": "private", "command": "server"}})
    )
    monkeypatch.setattr(
        module,
        "read_and_remove_private_mcp_snapshot",
        lambda *_args, **_kwargs: {},
    )
    with pytest.raises(module.ExpertMainPreparationError):
        _prepare(tmp_path, definition)
    assert not list((tmp_path / ".expert_main_runs").iterdir())


def test_workspace_agents_symlink_cannot_read_another_profile(tmp_path):
    _, definition = _definition(tmp_path / "other")
    workspace = tmp_path / "current"
    workspace.mkdir()
    (workspace / "agents").symlink_to(
        tmp_path / "other/agents", target_is_directory=True
    )
    with pytest.raises(_module().ExpertMainPreparationError):
        _prepare(workspace, definition)


def test_undeclared_parent_mcp_is_not_inherited_by_expert_main(tmp_path):
    repository, definition = _definition(tmp_path)
    package = repository.get(definition.agent_owned.definition_id)
    payload = package.raw_payload
    payload.pop("mcps")
    package = repository._package_from_payload(package.definition_id, payload)
    repository._write(package)
    config = AgentProfileConfig.model_validate(
        {
            "id": "profile",
            "name": "Profile",
            "mcp": {
                "clients": {
                    "parent": {"name": "parent", "command": "parent-only"}
                }
            },
        }
    )
    prepared = _prepare(
        tmp_path, package.definition, parent_agent_config=config
    )
    assert not prepared.mcp_configs
    prepared.cleanup()


def test_parent_approval_and_network_constraints_are_retained(tmp_path):
    _, definition = _definition(tmp_path)
    parent = PermissionPolicy.readonly(allow_tools=["read_file", "write_file"])
    parent.network_enabled = True
    parent.tools.ask = ["read_file"]
    workspace = parent.model_copy(deep=True)
    workspace.network_enabled = False
    workspace.tools.ask = ["write_file"]
    prepared = _prepare(
        tmp_path, definition, parent_policy=parent, workspace_policy=workspace
    )
    assert prepared.permission.tools.ask == ["read_file", "write_file"]
    assert not prepared.permission.network_enabled
    prepared.cleanup()


def test_missing_noncommunity_mcp_keeps_nonfatal_diagnostics(tmp_path):
    repository, definition = _definition(tmp_path)
    package = repository.get(definition.agent_owned.definition_id)
    package = repository.update(
        package.definition_id,
        {"mcps": ["offline"]},
        expected_revision=package.revision,
    )
    prepared = _prepare(tmp_path, package.definition)
    assert not prepared.mcp_configs
    assert prepared.diagnostics.skipped_mcps == ["offline"]
    prepared.cleanup()


def test_disabled_profile_skill_is_not_loaded_from_declared_name(tmp_path):
    repository, definition = _definition(tmp_path)
    package = repository.get(definition.agent_owned.definition_id)
    package = repository.update(
        package.definition_id,
        {"skills": ["private"]},
        expected_revision=package.revision,
    )
    skill = tmp_path / "skills/private"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("disabled Skill body")
    (tmp_path / "skill.json").write_text(
        json.dumps(
            {
                "layout_version": 2,
                "skills": {"private": {"enabled": False, "channels": ["all"]}},
            }
        )
    )
    prepared = _prepare(tmp_path, package.definition)
    assert not prepared.skill_snapshot_dirs
    assert prepared.diagnostics.skipped_skills == ["private"]
    prepared.cleanup()


def test_empty_expert_skill_runtime_snapshot_never_looks_up_profile_config(
    tmp_path,
):
    _, definition = _definition(tmp_path)
    prepared = _prepare(tmp_path, definition)
    assert prepared.workspace_skill_snapshot is not None
    assert not prepared.workspace_skill_snapshot.skills
    prepared.cleanup()


def test_private_skill_runtime_snapshot_is_built_from_copied_private_root(
    tmp_path,
):
    repository, definition = _definition(tmp_path, community=True)
    package = repository.get(definition.agent_owned.definition_id)
    payload = {**package.raw_payload, "skills": ["private"]}
    package = repository._package_from_payload(package.definition_id, payload)
    repository._write(package)
    skill = (
        tmp_path
        / "agents"
        / f"{package.definition_id}.dependencies/skills/private"
    )
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("private skill")
    (tmp_path / "skill.json").write_text(
        json.dumps(
            {
                "skills": {
                    "private": {
                        "enabled": True,
                        "config": {"SECRET": "profile-only"},
                    }
                }
            }
        )
    )
    prepared = _prepare(tmp_path, package.definition)
    snapshot = prepared.workspace_skill_snapshot.skills["private"]
    assert str(snapshot.directory) == prepared.skill_snapshot_dirs[0]
    assert not snapshot.config
    prepared.cleanup()
