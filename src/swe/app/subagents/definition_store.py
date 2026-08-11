# -*- coding: utf-8 -*-
"""Tenant-and-agent scoped stored SubAgent definition persistence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .models import SubAgentDefinition

MAX_DEFINITION_FILENAME_STEM_CHARS = 80
DEFINITION_FILENAME_DIGEST_CHARS = 12


@dataclass(frozen=True)
class DefinitionUpsertResult:
    """Result of writing one stored SubAgent definition."""

    created: bool
    definition: SubAgentDefinition


class SubAgentDefinitionStore:
    """One JSON file per stored SubAgent definition."""

    def __init__(self, root: Path):
        self._root = Path(root)

    def list_definitions(self) -> list[SubAgentDefinition]:
        """Return all stored definitions in deterministic file order."""
        if not self._root.exists():
            return []
        definitions: list[SubAgentDefinition] = []
        for path in sorted(self._root.glob("*.json")):
            definitions.append(
                SubAgentDefinition.model_validate_json(
                    path.read_text(encoding="utf-8"),
                ),
            )
        return definitions

    def get(self, name: str) -> SubAgentDefinition | None:
        """Return one stored definition by name."""
        path = self._path_for_name(name)
        if not path.exists():
            return None
        return SubAgentDefinition.model_validate_json(
            path.read_text(encoding="utf-8"),
        )

    def upsert(
        self,
        definition: SubAgentDefinition,
    ) -> DefinitionUpsertResult:
        """Create or replace a stored definition file."""
        path = self._path_for_name(definition.name)
        created = not path.exists()
        self._root.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                definition.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return DefinitionUpsertResult(
            created=created,
            definition=definition,
        )

    def _path_for_name(self, name: str) -> Path:
        raw = name.strip()
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._-")
        slug = slug[:MAX_DEFINITION_FILENAME_STEM_CHARS] or "definition"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return (
            self._root
            / f"{slug}-{digest[:DEFINITION_FILENAME_DIGEST_CHARS]}.json"
        )
