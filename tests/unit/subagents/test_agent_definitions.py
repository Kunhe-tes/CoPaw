# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
import tomllib
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from swe.app.subagents.agent_definitions import (
    AgentOwnedDefinitionConflict,
    AgentOwnedDefinitionRepository,
)


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "reviewer",
        "description": "Review a change set.",
        "instruction": "Review carefully and report concrete findings.",
        "trigger_keywords": ["review", "审查"],
        "extension": {"preserve": True},
    }
    payload.update(overrides)
    return payload


def test_create_writes_disabled_uuid_toml_with_agent_owned_source(
    tmp_path: Path,
) -> None:
    repository = AgentOwnedDefinitionRepository(
        tmp_path / "agents",
        owner_scope="tenant/default",
    )

    package = repository.create(_payload())

    UUID(package.definition_id)
    assert package.definition.source == "agent_owned"
    assert package.definition.enabled is False
    assert (tmp_path / "agents" / f"{package.definition_id}.toml").is_file()
    assert tomllib.loads(package.toml)["name"] == "reviewer"


def test_received_expert_round_trips_community_reference(
    tmp_path: Path,
) -> None:
    repository = AgentOwnedDefinitionRepository(
        tmp_path / "agents",
        owner_scope="tenant/default",
    )

    package = repository.create(
        _payload(
            enabled=True,
            community={
                "item_id": "community-1",
                "version": "1.2.3",
                "content_fingerprint": "sha256:abc",
            },
        ),
    )

    assert package.definition.agent_owned.community.item_id == "community-1"
    assert package.definition.agent_owned.community.version == "1.2.3"
    parsed = tomllib.loads(package.toml)
    assert parsed["community"]["content_fingerprint"] == "sha256:abc"


def test_update_preserves_unknown_toml_fields_and_requires_revision(
    tmp_path: Path,
) -> None:
    repository = AgentOwnedDefinitionRepository(
        tmp_path / "agents",
        owner_scope="tenant/default",
    )
    created = repository.create(_payload())

    updated = repository.update(
        created.definition_id,
        _payload(instruction="Report only actionable findings."),
        expected_revision=created.revision,
    )

    parsed = tomllib.loads(updated.toml)
    assert parsed["extension"] == {"preserve": True}
    with pytest.raises(AgentOwnedDefinitionConflict):
        repository.update(
            created.definition_id,
            _payload(),
            expected_revision=created.revision,
        )


def test_update_preserves_unknown_nested_fields_and_temporal_values(
    tmp_path: Path,
) -> None:
    repository = AgentOwnedDefinitionRepository(
        tmp_path / "agents",
        owner_scope="tenant/default",
    )
    created = repository.create(
        _payload(
            created_at=datetime(2026, 8, 15, 12, 30, 0),
            tools={"future_option": True},
            budget={"future_limit": 7},
        ),
    )

    updated = repository.update(
        created.definition_id,
        _payload(instruction="Report only actionable findings."),
        expected_revision=created.revision,
    )

    parsed = tomllib.loads(updated.toml)
    assert parsed["created_at"] == datetime(2026, 8, 15, 12, 30, 0)
    assert parsed["tools"]["future_option"] is True
    assert parsed["budget"]["future_limit"] == 7


def test_update_preserves_unknown_quoted_toml_keys(tmp_path: Path) -> None:
    repository = AgentOwnedDefinitionRepository(
        tmp_path / "agents",
        owner_scope="tenant/default",
    )
    created = repository.create(
        _payload(
            **{
                "future.option": True,
                "future field": "preserve me",
                "tools": {"future.option": True},
            },
        ),
    )

    updated = repository.update(
        created.definition_id,
        _payload(instruction="Report only actionable findings."),
        expected_revision=created.revision,
    )

    parsed = tomllib.loads(updated.toml)
    assert parsed["future.option"] is True
    assert parsed["future field"] == "preserve me"
    assert parsed["tools"]["future.option"] is True


