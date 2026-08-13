# -*- coding: utf-8 -*-
"""Load strict, Skill-owned SubAgent Definition TOML packages."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import (
    BudgetConfig,
    KNOWN_BUILTIN_TOOLS,
    SkillOwnedDefinitionMetadata,
    SkillOwnedModelReference,
    SkillOwnedToolConfig,
    SubAgentDefinition,
)

_TOP_LEVEL_KEYS = frozenset(
    {
        "name",
        "description",
        "instruction",
        "trigger_keywords",
        "skills",
        "mcps",
        "tools",
        "model",
        "budget",
    },
)
_TOOLS_KEYS = frozenset({"inherit", "allow", "deny"})
_MODEL_KEYS = frozenset({"provider", "id"})
_BUDGET_KEYS = frozenset({"max_turns", "max_tool_calls", "timeout_ms"})
_MAX_BUDGETS = {
    "max_turns": BudgetConfig().max_turns,
    "max_tool_calls": BudgetConfig().max_tool_calls,
    "timeout_ms": BudgetConfig().timeout_ms,
}


@dataclass(frozen=True)
class SkillDefinitionLoadError:
    """A single invalid package; other packages remain loadable."""

    path: Path
    message: str


@dataclass(frozen=True)
class SkillDefinitionLoadResult:
    definitions: list[SubAgentDefinition]
    errors: list[SkillDefinitionLoadError]


def _unknown_keys(payload: dict[str, Any], allowed: frozenset[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unknown field(s): {', '.join(unknown)}")


def _string(value: Any, field: str, *, allow_blank: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    cleaned = value.strip()
    if not allow_blank and not cleaned:
        raise ValueError(f"{field} must be non-empty")
    return cleaned


def _string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array of strings")
    return [_string(item, field) for item in value]


def _parse_budget(value: Any) -> BudgetConfig:
    if value is None:
        return BudgetConfig()
    if not isinstance(value, dict):
        raise ValueError("budget must be a table")
    _unknown_keys(value, _BUDGET_KEYS)
    parsed: dict[str, int] = {}
    for field, maximum in _MAX_BUDGETS.items():
        if field not in value:
            continue
        item = value[field]
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"budget.{field} must be an integer")
        if item <= 0 or item > maximum:
            raise ValueError(
                f"budget.{field} must be between 1 and {maximum}",
            )
        parsed[field] = item
    return BudgetConfig(**parsed)


def _parse_tools(value: Any) -> SkillOwnedToolConfig:
    if value is None:
        return SkillOwnedToolConfig()
    if not isinstance(value, dict):
        raise ValueError("tools must be a table")
    _unknown_keys(value, _TOOLS_KEYS)
    inherit = value.get("inherit", True)
    if not isinstance(inherit, bool):
        raise ValueError("tools.inherit must be a boolean")
    allow = _string_list(value.get("allow"), "tools.allow")
    deny = _string_list(value.get("deny"), "tools.deny")
    invalid = sorted((set(allow) | set(deny)) - KNOWN_BUILTIN_TOOLS)
    if invalid:
        raise ValueError(f"unknown built-in tool: {', '.join(invalid)}")
    return SkillOwnedToolConfig(inherit=inherit, allow=allow, deny=deny)


def _parse_model(value: Any) -> SkillOwnedModelReference | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("model must be a table")
    _unknown_keys(value, _MODEL_KEYS)
    if "provider" not in value or "id" not in value:
        raise ValueError("model requires provider and id")
    return SkillOwnedModelReference(
        provider=_string(value["provider"], "model.provider"),
        id=_string(value["id"], "model.id"),
    )


def _load_one(path: Path, skill_name: str) -> SubAgentDefinition:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"invalid TOML: {exc}") from exc
    _unknown_keys(payload, _TOP_LEVEL_KEYS)
    local_name = _string(payload.get("name"), "name")
    if ":" in local_name or "/" in local_name or "\\" in local_name:
        raise ValueError("name contains an unsafe separator")
    description = _string(payload.get("description"), "description")
    instruction = _string(payload.get("instruction"), "instruction")
    declared_skills = _string_list(payload.get("skills"), "skills")
    declared_mcps = _string_list(payload.get("mcps"), "mcps")
    trigger_keywords = _string_list(
        payload.get("trigger_keywords"),
        "trigger_keywords",
    )
    tools = _parse_tools(payload.get("tools"))
    model = _parse_model(payload.get("model"))
    budget = _parse_budget(payload.get("budget"))
    metadata = SkillOwnedDefinitionMetadata(
        skill_name=skill_name,
        local_name=local_name,
        declared_skills=declared_skills,
        declared_mcps=declared_mcps,
        tools=tools,
        model=model,
    )
    return SubAgentDefinition(
        name=f"{skill_name}:{local_name}",
        source="stored",
        owner_scope=f"skill:{skill_name}",
        description=description,
        instruction=instruction,
        trigger_keywords=trigger_keywords,
        budget=budget,
        skill_owned=metadata,
    )


def load_skill_owned_definitions(
    *,
    workspace_dir: Path,
    effective_skill_names: list[str],
) -> SkillDefinitionLoadResult:
    """Load valid agent packages from the effective Skill runtime view."""
    definitions: list[SubAgentDefinition] = []
    errors: list[SkillDefinitionLoadError] = []
    seen_local_names: dict[tuple[str, str], Path] = {}
    for skill_name in effective_skill_names:
        agents_dir = Path(workspace_dir) / "skills" / skill_name / "agents"
        if not agents_dir.is_dir():
            continue
        for path in sorted(agents_dir.glob("*.toml")):
            try:
                definition = _load_one(path, skill_name)
                local_name = definition.skill_owned.local_name  # type: ignore[union-attr]
                name_key = (skill_name, local_name)
                if name_key in seen_local_names:
                    raise ValueError(f"duplicate local name: {local_name}")
                seen_local_names[name_key] = path
                definitions.append(definition)
            except (ValueError, ValidationError) as exc:
                errors.append(SkillDefinitionLoadError(path, str(exc)))
    return SkillDefinitionLoadResult(definitions=definitions, errors=errors)
