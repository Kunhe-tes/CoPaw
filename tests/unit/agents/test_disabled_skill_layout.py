# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from swe.agents.skills_manager import (
    _default_workspace_manifest,
    get_workspace_disabled_skills_dir,
    get_workspace_skill_manifest_path,
    get_workspace_skill_state_dir,
    get_workspace_skills_dir,
    resolve_workspace_managed_skill_dir,
)


def test_workspace_skill_layout_paths(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"

    assert get_workspace_skills_dir(workspace_dir) == workspace_dir / "skills"
    assert get_workspace_disabled_skills_dir(workspace_dir) == (
        workspace_dir / ".disabled_skills"
    )
    assert get_workspace_skill_state_dir(workspace_dir) == (
        workspace_dir / ".skill_state"
    )
    assert get_workspace_skill_manifest_path(workspace_dir) == (
        workspace_dir / ".skill_state" / "manifest.json"
    )


def test_default_workspace_manifest_declares_layout_v2() -> None:
    manifest = _default_workspace_manifest()

    assert manifest["layout_version"] == 2
    assert manifest["schema_version"] == "workspace-skill-manifest.v1"
    assert manifest["version"] == 0


def test_managed_skill_dir_follows_manifest_enablement(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"

    assert (
        resolve_workspace_managed_skill_dir(
            workspace_dir,
            "docx",
            enabled=True,
        )
        == workspace_dir / "skills" / "docx"
    )
    assert (
        resolve_workspace_managed_skill_dir(
            workspace_dir,
            "docx",
            enabled=False,
        )
        == workspace_dir / ".disabled_skills" / "docx"
    )
