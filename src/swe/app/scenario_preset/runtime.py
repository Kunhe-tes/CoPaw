# -*- coding: utf-8 -*-
"""Submit-time, non-sensitive snapshot construction for scenario chats."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .service import ScenarioPresetCatalogService

logger = logging.getLogger(__name__)

_SNAPSHOT_META_KEY = "scenario_preset_snapshot"


async def initialize_scenario_snapshot(
    *,
    service: ScenarioPresetCatalogService,
    source_id: str,
    scenario_id: str,
    agent_id: str | None,
    workspace_dir: Path | None = None,
    agent_config: Any | None = None,
) -> dict[str, Any]:
    """Validate current catalog state and create the immutable safe snapshot.

    Market resolution is deliberately deferred to a follow-up runtime adapter;
    the persisted contract already excludes text, payloads, configuration, and
    credentials so later resource resolution cannot accidentally leak them.
    """
    scenario, bindings, capability = await service.get_submittable_scenario(
        source_id,
        scenario_id,
    )
    skill_names = _resolve_local_skill_names(workspace_dir, bindings)
    resources: list[dict[str, Any]] = [
        _resource_snapshot(binding, skill_names, agent_config)
        for binding in bindings
    ]
    snapshot: dict[str, Any] = {
        "scenario_id": scenario.id,
        "capability_id": capability.id,
        "capability_name": capability.name,
        "agent_id": agent_id,
        "resources": resources,
    }
    logger.info(
        "scenario_preset_initialized source_id=%s scenario_id=%s agent_id=%s resource_outcomes=%s",
        source_id,
        scenario.id,
        agent_id,
        [
            {
                "id": item["id"],
                "type": item["type"],
                "status": item["status"],
            }
            for item in resources
        ],
    )
    return snapshot


def _resolve_local_skill_names(
    workspace_dir: Path | None,
    bindings: list[Any],
) -> dict[str, str]:
    if workspace_dir is None:
        return {}
    from ..runner.skill_selection import resolve_scenario_skill_names

    resolved: dict[str, str] = {}
    for binding in bindings:
        if binding.resource_type.value != "skill":
            continue
        names = resolve_scenario_skill_names(
            workspace_dir=workspace_dir,
            channel="console",
            resource_ids=[binding.resource_id],
        )
        if names:
            resolved[binding.resource_id] = names[0]
    return resolved


def _resource_snapshot(
    binding: Any,
    skill_names: dict[str, str],
    agent_config: Any | None,
) -> dict[str, Any]:
    resource = {
        "id": binding.resource_id,
        "type": binding.resource_type.value,
        "status": "unresolved",
    }
    if binding.resource_type.value == "skill":
        matching_name = skill_names.get(binding.resource_id)
        if matching_name is not None:
            resource.update(
                {"status": "persistent", "skill_name": matching_name},
            )
    elif binding.resource_type.value == "mcp_service":
        matching_key = _resolve_local_mcp_client_key(agent_config, binding.resource_id)
        if matching_key is not None:
            resource.update(
                {
                    "status": "persistent",
                    "mcp_client_key": matching_key,
                },
            )
    return resource


def _resolve_local_mcp_client_key(
    agent_config: Any | None,
    resource_id: str,
) -> str | None:
    mcp_config = getattr(agent_config, "mcp", None)
    clients = getattr(mcp_config, "clients", None)
    if not isinstance(clients, dict):
        return None
    expected_source = f"marketplace:{resource_id}"
    for key, client in clients.items():
        if not getattr(client, "enabled", False):
            continue
        if getattr(client, "source", "") != expected_source:
            continue
        market_key = str(getattr(client, "market_client_key", "") or "").strip()
        return market_key or str(key)
    return None


def get_scenario_snapshot(
    meta: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Read a previously initialized snapshot without re-querying catalog data."""
    snapshot = (meta or {}).get(_SNAPSHOT_META_KEY)
    return dict(snapshot) if isinstance(snapshot, dict) else None


def with_scenario_snapshot(
    meta: dict[str, Any] | None,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Return a ChatSpec metadata merge that preserves unrelated fields."""
    return {**(meta or {}), _SNAPSHOT_META_KEY: snapshot}


def scenario_snapshot_skill_names(
    snapshot: dict[str, Any] | None,
) -> list[str]:
    """Return only validated skill names captured in an immutable chat snapshot."""
    result: list[str] = []
    for resource in (snapshot or {}).get("resources", []):
        if not isinstance(resource, dict) or resource.get("type") != "skill":
            continue
        name = resource.get("skill_name")
        if isinstance(name, str) and name.strip():
            result.append(name.strip())
    return result
