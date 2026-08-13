# -*- coding: utf-8 -*-
"""Stored SubAgent definition store and service tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swe.app.subagents import (
    AgentRegistry,
    build_definition_catalog,
    InMemoryDefinitionProvider,
    SubAgentDefinitionService,
    SubAgentDefinitionStore,
    SubAgentDefinition,
    SubAgentRegistrationRequest,
    SubAgentStartRequest,
    assign_subagent_nickname,
    builtin_definition_provider,
)


def _request(
    name: str = "aum-customer-analyst",
) -> SubAgentRegistrationRequest:
    return SubAgentRegistrationRequest.model_validate(
        {
            "name": name,
            "instruction": "Act as a customer strategy analyst.",
            "description": "Analyzes 1M AUM customer maintenance strategy.",
            "trigger_keywords": ["AUM", "客户维护"],
            "task_types": ["research", "analysis"],
            "priority": 20,
            "budget": {
                "max_turns": 4,
                "max_tool_calls": 20,
                "timeout_ms": 60000,
            },
        },
    )


def test_store_writes_one_json_file_per_definition(tmp_path: Path) -> None:
    store = SubAgentDefinitionStore(tmp_path)
    definition = SubAgentDefinitionService(
        store=store,
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    ).build_stored_definition(_request())

    result = store.upsert(definition)

    assert result.created is True
    [path] = list(tmp_path.glob("*.json"))
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["name"] == "aum-customer-analyst"
    assert saved["source"] == "stored"
    assert "nickname" not in saved or saved["nickname"] is None


def test_service_upsert_reports_registered_then_updated(
    tmp_path: Path,
) -> None:
    service = SubAgentDefinitionService(
        store=SubAgentDefinitionStore(tmp_path),
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    )

    first = service.register(_request())
    second = service.register(_request())

    assert first == {"status": "registered", "name": "aum-customer-analyst"}
    assert second == {"status": "updated", "name": "aum-customer-analyst"}


def test_service_rejects_builtin_name_conflict(tmp_path: Path) -> None:
    service = SubAgentDefinitionService(
        store=SubAgentDefinitionStore(tmp_path),
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    )

    result = service.register(_request("risk-reviewer"))

    assert result == {
        "status": "failed",
        "reason": "builtin_name_conflict",
        "name": "risk-reviewer",
    }


def test_store_lists_and_gets_definitions(tmp_path: Path) -> None:
    store = SubAgentDefinitionStore(tmp_path)
    service = SubAgentDefinitionService(
        store=store,
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    )
    definition = service.build_stored_definition(_request())

    store.upsert(definition)

    assert store.get("aum-customer-analyst") == definition
    assert store.list_definitions() == [definition]


def test_store_avoids_filename_collisions(tmp_path: Path) -> None:
    store = SubAgentDefinitionStore(tmp_path)
    service = SubAgentDefinitionService(
        store=store,
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    )
    slash_name = service.build_stored_definition(_request("a/b"))
    underscore_name = service.build_stored_definition(_request("a_b"))

    first = store.upsert(slash_name)
    second = store.upsert(underscore_name)

    assert first.created is True
    assert second.created is True
    assert store.get("a/b") == slash_name
    assert store.get("a_b") == underscore_name
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_store_bounds_long_safe_filenames(tmp_path: Path) -> None:
    store = SubAgentDefinitionStore(tmp_path)
    service = SubAgentDefinitionService(
        store=store,
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    )
    long_name = "a" * 300

    result = store.upsert(service.build_stored_definition(_request(long_name)))

    assert result.created is True
    [path] = list(tmp_path.glob("*.json"))
    assert len(path.name) < 128
    assert store.get(long_name) is not None


def test_store_avoids_case_only_filename_collisions(tmp_path: Path) -> None:
    store = SubAgentDefinitionStore(tmp_path)
    service = SubAgentDefinitionService(
        store=store,
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    )

    upper = store.upsert(service.build_stored_definition(_request("CaseName")))
    lower = store.upsert(service.build_stored_definition(_request("casename")))

    assert upper.created is True
    assert lower.created is True
    assert store.get("CaseName") is not None
    assert store.get("casename") is not None
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_service_builds_run_scoped_definition(tmp_path: Path) -> None:
    service = SubAgentDefinitionService(
        store=SubAgentDefinitionStore(tmp_path),
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    )
    request = SubAgentStartRequest.model_validate(
        {
            "name": "ad-hoc-analyst",
            "instruction": "Act as an analyst for this run.",
            "objective": "Analyze one customer scenario.",
        },
    )

    definition = service.build_run_scoped_definition(
        request,
        owner_scope="tenant-a/agent-b",
    )

    assert definition.name == "ad-hoc-analyst"
    assert definition.source == "run_scoped"
    assert definition.owner_scope == "tenant-a/agent-b"
    assert definition.instruction == "Act as an analyst for this run."


def test_service_requires_instruction_only_for_run_scoped_definition(
    tmp_path: Path,
) -> None:
    service = SubAgentDefinitionService(
        store=SubAgentDefinitionStore(tmp_path),
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    )
    request = SubAgentStartRequest.model_validate(
        {"name": "ad-hoc", "objective": "Inspect the patch."},
    )

    with pytest.raises(ValueError, match="instruction is required"):
        service.build_run_scoped_definition(request, owner_scope="tenant-a")


def test_service_resolves_exact_skill_owned_definition_without_instruction(
    tmp_path: Path,
) -> None:
    service = SubAgentDefinitionService(
        store=SubAgentDefinitionStore(tmp_path),
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    )
    skill_definition = SubAgentDefinition.model_validate(
        {
            "name": "security:reviewer",
            "source": "stored",
            "owner_scope": "skill:security",
            "description": "Review code.",
            "instruction": "Inspect evidence.",
            "skill_owned": {
                "skill_name": "security",
                "local_name": "reviewer",
            },
        },
    )
    catalog = build_definition_catalog(
        skill_definitions=[skill_definition],
        stored_definitions=[],
        builtin_definitions=builtin_definition_provider().list_definitions(),
    )
    request = SubAgentStartRequest.model_validate(
        {"name": "security:reviewer", "objective": "Review the patch."},
    )

    result = service.resolve_start_definition(request, catalog)

    assert result is not None
    assert result.definition == skill_definition
    assert result.metadata.reason == "exact_name"


def test_service_truncates_run_scoped_description_by_utf8_bytes(
    tmp_path: Path,
) -> None:
    service = SubAgentDefinitionService(
        store=SubAgentDefinitionStore(tmp_path),
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    )
    request = SubAgentStartRequest.model_validate(
        {
            "name": "ad-hoc-analyst",
            "instruction": "Act as an analyst for this run.",
            "objective": "分析" * 300,
        },
    )

    definition = service.build_run_scoped_definition(
        request,
        owner_scope="tenant-a/agent-b",
    )

    assert len(definition.description.encode("utf-8")) <= 1024
    assert definition.description


def test_start_request_limits_objective_and_background_size() -> None:
    base = {
        "name": "ad-hoc-analyst",
        "instruction": "Act as an analyst for this run.",
        "objective": "Inspect",
    }

    with pytest.raises(ValueError, match="objective exceeds 4096 bytes"):
        SubAgentStartRequest.model_validate(
            {**base, "objective": "x" * 4097},
        )
    with pytest.raises(ValueError, match="background exceeds 16384 bytes"):
        SubAgentStartRequest.model_validate(
            {**base, "background": "x" * 16385},
        )


def test_assign_subagent_nickname_prefers_configured_value() -> None:
    assert assign_subagent_nickname("  研究伙伴  ") == "研究伙伴"


def test_service_rejects_disabled_builtin_name_conflict(
    tmp_path: Path,
) -> None:
    builtin = builtin_definition_provider().list_definitions()[0]
    disabled_builtin = builtin.model_copy(update={"enabled": False})
    service = SubAgentDefinitionService(
        store=SubAgentDefinitionStore(tmp_path),
        builtin_registry=AgentRegistry(
            [InMemoryDefinitionProvider([disabled_builtin])],
        ),
    )

    result = service.register(_request(disabled_builtin.name))

    assert result == {
        "status": "failed",
        "reason": "builtin_name_conflict",
        "name": disabled_builtin.name,
    }


def test_registration_budget_can_only_narrow_defaults(
    tmp_path: Path,
) -> None:
    service = SubAgentDefinitionService(
        store=SubAgentDefinitionStore(tmp_path),
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    )

    with pytest.raises(ValueError, match="max_turns"):
        service.build_stored_definition(
            SubAgentRegistrationRequest.model_validate(
                {
                    "name": "too-large",
                    "instruction": "Act as an analyst.",
                    "description": "Too large budget.",
                    "budget": {"max_turns": 51},
                },
            ),
        )


@pytest.mark.parametrize(
    ("budget", "field_name"),
    [
        ({"max_turns": 0}, "max_turns"),
        ({"max_tool_calls": -1}, "max_tool_calls"),
        ({"timeout_ms": 999}, "timeout_ms"),
    ],
)
def test_registration_budget_rejects_values_below_minimums(
    tmp_path: Path,
    budget: dict[str, int],
    field_name: str,
) -> None:
    service = SubAgentDefinitionService(
        store=SubAgentDefinitionStore(tmp_path),
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    )

    with pytest.raises(ValueError, match=field_name):
        service.build_stored_definition(
            SubAgentRegistrationRequest.model_validate(
                {
                    "name": f"too-small-{field_name}",
                    "instruction": "Act as an analyst.",
                    "description": "Too small budget.",
                    "budget": budget,
                },
            ),
        )
