# -*- coding: utf-8 -*-
"""Deterministic SubAgent definition matcher tests."""

from __future__ import annotations

from datetime import datetime, timezone

from swe.app.subagents import (
    AgentRegistry,
    SubAgentDefinition,
    SubAgentDefinitionMatcher,
    SubAgentDefinitionService,
    SubAgentDefinitionStore,
    SubAgentStartRequest,
    builtin_definition_provider,
)


def _definition(
    name: str,
    *,
    source: str = "stored",
    priority: int = 100,
    enabled: bool = True,
    trigger_keywords: list[str] | None = None,
    task_types: list[str] | None = None,
    description: str = "Research analyst.",
) -> SubAgentDefinition:
    return SubAgentDefinition.model_validate(
        {
            "name": name,
            "source": source,
            "enabled": enabled,
            "description": description,
            "instruction": f"Act as {name}.",
            "trigger_keywords": trigger_keywords or [],
            "task_types": task_types or [],
            "priority": priority,
            "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        },
    )


def _request(
    name: str = "research analyst",
    objective: str = "Analyze 1M AUM customer maintenance.",
) -> SubAgentStartRequest:
    return SubAgentStartRequest.model_validate(
        {
            "name": name,
            "instruction": "Act as a customer strategy analyst.",
            "objective": objective,
            "background": "Need AUM and 客户维护 advice.",
        },
    )


def test_exact_name_match_short_circuits() -> None:
    matcher = SubAgentDefinitionMatcher()
    result = matcher.match(
        _request("risk-reviewer"),
        [_definition("risk-reviewer")],
    )

    assert result is not None
    assert result.definition.name == "risk-reviewer"
    assert result.metadata.score == 1.0
    assert result.metadata.reason == "exact_name"


def test_normalized_name_match_short_circuits() -> None:
    matcher = SubAgentDefinitionMatcher()
    result = matcher.match(
        _request("Research Analyst"),
        [_definition("research_analyst")],
    )

    assert result is not None
    assert result.metadata.score == 0.95
    assert result.metadata.reason == "normalized_name"


def test_keyword_match_can_short_circuit_at_threshold() -> None:
    matcher = SubAgentDefinitionMatcher()
    result = matcher.match(
        _request("customer worker"),
        [
            _definition(
                "aum-customer-analyst",
                trigger_keywords=["AUM", "客户维护"],
            ),
        ],
    )

    assert result is not None
    assert result.definition.name == "aum-customer-analyst"
    assert result.metadata.score == 0.85


def test_low_score_falls_back_without_match() -> None:
    matcher = SubAgentDefinitionMatcher()
    result = matcher.match(
        _request("customer worker", "Summarize meeting notes."),
        [_definition("risk-reviewer", task_types=["risk"])],
    )

    assert result is None


def test_duplicate_keywords_do_not_inflate_score_to_threshold() -> None:
    matcher = SubAgentDefinitionMatcher()
    result = matcher.match(
        _request("risk worker", "Summarize risk."),
        [
            _definition(
                "risk-reviewer",
                trigger_keywords=["risk", " risk "],
            ),
        ],
    )

    assert result is None


def test_ties_use_stored_then_priority_then_name() -> None:
    matcher = SubAgentDefinitionMatcher()
    request = _request("customer worker")
    stored = _definition(
        "stored-a",
        source="stored",
        priority=20,
        trigger_keywords=["AUM", "客户维护"],
    )
    builtin = _definition(
        "builtin-a",
        source="builtin",
        priority=1,
        trigger_keywords=["AUM", "客户维护"],
    )

    result = matcher.match(request, [builtin, stored])

    assert result is not None
    assert result.definition.name == "stored-a"


def test_same_source_ties_use_priority_updated_at_then_name() -> None:
    matcher = SubAgentDefinitionMatcher()
    request = _request("customer worker")
    newer_low_priority = _definition(
        "newer-low-priority",
        priority=20,
        trigger_keywords=["AUM", "客户维护"],
    )
    older_high_priority = _definition(
        "older-high-priority",
        priority=10,
        trigger_keywords=["AUM", "客户维护"],
    ).model_copy(
        update={"updated_at": datetime(2025, 1, 1, tzinfo=timezone.utc)},
    )

    priority_result = matcher.match(
        request,
        [newer_low_priority, older_high_priority],
    )

    assert priority_result is not None
    assert priority_result.definition.name == "older-high-priority"

    older_by_name = _definition(
        "z-later-name",
        priority=10,
        trigger_keywords=["AUM", "客户维护"],
    ).model_copy(
        update={"updated_at": datetime(2025, 1, 1, tzinfo=timezone.utc)},
    )
    newer_by_time = _definition(
        "a-earlier-name",
        priority=10,
        trigger_keywords=["AUM", "客户维护"],
    )

    updated_result = matcher.match(request, [older_by_name, newer_by_time])

    assert updated_result is not None
    assert updated_result.definition.name == "a-earlier-name"

    b_name = _definition(
        "b-name",
        priority=10,
        trigger_keywords=["AUM", "客户维护"],
    )
    a_name = _definition(
        "a-name",
        priority=10,
        trigger_keywords=["AUM", "客户维护"],
    )

    name_result = matcher.match(request, [b_name, a_name])

    assert name_result is not None
    assert name_result.definition.name == "a-name"


def test_definition_service_matches_available_definitions(tmp_path) -> None:
    service = SubAgentDefinitionService(
        store=SubAgentDefinitionStore(tmp_path),
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    )
    service._store.upsert(
        _definition(
            "aum-customer-analyst",
            trigger_keywords=["AUM", "客户维护"],
        ),
    )

    result = service.match_start_request(_request("customer worker"))

    assert result is not None
    assert result.definition.name == "aum-customer-analyst"
