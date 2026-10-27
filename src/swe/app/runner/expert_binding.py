# -*- coding: utf-8 -*-
"""Server-owned Chat identity and optimistic concurrency contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

EXPERT_BINDING_META_KEY = "expert_main_binding"


class ChatExpertBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    revision: int = Field(default=0, ge=0)
    expert_id: str | None = None


class ExpertBindingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0, strict=True)
    expert_id: str | None = Field(min_length=1, strict=True)

    @field_validator("expert_id")
    @classmethod
    def reject_blank_expert_id(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("expert_id must be null or non-blank")
        return value


class ExpertBindingView(ChatExpertBinding):
    enabled: bool
    available: bool
    expert_name: str | None = None
    reason: str | None = None


class ExpertBindingConflict(ValueError):
    def __init__(self, binding: ChatExpertBinding):
        super().__init__("Expert binding changed")
        self.binding = binding


class ExpertBindingModeConflict(ValueError):
    """Persistent experts are supported only in ordinary Chat."""


def read_expert_binding(chat) -> ChatExpertBinding:
    payload = (getattr(chat, "meta", None) or {}).get(EXPERT_BINDING_META_KEY)
    return ChatExpertBinding.model_validate(payload or {})


def is_ordinary_chat(chat) -> bool:
    return not any(
        (getattr(chat, "meta", None) or {}).get(key) is True
        for key in (
            "plan_mode_enabled",
            "goal_mode_enabled",
        )
    )


def resolve_bound_expert(workspace, expert_id: str):
    """Resolve the exact local ID inside the currently authorized Profile."""
    from pathlib import Path
    from ..subagents import (
        AgentOwnedDefinitionRepository,
        builtin_definition_provider,
    )

    names = {
        item.name for item in builtin_definition_provider().list_definitions()
    }
    try:
        package = AgentOwnedDefinitionRepository(
            Path(workspace.workspace_dir) / "agents",
            owner_scope=(
                f"{workspace.tenant_id or 'default'}/{workspace.agent_id}"
            ),
            builtin_names=names,
        ).get(expert_id)
    except (OSError, ValueError):
        return None
    definition = package.definition if package else None
    return (
        definition
        if definition and definition.enabled and definition.name not in names
        else None
    )


async def expert_main_enabled_for_request(request) -> bool:
    from ..source_system_config.registry import is_expert_as_main_enabled

    service = getattr(request.app.state, "source_system_config_service", None)
    source_id = getattr(request.state, "source_id", None)
    config = getattr(request.state, "source_system_config", None)
    if service is not None and source_id:
        config = await service.resolve_config(source_id, force_refresh=True)
    return is_expert_as_main_enabled(config)


async def binding_view(workspace, chat, *, enabled: bool) -> ExpertBindingView:
    from swe.runtime_workers import run_runtime_state_work

    binding = read_expert_binding(chat)
    definition = (
        (
            await run_runtime_state_work(
                resolve_bound_expert, workspace, binding.expert_id
            )
        )
        if binding.expert_id
        else None
    )
    return ExpertBindingView(
        **binding.model_dump(),
        enabled=enabled,
        available=binding.expert_id is None or definition is not None,
        expert_name=definition.name if definition else None,
        reason=(
            "expert_unavailable"
            if enabled and binding.expert_id and definition is None
            else None
        ),
    )


async def reconcile_binding(workspace, chat, *, enabled: bool):
    """Disabling persists a release, so re-enabling cannot resurrect it."""
    if not enabled:
        await workspace.chat_manager.release_current_expert_binding(chat.id)
        chat = await workspace.chat_manager.get_chat(chat.id)
    return chat
