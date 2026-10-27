# -*- coding: utf-8 -*-
"""Prepare a private, bounded expert snapshot for one main Chat message."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Mapping
from uuid import UUID

from ...agents.skill_runtime_snapshot import (
    ManifestStat,
    SkillRuntimeSnapshot,
    WorkspaceSkillSnapshot,
    _freeze,
    get_workspace_skill_snapshot,
)
from ...agents.skill_runtime_profile import build_skill_runtime_profile
from ...agents.skills_manager import (
    _build_signature,
    _build_skill_metadata,
    get_skill_freshness_token,
)
from ...config.config import AgentProfileConfig, MCPClientConfig
from ...providers.models import ModelSlotConfig
from ..subagents.agent_definitions import AgentOwnedDefinitionRepository
from ..subagents.launch_snapshot import (
    _ensure_private_run_store_dir,
    _remove_snapshot_tree,
    capture_launch_dependencies,
    read_and_remove_private_mcp_snapshot,
    resolve_skill_owned_model_slot,
)
from ..subagents.models import (
    BudgetConfig,
    KNOWN_BUILTIN_TOOLS,
    PermissionPolicy,
    SubAgentDefinition,
    SubAgentLaunchDiagnostics,
)
from ..subagents.permissions import (
    build_definition_policy,
    compose_effective_policy,
)
from ..subagents.session_dependencies import (
    capture_community_expert_session_dependencies,
    initialize_community_expert_main_dependency_view,
)


class ExpertMainPreparationError(RuntimeError):
    """The selected expert cannot safely start this message."""


@dataclass(frozen=True)
class ExpertMainPreparationContext:
    workspace_dir: Path
    chat_id: str
    binding_revision: int
    tenant_id: str
    channel: str = "console"


@dataclass(frozen=True)
class PreparedExpertMainExecution:
    expert_id: str
    expert_name: str
    binding_revision: int
    instruction: str
    definition: SubAgentDefinition
    permission: PermissionPolicy
    budget: BudgetConfig
    skill_snapshot_dirs: tuple[str, ...]
    mcp_configs: Mapping[str, MCPClientConfig]
    model_slot: ModelSlotConfig | None
    community_version: str | None
    content_fingerprint: str | None
    diagnostics: SubAgentLaunchDiagnostics
    snapshot_root: Path
    workspace_skill_snapshot: WorkspaceSkillSnapshot

    def cleanup(self) -> None:
        """Release only this message's private files after execution ends."""
        _remove_snapshot_tree(self.snapshot_root)


def prepare_expert_main_execution(
    *,
    definition: SubAgentDefinition,
    context: ExpertMainPreparationContext,
    parent_agent_config: AgentProfileConfig,
    parent_policy: PermissionPolicy,
    workspace_policy: PermissionPolicy,
    chat_model_slot: ModelSlotConfig | None,
    main_budget: BudgetConfig | None = None,
) -> PreparedExpertMainExecution:
    """Validate an admitted Profile expert and capture its message resources.

    Chat/Source ownership and binding revision admission belong to the caller.
    Re-read the exact local expert ID and refuse stale definitions.
    It never connects MCPs or loads Profile long-term memory.
    """
    workspace = Path(context.workspace_dir).resolve()
    captured, revision = _current_definition(workspace, definition)
    policy = _expert_policy(captured, parent_policy, workspace_policy)
    budget = _message_budget(captured.budget, parent_agent_config, main_budget)
    chosen = (
        resolve_skill_owned_model_slot(context.tenant_id, captured)
        or chat_model_slot
    )
    root = workspace / ".expert_main_runs"
    _ensure_private_run_store_dir(root)
    snapshot_root = Path(tempfile.mkdtemp(prefix="message-", dir=root))
    snapshot_root.chmod(0o700)
    run_id = "dependencies"
    skills = {}
    try:
        view = initialize_community_expert_main_dependency_view(
            workspace_dir=workspace,
            chat_id=context.chat_id,
            definition=captured,
        )
        if view is not None:
            skill_dirs, mcp_path, diagnostics = (
                capture_community_expert_session_dependencies(
                    run_store_dir=snapshot_root,
                    run_id=run_id,
                    dependency_view_root=view,
                    definition=captured,
                    parent_agent_config=parent_agent_config,
                )
            )
        else:
            metadata = captured.agent_owned
            launch_definition = captured
            if metadata.declared_mcps is None:
                launch_definition = captured.model_copy(deep=True)
                launch_definition.agent_owned.declared_mcps = []
            skills = get_workspace_skill_snapshot(workspace).skills
            effective_names = [
                name
                for name, skill in skills.items()
                if "all" in skill.channels or context.channel in skill.channels
            ]
            skill_dirs, mcp_path, diagnostics = capture_launch_dependencies(
                run_store_dir=snapshot_root,
                run_id=run_id,
                workspace_dir=workspace,
                parent_agent_config=parent_agent_config,
                definition=launch_definition,
                effective_skill_names=effective_names,
                skill_snapshot_signatures={
                    name: skill.content_signature
                    for name, skill in skills.items()
                },
                skill_snapshot_dirs={
                    name: skill.directory for name, skill in skills.items()
                },
            )
        payload = read_and_remove_private_mcp_snapshot(
            mcp_path,
            run_store_dir=snapshot_root,
            run_id=run_id,
        )
        if set(payload) != set(diagnostics.snapshotted_mcps):
            raise ExpertMainPreparationError(
                "expert MCP capture is incomplete"
            )
        mcps = {
            name: MCPClientConfig.model_validate(raw)
            for name, raw in payload.items()
        }
        _, latest_revision = _current_definition(workspace, captured)
        if latest_revision != revision:
            raise ExpertMainPreparationError(
                "expert changed during preparation"
            )
        community = captured.agent_owned.community
        return PreparedExpertMainExecution(
            expert_id=captured.agent_owned.definition_id,
            expert_name=captured.name,
            binding_revision=context.binding_revision,
            instruction=captured.instruction,
            definition=captured,
            permission=policy,
            budget=budget,
            skill_snapshot_dirs=tuple(skill_dirs),
            mcp_configs=MappingProxyType(mcps),
            model_slot=(
                chosen.model_copy(deep=True) if chosen is not None else None
            ),
            community_version=community.version if community else None,
            content_fingerprint=(
                community.content_fingerprint if community else None
            ),
            diagnostics=diagnostics,
            snapshot_root=snapshot_root,
            workspace_skill_snapshot=_message_skill_snapshot(
                workspace,
                skill_dirs,
                skills,
            ),
        )
    except (OSError, ValueError) as exc:
        _remove_snapshot_tree(snapshot_root)
        raise ExpertMainPreparationError(
            "expert resources are unavailable"
        ) from exc
    except BaseException:
        _remove_snapshot_tree(snapshot_root)
        raise


