# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pytest

from swe.app.subagents.skill_definitions import (
    build_definition_catalog,
    load_skill_owned_definitions,
)
from swe.app.subagents.models import (
    DefinitionValidationError,
    SkillOwnedDefinitionMetadata,
    SubAgentDefinition,
)


def _definition(
    name: str,
    *,
    source: str = "stored",
    skill_name: str | None = None,
) -> SubAgentDefinition:
    metadata = None
    if skill_name is not None:
        metadata = SkillOwnedDefinitionMetadata(
            skill_name=skill_name,
            local_name=name.removeprefix(f"{skill_name}:"),
        )
    return SubAgentDefinition.model_validate(
        {
            "name": name,
            "source": source,
            "owner_scope": f"skill:{skill_name}" if skill_name else source,
            "description": "Review code.",
            "instruction": "Inspect evidence.",
            "skill_owned": metadata,
        },
    )


def _write_skill_definition(
    workspace_dir: Path,
    skill_name: str,
    filename: str,
    contents: str,
) -> None:
    definition_path = (
        workspace_dir / "skills" / skill_name / "agents" / f"{filename}.toml"
    )
    definition_path.parent.mkdir(parents=True, exist_ok=True)
    definition_path.write_text(contents, encoding="utf-8")


def test_load_skill_definition_qualifies_local_name(tmp_path: Path) -> None:
    _write_skill_definition(
        tmp_path,
        "security",
        "reviewer",
        """
name = "reviewer"
description = "Review code and identify security regressions."
instruction = "Inspect the change and cite evidence."
trigger_keywords = ["review", "security"]
skills = ["security"]
mcps = ["github"]

[tools]
allow = ["read_file", "write_file", "edit_file"]
deny = ["execute_shell_command"]

[model]
provider = "openai"
id = "gpt-5-mini"

[budget]
max_turns = 20
max_tool_calls = 10
timeout_ms = 120000
""",
    )

    loaded = load_skill_owned_definitions(
        workspace_dir=tmp_path,
        effective_skill_names=["security"],
    )

    assert loaded.errors == []
    definition = loaded.definitions[0]
    assert definition.name == "security:reviewer"
    assert definition.source == "skill_owned"
    assert definition.skill_owned is not None
    assert definition.skill_owned.local_name == "reviewer"
    assert definition.skill_owned.declared_skills == ["security"]
    assert definition.skill_owned.tools.inherit is True


def test_skill_definition_preserves_missing_vs_empty_mcps(tmp_path: Path) -> None:
    _write_skill_definition(
        tmp_path,
        "quality",
        "inherits-mcp",
        """
name = "inherits-mcp"
description = "Inherit MCP."
instruction = "Inspect evidence."
""",
    )
    _write_skill_definition(
        tmp_path,
        "quality",
        "blocks-mcp",
        """
name = "blocks-mcp"
description = "Block MCP."
instruction = "Inspect evidence."
mcps = []
""",
    )

    loaded = load_skill_owned_definitions(
        workspace_dir=tmp_path,
        effective_skill_names=["quality"],
    )

    definitions = {definition.name: definition for definition in loaded.definitions}
    assert definitions["quality:inherits-mcp"].skill_owned.declared_mcps is None
    assert definitions["quality:blocks-mcp"].skill_owned.declared_mcps == []


def test_invalid_package_does_not_hide_valid_sibling(tmp_path: Path) -> None:
    _write_skill_definition(
        tmp_path,
        "security",
        "valid",
        """
name = "valid"
description = "A valid definition."
instruction = "Inspect evidence."
""",
    )
    _write_skill_definition(
        tmp_path,
        "security",
        "invalid",
        """
name = "invalid"
description = "An invalid definition."
instruction = "Inspect evidence."
unknown = "field"
""",
    )

    loaded = load_skill_owned_definitions(
        workspace_dir=tmp_path,
        effective_skill_names=["security"],
    )

    assert [definition.name for definition in loaded.definitions] == [
        "security:valid",
    ]
    assert len(loaded.errors) == 1
    assert loaded.errors[0].path.name == "invalid.toml"
    assert "unknown field" in loaded.errors[0].message


def test_invalid_packages_are_reported_independently(tmp_path: Path) -> None:
    _write_skill_definition(
        tmp_path,
        "security",
        "bad-tool",
        """
name = "bad-tool"
description = "Invalid tool."
instruction = "Inspect evidence."

[tools]
allow = ["not_a_builtin_tool"]
""",
    )
    _write_skill_definition(
        tmp_path,
        "security",
        "blank-instruction",
        """
name = "blank-instruction"
description = "Blank instruction."
instruction = "  "
""",
    )
    _write_skill_definition(
        tmp_path,
        "security",
        "bad-model",
        """
name = "bad-model"
description = "Incomplete model."
instruction = "Inspect evidence."

[model]
provider = "openai"
""",
    )

    loaded = load_skill_owned_definitions(
        workspace_dir=tmp_path,
        effective_skill_names=["security"],
    )

    assert loaded.definitions == []
    assert {error.path.name for error in loaded.errors} == {
        "bad-tool.toml",
        "bad-model.toml",
        "blank-instruction.toml",
    }


