# -*- coding: utf-8 -*-
"""Source-aware SubAgent definition registry and provider interfaces."""

from __future__ import annotations

from typing import Protocol

from packaging.version import InvalidVersion, Version

from .models import DefinitionValidationError, SubAgentDefinition


class SubAgentDefinitionProvider(Protocol):
    """Provider interface for built-in or stored definitions."""

    def list_definitions(self) -> list[SubAgentDefinition]:
        """Return all definitions available from this provider."""


class InMemoryDefinitionProvider:
    """Simple provider used for built-ins and tests."""

    def __init__(self, definitions: list[SubAgentDefinition]):
        self._definitions = list(definitions)

    def list_definitions(self) -> list[SubAgentDefinition]:
        """Return provider definitions."""
        return list(self._definitions)


class AgentRegistry:
    """Resolve SubAgent definitions from ordered providers without shadowing."""

    def __init__(self, providers: list[SubAgentDefinitionProvider]):
        self._definitions: dict[tuple[str, str], SubAgentDefinition] = {}
        self._load(providers)

    def _load(self, providers: list[SubAgentDefinitionProvider]) -> None:
        builtin_names: set[str] = set()
        stored_names: set[str] = set()
        for provider in providers:
            for definition in provider.list_definitions():
                errors = definition.validation_errors()
                if errors:
                    raise DefinitionValidationError("; ".join(errors))
                if definition.source == "run_scoped":
                    raise DefinitionValidationError(
                        "run_scoped definition cannot be loaded into the "
                        f"SubAgent registry: {definition.name}",
                    )
                key = (definition.name, definition.version)
                if key in self._definitions:
                    raise DefinitionValidationError(
                        "duplicate SubAgent definition: "
                        f"{definition.name}@{definition.version}",
                    )
                if definition.source == "builtin":
                    if definition.name in stored_names:
                        raise DefinitionValidationError(
                            "stored definition cannot shadow builtin "
                            f"SubAgent definition: {definition.name}",
                        )
                    builtin_names.add(definition.name)
                elif definition.name in builtin_names:
                    raise DefinitionValidationError(
                        "stored definition cannot shadow builtin "
                        f"SubAgent definition: {definition.name}",
                    )
                else:
                    stored_names.add(definition.name)
                self._definitions[key] = definition

    @staticmethod
    def _version_sort_key(
        definition: SubAgentDefinition,
    ) -> tuple[int, Version | str]:
        """Prefer semantic versions while remaining stable for legacy strings."""
        try:
            return (1, Version(definition.version))
        except InvalidVersion:
            return (0, definition.version)

    def list(
        self,
        *,
        source: str | None = None,
        owner_scope: str | None = None,
    ) -> list[SubAgentDefinition]:
        """List definitions, optionally filtered by source or owner scope."""
        definitions = list(self._definitions.values())
        if source is not None:
            definitions = [d for d in definitions if d.source == source]
        if owner_scope is not None:
            definitions = [
                d for d in definitions if d.owner_scope == owner_scope
            ]
        return sorted(
            definitions,
            key=lambda d: (d.name, self._version_sort_key(d)),
        )

    def resolve(
        self,
        name: str,
        version: str | None = None,
    ) -> SubAgentDefinition:
        """Resolve a definition by name, using latest semantic version by default."""
        if version is not None:
            return self.get(name, version)
        matches = [
            definition
            for (definition_name, _), definition in self._definitions.items()
            if definition_name == name and definition.enabled
        ]
        if not matches:
            raise KeyError(name)
        return max(matches, key=self._version_sort_key)

    def get(self, name: str, version: str) -> SubAgentDefinition:
        """Return an exact definition version."""
        try:
            return self._definitions[(name, version)]
        except KeyError:
            raise KeyError(f"{name}@{version}") from None
