# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from swe.app.subagents.skill_definitions import (
    load_skill_owned_definitions,
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
    assert definition.source == "stored"
    assert definition.skill_owned is not None
    assert definition.skill_owned.local_name == "reviewer"
    assert definition.skill_owned.declared_skills == ["security"]
    assert definition.skill_owned.tools.inherit is True


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