def test_duplicate_local_name_is_invalid(tmp_path: Path) -> None:
    _write_skill_definition(
        tmp_path,
        "security",
        "first",
        """
name = "reviewer"
description = "First definition."
instruction = "Inspect evidence."
""",
    )
    _write_skill_definition(
        tmp_path,
        "security",
        "second",
        """
name = "reviewer"
description = "Second definition."
instruction = "Inspect evidence."
""",
    )

    loaded = load_skill_owned_definitions(
        workspace_dir=tmp_path,
        effective_skill_names=["security"],
    )

    assert [definition.name for definition in loaded.definitions] == [
        "security:reviewer",
    ]
    assert len(loaded.errors) == 1
    assert "duplicate local name" in loaded.errors[0].message


def test_duplicate_declared_dependencies_only_skip_bad_definition(
    tmp_path: Path,
) -> None:
    _write_skill_definition(
        tmp_path,
        "security",
        "bad-dependencies",
        """
name = "bad-dependencies"
description = "Invalid duplicate dependencies."
instruction = "Inspect evidence."
skills = ["security", "security"]
""",
    )

    loaded = load_skill_owned_definitions(
        workspace_dir=tmp_path,
        effective_skill_names=["security"],
    )

    assert loaded.definitions == []
    assert "skills cannot contain duplicates" in loaded.errors[0].message


def test_same_local_name_in_different_skills_is_valid(tmp_path: Path) -> None:
    for skill_name in ("security", "quality"):
        _write_skill_definition(
            tmp_path,
            skill_name,
            "reviewer",
            """
name = "reviewer"
description = "Review a change."
instruction = "Inspect evidence."
""",
        )

    loaded = load_skill_owned_definitions(
        workspace_dir=tmp_path,
        effective_skill_names=["security", "quality"],
    )

    assert [definition.name for definition in loaded.definitions] == [
        "security:reviewer",
        "quality:reviewer",
    ]
    assert loaded.errors == []


def test_loader_uses_resolved_effective_skill_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builtin_skill = tmp_path / "packaged" / "security"
    definition_dir = builtin_skill / "agents"
    definition_dir.mkdir(parents=True)
    (definition_dir / "reviewer.toml").write_text(
        'name = "reviewer"\n'
        'description = "Review code."\n'
        'instruction = "Inspect evidence."\n',
        encoding="utf-8",
    )

    import swe.app.subagents.skill_definitions as loader

    monkeypatch.setattr(
        loader,
        "resolve_effective_skill_dir",
        lambda _workspace, name: builtin_skill if name == "security" else None,
    )

    loaded = loader.load_skill_owned_definitions(
        workspace_dir=tmp_path / "workspace",
        effective_skill_names=["security"],
    )

    assert [definition.name for definition in loaded.definitions] == [
        "security:reviewer",
    ]
    assert loaded.errors == []


def test_loader_skips_symlinked_definition_file(tmp_path: Path) -> None:
    _write_skill_definition(
        tmp_path,
        "security",
        "valid",
        'name = "valid"\n'
        'description = "Valid."\n'
        'instruction = "Inspect evidence."\n',
    )
    outside = tmp_path / "outside.toml"
    outside.write_text(
        'name = "outside"\n'
        'description = "Outside."\n'
        'instruction = "Should not load."\n',
        encoding="utf-8",
    )
    link = tmp_path / "skills" / "security" / "agents" / "linked.toml"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")

    loaded = load_skill_owned_definitions(
        workspace_dir=tmp_path,
        effective_skill_names=["security"],
    )

    assert [definition.name for definition in loaded.definitions] == [
        "security:valid",
    ]
    assert loaded.errors == []


def test_catalog_resolves_skill_owned_name_exactly_before_legacy_matching() -> (
    None
):
    catalog = build_definition_catalog(
        skill_definitions=[
            _definition("security:reviewer", skill_name="security"),
        ],
        stored_definitions=[_definition("reviewer")],
        builtin_definitions=[_definition("risk-reviewer", source="builtin")],
    )

    assert (
        catalog.resolve_exact("security:reviewer").name == "security:reviewer"
    )
    assert catalog.resolve_exact("reviewer").name == "reviewer"
    assert catalog.resolve_exact("security:missing") is None


def test_catalog_rejects_stored_claim_of_skill_qualified_name() -> None:
    with pytest.raises(DefinitionValidationError, match="reserved"):
        build_definition_catalog(
            skill_definitions=[
                _definition("security:reviewer", skill_name="security"),
            ],
            stored_definitions=[_definition("security:reviewer")],
            builtin_definitions=[],
        )


def test_catalog_rejects_custom_claim_of_builtin_name() -> None:
    with pytest.raises(DefinitionValidationError, match="builtin"):
        build_definition_catalog(
            skill_definitions=[],
            stored_definitions=[_definition("risk-reviewer")],
            builtin_definitions=[
                _definition("risk-reviewer", source="builtin"),
            ],
        )
