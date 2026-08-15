# -*- coding: utf-8 -*-
"""Agent-owned TOML SubAgent Definition packages."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import tomllib
from typing import Any
from uuid import UUID, uuid4

import fcntl

from .models import (
    AgentOwnedDefinitionMetadata,
    BudgetConfig,
    KNOWN_BUILTIN_TOOLS,
    SkillOwnedModelReference,
    SkillOwnedToolConfig,
    SubAgentDefinition,
)

_MANAGED_TOP_LEVEL_KEYS = frozenset(
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
        "enabled",
    },
)
_MAX_BUDGETS = {
    "max_turns": BudgetConfig().max_turns,
    "max_tool_calls": BudgetConfig().max_tool_calls,
    "timeout_ms": BudgetConfig().timeout_ms,
}
_ROOT_LOCKS: dict[Path, threading.RLock] = {}
_ROOT_LOCKS_GUARD = threading.Lock()
_BARE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class AgentOwnedDefinitionConflict(ValueError):
    """Raised when a package mutation cannot apply to its current revision."""


@dataclass(frozen=True)
class AgentOwnedDefinitionPackage:
    """A read-only view of one package and its validation state."""

    definition_id: str
    revision: str
    toml: str
    definition: SubAgentDefinition | None
    raw_payload: dict[str, Any]
    validation_error: str = ""

    @property
    def valid(self) -> bool:
        return self.definition is not None


class AgentOwnedDefinitionRepository:
    """Persist Agent-owned Definition packages as revisioned TOML files."""

    def __init__(
        self,
        root: Path,
        *,
        owner_scope: str,
        builtin_names: set[str] | None = None,
    ) -> None:
        self._root = Path(root)
        self._owner_scope = owner_scope
        self._builtin_names = set(builtin_names or [])

    def list(self) -> list[AgentOwnedDefinitionPackage]:
        if not self._root.exists():
            return []
        return [
            self._read_path(path)
            for path in sorted(self._root.glob("*.toml"))
            if _is_definition_id(path.stem)
        ]

    def get(self, definition_id: str) -> AgentOwnedDefinitionPackage | None:
        path = self._path_for_id(definition_id)
        return self._read_path(path) if path.exists() else None

    def create(self, payload: dict[str, Any]) -> AgentOwnedDefinitionPackage:
        with self._mutation_lock():
            definition_id = str(uuid4())
            normalized = dict(payload)
            normalized["enabled"] = False
            package = self._package_from_payload(definition_id, normalized)
            self._write(package)
            return self.get(definition_id)  # type: ignore[return-value]

    def update(
        self,
        definition_id: str,
        payload: dict[str, Any],
        *,
        expected_revision: str,
    ) -> AgentOwnedDefinitionPackage:
        with self._mutation_lock():
            current = self._require_current(definition_id, expected_revision)
            normalized = _merge_update_payload(current.raw_payload, payload)
            if current.definition is not None:
                normalized["enabled"] = current.definition.enabled
            package = self._package_from_payload(definition_id, normalized)
            if package.definition.enabled:
                self._validate_enabled_name(
                    package.definition.name,
                    definition_id,
                )
            self._write(package)
            return self.get(definition_id)  # type: ignore[return-value]

    def enable(
        self,
        definition_id: str,
        *,
        expected_revision: str,
    ) -> AgentOwnedDefinitionPackage:
        with self._mutation_lock():
            current = self._require_current(definition_id, expected_revision)
            if current.definition is None:
                raise AgentOwnedDefinitionConflict(
                    "definition package is invalid",
                )
            self._validate_enabled_name(current.definition.name, definition_id)
            payload = dict(current.raw_payload)
            payload["enabled"] = True
            package = self._package_from_payload(definition_id, payload)
            self._write(package)
            return self.get(definition_id)  # type: ignore[return-value]

    def disable(
        self,
        definition_id: str,
        *,
        expected_revision: str,
    ) -> AgentOwnedDefinitionPackage:
        with self._mutation_lock():
            current = self._require_current(definition_id, expected_revision)
            if current.definition is None:
                raise AgentOwnedDefinitionConflict(
                    "definition package is invalid",
                )
            payload = dict(current.raw_payload)
            payload["enabled"] = False
            package = self._package_from_payload(definition_id, payload)
            self._write(package)
            return self.get(definition_id)  # type: ignore[return-value]

    def delete(self, definition_id: str, *, expected_revision: str) -> None:
        with self._mutation_lock():
            current = self._require_current(definition_id, expected_revision)
            self._path_for_id(current.definition_id).unlink()

    def _require_current(
        self,
        definition_id: str,
        expected_revision: str,
    ) -> AgentOwnedDefinitionPackage:
        current = self.get(definition_id)
        if current is None:
            raise AgentOwnedDefinitionConflict(
                "definition package does not exist",
            )
        if current.revision != expected_revision:
            raise AgentOwnedDefinitionConflict(
                "definition package has changed",
            )
        return current

    def _validate_enabled_name(self, name: str, definition_id: str) -> None:
        if name in self._builtin_names:
            raise AgentOwnedDefinitionConflict(
                f"definition name conflicts with builtin: {name}",
            )
        for package in self.list():
            definition = package.definition
            if (
                package.definition_id != definition_id
                and definition is not None
                and definition.enabled
                and definition.name == name
            ):
                raise AgentOwnedDefinitionConflict(
                    f"definition name conflicts with enabled package: {name}",
                )

    def _read_path(self, path: Path) -> AgentOwnedDefinitionPackage:
        definition_id = path.stem
        try:
            raw = path.read_bytes()
            toml = raw.decode("utf-8")
            revision = _revision(raw)
            payload = tomllib.loads(toml)
        except (
            OSError,
            UnicodeDecodeError,
            tomllib.TOMLDecodeError,
        ) as exc:
            return self._invalid_package(
                definition_id,
                raw if "raw" in locals() else b"",
                toml if "toml" in locals() else "",
                f"invalid TOML: {exc}",
            )
        try:
            definition = self._definition_from_payload(definition_id, payload)
        except ValueError as exc:
            return self._invalid_package(
                definition_id,
                raw,
                toml,
                f"invalid definition: {exc}",
            )
        return AgentOwnedDefinitionPackage(
            definition_id=definition_id,
            revision=revision,
            toml=toml,
            definition=definition,
            raw_payload=payload,
        )

    @staticmethod
    def _invalid_package(
        definition_id: str,
        raw: bytes,
        toml: str,
        validation_error: str,
    ) -> AgentOwnedDefinitionPackage:
        return AgentOwnedDefinitionPackage(
            definition_id=definition_id,
            revision=_revision(raw),
            toml=toml,
            definition=None,
            raw_payload={},
            validation_error=validation_error,
        )

    def _package_from_payload(
        self,
        definition_id: str,
        payload: dict[str, Any],
    ) -> AgentOwnedDefinitionPackage:
        definition = self._definition_from_payload(definition_id, payload)
        normalized = _normalize_payload(payload, definition)
        toml = _render_toml(normalized)
        return AgentOwnedDefinitionPackage(
            definition_id=definition_id,
            revision=_revision(toml),
            toml=toml,
            definition=definition,
            raw_payload=normalized,
        )

    def _definition_from_payload(
        self,
        definition_id: str,
        payload: dict[str, Any],
    ) -> SubAgentDefinition:
        _validate_definition_id(definition_id)
        name = _string(payload.get("name"), "name")
        if any(separator in name for separator in (":", "/", "\\")):
            raise ValueError("name contains an unsafe separator")
        description = _string(payload.get("description"), "description")
        instruction = _string(payload.get("instruction"), "instruction")
        enabled = payload.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        metadata = AgentOwnedDefinitionMetadata(
            definition_id=definition_id,
            declared_skills=_string_list(payload.get("skills"), "skills"),
            declared_mcps=(
                _string_list(payload.get("mcps"), "mcps")
                if "mcps" in payload
                else None
            ),
            tools=_parse_tools(payload.get("tools")),
            model=_parse_model(payload.get("model")),
        )
        return SubAgentDefinition(
            name=name,
            source="agent_owned",
            owner_scope=self._owner_scope,
            enabled=enabled,
            description=description,
            instruction=instruction,
            trigger_keywords=_string_list(
                payload.get("trigger_keywords"),
                "trigger_keywords",
            ),
            budget=_parse_budget(payload.get("budget")),
            agent_owned=metadata,
        )

    def _path_for_id(self, definition_id: str) -> Path:
        _validate_definition_id(definition_id)
        return self._root / f"{definition_id}.toml"

    def _write(self, package: AgentOwnedDefinitionPackage) -> None:
        path = self._path_for_id(package.definition_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.stem}-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(package.toml)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_path = Path(handle.name)
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @contextmanager
    def _mutation_lock(self):
        self._root.mkdir(parents=True, exist_ok=True)
        with _root_lock(self._root):
            lock_path = self._root / ".definitions.lock"
            with lock_path.open("a+") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _normalize_payload(
    payload: dict[str, Any],
    definition: SubAgentDefinition,
) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.update(
        {
            "name": definition.name,
            "description": definition.description,
            "instruction": definition.instruction,
            "trigger_keywords": definition.trigger_keywords,
            "enabled": definition.enabled,
            "skills": definition.agent_owned.declared_skills,
            "tools": _merge_table(
                payload.get("tools"),
                definition.agent_owned.tools.model_dump(),
            ),
            "budget": _merge_table(
                payload.get("budget"),
                definition.budget.model_dump(),
            ),
        },
    )
    if definition.agent_owned.declared_mcps is None:
        normalized.pop("mcps", None)
    else:
        normalized["mcps"] = definition.agent_owned.declared_mcps
    if definition.agent_owned.model is None:
        normalized.pop("model", None)
    else:
        normalized["model"] = _merge_table(
            payload.get("model"),
            definition.agent_owned.model.model_dump(),
        )
    return normalized


def _merge_table(value: Any, managed: dict[str, Any]) -> dict[str, Any]:
    return {**(value if isinstance(value, dict) else {}), **managed}


def _merge_update_payload(
    current: dict[str, Any],
    updated: dict[str, Any],
) -> dict[str, Any]:
    merged = {**current, **updated}
    for field in ("tools", "model", "budget"):
        if field in current and field in updated:
            merged[field] = _merge_table(current[field], updated[field])
    return merged


def _parse_tools(value: Any) -> SkillOwnedToolConfig:
    if value is None:
        return SkillOwnedToolConfig()
    if not isinstance(value, dict):
        raise ValueError("tools must be a table")
    inherit = value.get("inherit", True)
    if not isinstance(inherit, bool):
        raise ValueError("tools.inherit must be a boolean")
    allow = _string_list(value.get("allow"), "tools.allow")
    deny = _string_list(value.get("deny"), "tools.deny")
    unknown = sorted((set(allow) | set(deny)) - KNOWN_BUILTIN_TOOLS)
    if unknown:
        raise ValueError(f"unknown built-in tool: {', '.join(unknown)}")
    return SkillOwnedToolConfig(inherit=inherit, allow=allow, deny=deny)


def _parse_model(value: Any) -> SkillOwnedModelReference | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("model must be a table")
    return SkillOwnedModelReference(
        provider=_string(value.get("provider"), "model.provider"),
        id=_string(value.get("id"), "model.id"),
    )


def _parse_budget(value: Any) -> BudgetConfig:
    if value is None:
        return BudgetConfig()
    if not isinstance(value, dict):
        raise ValueError("budget must be a table")
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


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise ValueError(f"{field} must be an array of strings")
    cleaned = [item.strip() for item in value]
    if not all(cleaned) or len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{field} contains an empty or duplicate item")
    return cleaned


def _validate_definition_id(definition_id: str) -> None:
    try:
        canonical_id = str(UUID(definition_id))
    except (TypeError, ValueError) as exc:
        raise ValueError("definition id must be a UUID") from exc
    if definition_id != canonical_id:
        raise ValueError("definition id must use canonical UUID format")


def _is_definition_id(definition_id: str) -> bool:
    try:
        _validate_definition_id(definition_id)
    except ValueError:
        return False
    return True


def _revision(toml: str | bytes) -> str:
    raw = toml.encode("utf-8") if isinstance(toml, str) else toml
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _render_toml(payload: dict[str, Any]) -> str:
    scalar_items = [
        (key, value)
        for key, value in payload.items()
        if not isinstance(value, dict)
    ]
    table_items = [
        (key, value)
        for key, value in payload.items()
        if isinstance(value, dict)
    ]
    lines = [_render_assignment(key, value) for key, value in scalar_items]
    for key, value in table_items:
        lines.extend(["", f"[{_render_key(key)}]"])
        lines.extend(
            _render_assignment(item_key, item_value)
            for item_key, item_value in value.items()
        )
    return "\n".join(lines) + "\n"


def _render_assignment(key: str, value: Any) -> str:
    return f"{_render_key(key)} = {_render_value(value)}"


def _render_key(key: str) -> str:
    return (
        key
        if _BARE_KEY_PATTERN.fullmatch(key)
        else json.dumps(key, ensure_ascii=False)
    )


def _render_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(_render_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return (
            "{ "
            + ", ".join(
                f"{_render_key(key)} = {_render_value(item)}"
                for key, item in value.items()
            )
            + " }"
        )
    raise ValueError(f"unsupported TOML value: {type(value).__name__}")


def _root_lock(root: Path) -> threading.RLock:
    resolved = root.resolve()
    with _ROOT_LOCKS_GUARD:
        return _ROOT_LOCKS.setdefault(resolved, threading.RLock())