def _current_definition(
    workspace: Path,
    definition: SubAgentDefinition,
) -> tuple[SubAgentDefinition, str]:
    metadata = definition.agent_owned
    if metadata is None:
        raise ExpertMainPreparationError(
            "expert must belong to the current Profile"
        )
    try:
        expert_id = str(UUID(metadata.definition_id))
    except ValueError as exc:
        raise ExpertMainPreparationError("expert identity is invalid") from exc
    if expert_id != metadata.definition_id:
        raise ExpertMainPreparationError("expert identity is invalid")
    path = workspace / "agents" / f"{expert_id}.toml"
    if path.parent.is_symlink():
        raise ExpertMainPreparationError("expert definition root is invalid")
    if path.is_symlink():
        raise ExpertMainPreparationError("expert definition path is invalid")
    repository = AgentOwnedDefinitionRepository(
        path.parent, owner_scope=definition.owner_scope
    )
    package = repository.get(expert_id)
    if (
        package is None
        or package.definition is None
        or not package.definition.enabled
    ):
        raise ExpertMainPreparationError("expert is unavailable")
    excluded = {"created_at", "updated_at"}
    if package.definition.model_dump(
        exclude=excluded
    ) != definition.model_dump(exclude=excluded):
        raise ExpertMainPreparationError("expert changed before preparation")
    return package.definition.model_copy(deep=True), package.revision


def _expert_policy(
    definition: SubAgentDefinition,
    parent: PermissionPolicy,
    workspace: PermissionPolicy,
) -> PermissionPolicy:
    policy = compose_effective_policy(
        parent,
        build_definition_policy(definition, parent),
        parent,
        workspace,
    )
    policy.tools.allow = sorted(set(policy.tools.allow) & KNOWN_BUILTIN_TOOLS)
    # Composition predates interactive main execution: retain approval/network
    # narrowing explicitly instead of broadening any source policy.
    policy.tools.ask = sorted(set(parent.tools.ask) | set(workspace.tools.ask))
    policy.network_enabled = (
        parent.network_enabled and workspace.network_enabled
    )
    return policy


def _message_budget(
    expert: BudgetConfig,
    profile: AgentProfileConfig,
    main_budget: BudgetConfig | None,
) -> BudgetConfig:
    values = expert.model_dump()
    values["max_turns"] = min(values["max_turns"], profile.running.max_iters)
    if main_budget is not None:
        values = {
            name: min(value, getattr(main_budget, name))
            for name, value in values.items()
        }
    return BudgetConfig(**values)


def _message_skill_snapshot(
    workspace: Path,
    paths: list[str],
    captured_skills: Mapping[str, SkillRuntimeSnapshot],
) -> WorkspaceSkillSnapshot:
    skills = {}
    for raw_path in paths:
        path = Path(raw_path)
        original = captured_skills.get(path.name)
        metadata = _build_skill_metadata(path.name, path, source="expert_main")
        skills[path.name] = SkillRuntimeSnapshot(
            directory=path,
            metadata=_freeze(metadata),
            content_signature=_build_signature(path),
            freshness_token=get_skill_freshness_token(path),
            runtime_profile=build_skill_runtime_profile(path, path.name),
            config=_freeze(dict(original.config) if original else {}),
            requirements=_freeze(
                dict(original.requirements)
                if original
                else metadata["requirements"]
            ),
            channels=original.channels if original else ("all",),
        )
    return WorkspaceSkillSnapshot(
        workspace_dir=workspace,
        generation=0,
        manifest_stat=ManifestStat(0, 0, 0),
        skills=MappingProxyType(skills),
    )
