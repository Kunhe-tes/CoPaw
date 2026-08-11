# -*- coding: utf-8 -*-
"""Deterministic SubAgent definition matching."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .models import (
    DefinitionMatchMetadata,
    SubAgentDefinition,
    SubAgentStartRequest,
)

SHORT_CIRCUIT_THRESHOLD = 0.85


@dataclass(frozen=True)
class DefinitionMatchResult:
    """Resolved definition and persisted match metadata."""

    definition: SubAgentDefinition
    metadata: DefinitionMatchMetadata


def normalize_name(value: str) -> str:
    """Normalize user-facing SubAgent names for deterministic matching."""
    value = value.strip().casefold()
    return re.sub(r"[\s_-]+", "-", value)


class SubAgentDefinitionMatcher:
    """Rule-based matcher for stored and built-in SubAgent definitions."""

    def match(
        self,
        request: SubAgentStartRequest,
        candidates: list[SubAgentDefinition],
    ) -> DefinitionMatchResult | None:
        """Return the best confident match, or None for run-scoped fallback."""
        scored = [
            result
            for candidate in candidates
            if candidate.enabled
            for result in [self._score(request, candidate)]
            if result is not None
        ]
        if not scored:
            return None
        scored.sort(key=self._sort_key)
        best = scored[0]
        if (best.metadata.score or 0) < SHORT_CIRCUIT_THRESHOLD:
            return None
        return best

    def _score(
        self,
        request: SubAgentStartRequest,
        candidate: SubAgentDefinition,
    ) -> DefinitionMatchResult | None:
        if request.name == candidate.name:
            return self._result(candidate, 1.0, "exact_name")
        if normalize_name(request.name) == normalize_name(candidate.name):
            return self._result(candidate, 0.95, "normalized_name")

        query = " ".join(
            [request.name, request.objective, request.background],
        ).casefold()
        normalized_keywords = {
            keyword.strip().casefold()
            for keyword in candidate.trigger_keywords
            if keyword.strip()
        }
        keyword_hits = [
            keyword for keyword in normalized_keywords if keyword in query
        ]
        if keyword_hits:
            score = min(0.85, 0.65 + 0.1 * len(keyword_hits))
            return self._result(candidate, score, "trigger_keywords")

        task_hits = [
            task_type
            for task_type in candidate.task_types
            if task_type.strip().casefold() in query
        ]
        if task_hits:
            return self._result(candidate, 0.75, "task_types")

        description = candidate.description.strip().casefold()
        if description and description in query:
            return self._result(candidate, 0.70, "description")

        return None

    def _result(
        self,
        definition: SubAgentDefinition,
        score: float,
        reason: str,
    ) -> DefinitionMatchResult:
        return DefinitionMatchResult(
            definition=definition,
            metadata=DefinitionMatchMetadata(
                matched=True,
                definition_name=definition.name,
                definition_source=definition.source,
                score=score,
                reason=reason,
            ),
        )

    def _sort_key(self, result: DefinitionMatchResult) -> tuple:
        definition = result.definition
        source_rank = 0 if definition.source == "stored" else 1
        return (
            -(result.metadata.score or 0),
            source_rank,
            definition.priority,
            -definition.updated_at.timestamp(),
            definition.name,
        )
