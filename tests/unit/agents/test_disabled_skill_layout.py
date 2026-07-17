# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

import pytest

from swe.agents import skills_manager
from swe.agents.skills_manager import (
    _default_workspace_manifest,
    get_legacy_workspace_skill_manifest_path,
    get_workspace_disabled_skills_dir,
    get_workspace_skill_manifest_path,
    get_workspace_skill_state_dir,
    get_workspace_skills_dir,
    reconcile_workspace_manifest,
    resolve_effective_skills,
    resolve_workspace_managed_skill_dir,
)
from swe.utils.fs_text import SanitizedFsText


def _write_skill(path: Path, marker: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill\n---\n" + f"\n{marker}\n",
        encoding="utf-8",
    )


def _write_manifest(
    workspace: Path,
    skills: dict[str, dict[str, object]],
) -> None:
    manifest_path = get_workspace_skill_manifest_path(workspace)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-skill-manifest.v1",
                "layout_version": 2,
                "version": 0,
                "skills": skills,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _entry(enabled: bool) -> dict[str, object]:
    return {
        "enabled": enabled,
        "channels": ["all"],
        "source": "customized",
        "config": {},
        "metadata": {},
    }


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
    assert get_legacy_workspace_skill_manifest_path(workspace_dir) == (
        workspace_dir / "skill.json"
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


def test_reconcile_moves_registered_disabled_skill_out_of_runtime_root(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    active = workspace / "skills" / "demo"
    disabled = workspace / ".disabled_skills" / "demo"
    _write_skill(active, "active-copy")
    _write_manifest(workspace, {"demo": _entry(enabled=False)})

    state = reconcile_workspace_manifest(workspace)

    assert not active.exists()
    assert disabled.exists()
    assert resolve_effective_skills(workspace, "console") == []
    assert state["skills"]["demo"]["enabled"] is False


def test_reconcile_moves_registered_enabled_skill_into_runtime_root(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    active = workspace / "skills" / "demo"
    disabled = workspace / ".disabled_skills" / "demo"
    _write_skill(disabled, "disabled-copy")
    _write_manifest(workspace, {"demo": _entry(enabled=True)})

    reconcile_workspace_manifest(workspace)

    assert active.exists()
    assert not disabled.exists()
    assert resolve_effective_skills(workspace, "console") == ["demo"]


def test_reconcile_prefers_runtime_copy_when_both_registered_copies_exist(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    active = workspace / "skills" / "demo"
    disabled = workspace / ".disabled_skills" / "demo"
    _write_skill(active, "runtime-wins")
    _write_skill(disabled, "discard-me")
    _write_manifest(workspace, {"demo": _entry(enabled=False)})

    reconcile_workspace_manifest(workspace)

    assert not active.exists()
    assert "runtime-wins" in (disabled / "SKILL.md").read_text(
        encoding="utf-8",
    )
    assert "discard-me" not in (disabled / "SKILL.md").read_text(
        encoding="utf-8",
    )


def test_reconcile_ignores_unmanaged_runtime_content(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    manual = workspace / "skills" / "new-skill"
    _write_skill(manual, "manual-copy")
    _write_manifest(workspace, {})

    state = reconcile_workspace_manifest(workspace)

    assert state["skills"] == {}
    assert manual.exists()


def test_reconcile_removes_registered_entry_when_both_copies_are_missing(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    _write_manifest(workspace, {"demo": _entry(enabled=True)})

    state = reconcile_workspace_manifest(workspace)

    assert state["skills"] == {}


def test_effective_skill_resolution_fails_closed_when_move_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    active = workspace / "skills" / "demo"
    disabled = workspace / ".disabled_skills" / "demo"
    _write_skill(disabled, "disabled-copy")
    _write_manifest(workspace, {"demo": _entry(enabled=True)})

    def fail_move(_source: Path, _target: Path) -> None:
        raise OSError("cannot move registered skill")

    monkeypatch.setattr(
        "swe.agents.skills_manager._move_skill_dir",
        fail_move,
    )

    with pytest.raises(OSError, match="cannot move registered skill"):
        resolve_effective_skills(workspace, "console")
    assert not active.exists()


def test_reconcile_rolls_back_sanitized_rename_when_manifest_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    original_dir = workspace / "skills" / "bad-skill"
    sanitized_dir = workspace / "skills" / "safe-skill"
    _write_skill(original_dir, "registered-copy")
    _write_manifest(workspace, {"bad-skill": _entry(enabled=True)})
    manifest_path = get_workspace_skill_manifest_path(workspace)

    original_sanitize = skills_manager.sanitize_fs_text

    def sanitize_bad_skill(text: str) -> SanitizedFsText:
        if text == "bad-skill":
            return SanitizedFsText(
                value="safe-skill",
                changed=True,
                strategy="replace",
            )
        return original_sanitize(text)

    def fail_manifest_write(_path: Path, _payload: dict) -> None:
        raise OSError("manifest write failed")

    monkeypatch.setattr(
        skills_manager,
        "sanitize_fs_text",
        sanitize_bad_skill,
    )
    monkeypatch.setattr(
        skills_manager,
        "_write_json_atomic",
        fail_manifest_write,
    )

    with pytest.raises(OSError, match="manifest write failed"):
        reconcile_workspace_manifest(workspace)

    assert original_dir.exists()
    assert not sanitized_dir.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "bad-skill" in manifest["skills"]
    assert "safe-skill" not in manifest["skills"]


def test_reconcile_preserves_publication_and_rollback_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    original_dir = workspace / "skills" / "bad-skill"
    sanitized_dir = workspace / "skills" / "safe-skill"
    _write_skill(original_dir, "registered-copy")
    _write_manifest(workspace, {"bad-skill": _entry(enabled=True)})

    original_sanitize = skills_manager.sanitize_fs_text
    original_move = skills_manager._move_skill_dir
    publication_error = OSError("manifest write failed")
    rollback_error = OSError("rollback failed")

    def sanitize_bad_skill(text: str) -> SanitizedFsText:
        if text == "bad-skill":
            return SanitizedFsText(
                value="safe-skill",
                changed=True,
                strategy="replace",
            )
        return original_sanitize(text)

    def fail_manifest_write(_path: Path, _payload: dict) -> None:
        raise publication_error

    def fail_rollback(source: Path, target: Path) -> None:
        if source == sanitized_dir and target == original_dir:
            raise rollback_error
        original_move(source, target)

    monkeypatch.setattr(
        skills_manager,
        "sanitize_fs_text",
        sanitize_bad_skill,
    )
    monkeypatch.setattr(
        skills_manager,
        "_write_json_atomic",
        fail_manifest_write,
    )
    monkeypatch.setattr(
        skills_manager,
        "_move_skill_dir",
        fail_rollback,
    )

    with pytest.raises(RuntimeError) as exc_info:
        reconcile_workspace_manifest(workspace)

    error = exc_info.value
    assert isinstance(
        error,
        skills_manager.WorkspaceManifestReconciliationError,
    )
    assert error.reconciliation_error is publication_error
    assert error.rollback_errors == (rollback_error,)
    assert error.__cause__ is publication_error


def test_reconcile_rejects_malformed_workspace_manifest_without_mutation(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    active = workspace / "skills" / "demo"
    disabled = workspace / ".disabled_skills" / "demo"
    _write_skill(active, "active-copy")
    _write_skill(disabled, "disabled-copy")
    manifest_path = get_workspace_skill_manifest_path(workspace)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    malformed = "{not valid json"
    manifest_path.write_text(malformed, encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        reconcile_workspace_manifest(workspace)

    assert manifest_path.read_text(encoding="utf-8") == malformed
    assert active.exists()
    assert disabled.exists()