def test_list_reports_invalid_package_without_hiding_valid_siblings(
    tmp_path: Path,
) -> None:
    root = tmp_path / "agents"
    repository = AgentOwnedDefinitionRepository(
        root,
        owner_scope="tenant/default",
    )
    valid = repository.create(_payload())
    malformed_id = str(uuid4())
    (root / f"{malformed_id}.toml").write_text("name = [", encoding="utf-8")

    packages = repository.list()

    assert {package.definition_id for package in packages} == {
        valid.definition_id,
        malformed_id,
    }
    invalid = next(package for package in packages if not package.valid)
    assert "invalid TOML" in invalid.validation_error


def test_list_reports_invalid_utf8_package_without_hiding_valid_siblings(
    tmp_path: Path,
) -> None:
    root = tmp_path / "agents"
    repository = AgentOwnedDefinitionRepository(
        root,
        owner_scope="tenant/default",
    )
    valid = repository.create(_payload())
    malformed_id = str(uuid4())
    (root / f"{malformed_id}.toml").write_bytes(b"\x80not utf8")

    packages = repository.list()

    assert {package.definition_id for package in packages} == {
        valid.definition_id,
        malformed_id,
    }
    invalid = next(package for package in packages if not package.valid)
    assert "invalid TOML" in invalid.validation_error


def test_list_distinguishes_invalid_definition_from_invalid_toml(
    tmp_path: Path,
) -> None:
    root = tmp_path / "agents"
    repository = AgentOwnedDefinitionRepository(
        root,
        owner_scope="tenant/default",
    )
    definition_id = str(uuid4())
    root.mkdir()
    (root / f"{definition_id}.toml").write_text(
        'name = "reviewer"\ndescription = "Review."\ninstruction = "Review."\n'
        "[budget]\nmax_turns = 0\n",
        encoding="utf-8",
    )

    package = repository.list()[0]

    assert package.valid is False
    assert package.validation_error.startswith("invalid definition:")


def test_list_skips_noncanonical_uuid_file_names(tmp_path: Path) -> None:
    root = tmp_path / "agents"
    repository = AgentOwnedDefinitionRepository(
        root,
        owner_scope="tenant/default",
    )
    noncanonical_id = str(uuid4()).upper()
    root.mkdir()
    (root / f"{noncanonical_id}.toml").write_text(
        'name = "reviewer"\ndescription = "Review."\ninstruction = "Review."\n',
        encoding="utf-8",
    )

    assert repository.list() == []
    with pytest.raises(ValueError):
        repository.get(noncanonical_id)


def test_enable_rejects_builtin_and_enabled_agent_owned_name_conflicts(
    tmp_path: Path,
) -> None:
    repository = AgentOwnedDefinitionRepository(
        tmp_path / "agents",
        owner_scope="tenant/default",
        builtin_names={"builtin-reviewer"},
    )
    builtin_conflict = repository.create(_payload(name="builtin-reviewer"))
    first = repository.create(_payload(name="reviewer"))
    second = repository.create(_payload(name="reviewer"))

    with pytest.raises(AgentOwnedDefinitionConflict):
        repository.enable(
            builtin_conflict.definition_id,
            expected_revision=builtin_conflict.revision,
        )
    repository.enable(first.definition_id, expected_revision=first.revision)
    with pytest.raises(AgentOwnedDefinitionConflict):
        repository.enable(
            second.definition_id,
            expected_revision=second.revision,
        )


def test_update_rejects_name_conflicts_when_definition_is_enabled(
    tmp_path: Path,
) -> None:
    repository = AgentOwnedDefinitionRepository(
        tmp_path / "agents",
        owner_scope="tenant/default",
        builtin_names={"builtin-reviewer"},
    )
    first = repository.create(_payload(name="first"))
    second = repository.create(_payload(name="second"))
    enabled = repository.enable(
        first.definition_id,
        expected_revision=first.revision,
    )
    repository.enable(second.definition_id, expected_revision=second.revision)

    with pytest.raises(AgentOwnedDefinitionConflict):
        repository.update(
            enabled.definition_id,
            _payload(name="builtin-reviewer"),
            expected_revision=enabled.revision,
        )
    with pytest.raises(AgentOwnedDefinitionConflict):
        repository.update(
            enabled.definition_id,
            _payload(name="second"),
            expected_revision=enabled.revision,
        )
