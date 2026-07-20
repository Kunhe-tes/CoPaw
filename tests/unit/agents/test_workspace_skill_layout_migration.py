# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

import pytest

from swe.agents import workspace_skill_layout_migration as migration
from swe.agents.workspace_skill_layout_migration import (
    SkillLayoutMigrationError,
    apply_workspace_skill_layout_migration,
    check_workspace_skill_layout_migration,
)


def _write_skill(path: Path, marker: str = "demo") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {path.name}\n---\n{marker}\n",
        encoding="utf-8",
    )


def _legacy_workspace(
    root: Path,
    tenant: str,
    *,
    workspace_name: str = "default",
    skills: dict[str, dict[str, Any]] | None = None,
) -> Path:
    workspace = root / tenant / "workspaces" / workspace_name
    entries = skills or {
        "demo": {
            "enabled": False,
            "channels": ["console"],
            "config": {"token": "kept"},
            "custom_entry_field": {"kept": True},
        },
    }
    for skill_name in entries:
        _write_skill(workspace / "skills" / skill_name)
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "skill.json").write_text(
        json.dumps(
            {
                "schema_version": "workspace-skill-manifest.v1",
                "version": 7,
                "custom_manifest_field": ["kept"],
                "skills": entries,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return workspace


def _write_v2_manifest(
    workspace: Path,
    skills: dict[str, dict[str, Any]],
    *,
    layout_version: object = 2,
) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "skill.json").write_text(
        json.dumps(
            {
                "schema_version": "workspace-skill-manifest.v1",
                "layout_version": layout_version,
                "version": 8,
                "skills": skills,
            },
        ),
        encoding="utf-8",
    )


def _write_obsolete_v2_manifest(
    workspace: Path,
    skills: dict[str, dict[str, Any]],
) -> None:
    state = workspace / ".skill_state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "workspace-skill-manifest.v1",
                "layout_version": 2,
                "version": 8,
                "skills": skills,
            },
        ),
        encoding="utf-8",
    )


def _snapshot_paths(workspace: Path) -> dict[str, tuple[str, bytes | None]]:
    snapshot: dict[str, tuple[str, bytes | None]] = {}
    for relative in (
        "skill.json",
        "skills",
        ".disabled_skills",
        ".skill_state",
    ):
        path = workspace / relative
        if not path.exists():
            snapshot[relative] = ("absent", None)
            continue
        if path.is_file():
            snapshot[relative] = ("file", path.read_bytes())
            continue
        snapshot[relative] = ("directory", None)
        for child in sorted(path.rglob("*")):
            child_relative = child.relative_to(workspace).as_posix()
            snapshot[child_relative] = (
                "directory" if child.is_dir() else "file",
                None if child.is_dir() else child.read_bytes(),
            )
    return snapshot


def _remove_directory_permissions(path: Path, permissions: int) -> int:
    original_mode = stat.S_IMODE(path.stat().st_mode)
    path.chmod(original_mode & ~permissions)
    return original_mode


def test_check_builds_complete_read_only_plan(tmp_path: Path) -> None:
    first = _legacy_workspace(tmp_path, "tenant-b")
    second = _legacy_workspace(
        tmp_path,
        "tenant-a",
        workspace_name="secondary",
    )
    before = {path: _snapshot_paths(path) for path in (first, second)}

    report = check_workspace_skill_layout_migration(tmp_path)

    assert report.success is True
    assert [(item.workspace, item.status) for item in report.workspaces] == [
        (second, "ready"),
        (first, "ready"),
    ]
    assert {path: _snapshot_paths(path) for path in (first, second)} == before


def test_check_does_not_rename_legacy_singular_skill_directory(
    tmp_path: Path,
) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")
    singular_root = workspace / "skill"
    (workspace / "skills").rename(singular_root)

    with pytest.raises(SkillLayoutMigrationError, match="missing registered"):
        check_workspace_skill_layout_migration(tmp_path)

    assert (singular_root / "demo" / "SKILL.md").exists()
    assert not (workspace / "skills").exists()


def test_check_preflights_every_workspace_before_raising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspaces = [
        tmp_path / "tenant-a" / "workspaces" / "default",
        tmp_path / "tenant-b" / "workspaces" / "default",
    ]
    for workspace in workspaces:
        workspace.mkdir(parents=True)
    checked: list[Path] = []

    def record_preflight(workspace: Path) -> migration._WorkspaceMigrationPlan:
        checked.append(workspace)
        if workspace == workspaces[0]:
            raise SkillLayoutMigrationError("first invalid")
        return migration._WorkspaceMigrationPlan(workspace, "not_applicable")

    monkeypatch.setattr(migration, "_preflight_workspace", record_preflight)

    with pytest.raises(SkillLayoutMigrationError, match="first invalid"):
        check_workspace_skill_layout_migration(tmp_path)

    assert checked == workspaces


def test_missing_release_root_returns_empty_success_report(
    tmp_path: Path,
) -> None:
    report = check_workspace_skill_layout_migration(tmp_path / "missing")

    assert report.success is True
    assert report.workspaces == ()


def test_discovery_rejects_dangling_symlink_release_root(
    tmp_path: Path,
) -> None:
    release_root = tmp_path / "release"
    release_root.symlink_to(tmp_path / "missing", target_is_directory=True)

    with pytest.raises(SkillLayoutMigrationError, match="symbolic link"):
        check_workspace_skill_layout_migration(release_root)


@pytest.mark.parametrize(
    "symlink_level",
    ["tenant", "workspaces", "workspace"],
)
def test_discovery_rejects_symlinked_workspace_hierarchy(
    tmp_path: Path,
    symlink_level: str,
) -> None:
    release_root = tmp_path / "release"
    outside = tmp_path / "outside"
    outside_workspace = outside / "tenant" / "workspaces" / "default"
    outside_workspace.mkdir(parents=True)
    release_root.mkdir()

    if symlink_level == "tenant":
        (release_root / "tenant").symlink_to(
            outside / "tenant",
            target_is_directory=True,
        )
    else:
        tenant = release_root / "tenant"
        tenant.mkdir()
        if symlink_level == "workspaces":
            (tenant / "workspaces").symlink_to(
                outside / "tenant" / "workspaces",
                target_is_directory=True,
            )
        else:
            workspaces = tenant / "workspaces"
            workspaces.mkdir()
            (workspaces / "default").symlink_to(
                outside_workspace,
                target_is_directory=True,
            )

    with pytest.raises(SkillLayoutMigrationError, match="symbolic link"):
        check_workspace_skill_layout_migration(release_root)

    assert outside_workspace.exists()


@pytest.mark.parametrize(
    "symlink_path",
    [
        "skills",
        ".disabled_skills",
        ".skill_state",
        "skill.json",
        "skills/demo",
        "skills/demo/SKILL.md",
    ],
)
def test_preflight_rejects_symlinked_legacy_layout_paths(
    tmp_path: Path,
    symlink_path: str,
) -> None:
    release_root = tmp_path / "release"
    workspace = _legacy_workspace(release_root, "tenant-a")
    path = workspace / symlink_path
    outside = tmp_path / "outside" / symlink_path.replace("/", "-")
    outside.parent.mkdir(parents=True, exist_ok=True)

    if path.is_dir():
        path.rename(outside)
        path.symlink_to(outside, target_is_directory=True)
    elif path.exists():
        path.rename(outside)
        path.symlink_to(outside)
    else:
        outside.mkdir()
        path.symlink_to(outside, target_is_directory=True)

    with pytest.raises(SkillLayoutMigrationError, match="symbolic link"):
        check_workspace_skill_layout_migration(release_root)

    assert path.is_symlink()
    assert outside.exists()


def test_preflight_rejects_symlinked_v2_manifest(tmp_path: Path) -> None:
    release_root = tmp_path / "release"
    workspace = release_root / "tenant-a" / "workspaces" / "default"
    _write_skill(workspace / "skills" / "demo")
    _write_obsolete_v2_manifest(workspace, {"demo": {"enabled": True}})
    manifest = workspace / ".skill_state" / "manifest.json"
    outside = tmp_path / "outside" / "manifest.json"
    outside.parent.mkdir(parents=True)
    manifest.rename(outside)
    manifest.symlink_to(outside)

    with pytest.raises(SkillLayoutMigrationError, match="symbolic link"):
        check_workspace_skill_layout_migration(release_root)

    assert manifest.is_symlink()
    assert outside.exists()


@pytest.mark.parametrize(
    ("root_name", "skills"),
    [
        ("skills", {}),
        (".disabled_skills", {"demo": {"enabled": True}}),
        (".skill_state", {}),
    ],
)
def test_preflight_rejects_file_shaped_managed_roots(
    tmp_path: Path,
    root_name: str,
    skills: dict[str, dict[str, Any]],
) -> None:
    workspace = tmp_path / "tenant-a" / "workspaces" / "default"
    if skills:
        _write_skill(workspace / "skills" / "demo")
    _write_v2_manifest(workspace, skills)
    (workspace / root_name).write_text("not a directory", encoding="utf-8")

    with pytest.raises(SkillLayoutMigrationError, match="must be a directory"):
        check_workspace_skill_layout_migration(tmp_path)


def test_empty_and_unrelated_workspaces_are_not_applicable(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "tenant-a" / "workspaces" / "empty"
    unrelated = tmp_path / "tenant-a" / "workspaces" / "unrelated"
    empty.mkdir(parents=True)
    _write_skill(unrelated / "skills" / "unregistered")

    report = check_workspace_skill_layout_migration(tmp_path)

    assert [(item.workspace, item.status) for item in report.workspaces] == [
        (empty, "not_applicable"),
        (unrelated, "not_applicable"),
    ]


def test_normal_skill_state_directory_is_untouched_and_not_applicable(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "tenant-a" / "workspaces" / "default"
    state_file = workspace / ".skill_state" / "notes.txt"
    state_file.parent.mkdir(parents=True)
    state_file.write_text("keep me", encoding="utf-8")

    report = apply_workspace_skill_layout_migration(tmp_path)

    assert report.workspaces[0].status == "not_applicable"
    assert state_file.read_text(encoding="utf-8") == "keep me"


def test_apply_moves_disabled_and_preserves_manifest_payload(
    tmp_path: Path,
) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")

    report = apply_workspace_skill_layout_migration(tmp_path)

    assert report.workspaces[0].status == "migrated"
    manifest = json.loads(
        (workspace / "skill.json").read_text(encoding="utf-8"),
    )
    assert manifest["layout_version"] == 2
    assert manifest["version"] == 7
    assert manifest["custom_manifest_field"] == ["kept"]
    assert manifest["skills"]["demo"]["channels"] == ["console"]
    assert manifest["skills"]["demo"]["config"] == {"token": "kept"}
    assert manifest["skills"]["demo"]["custom_entry_field"] == {
        "kept": True,
    }
    assert (workspace / ".disabled_skills" / "demo" / "SKILL.md").exists()
    assert not (workspace / "skills" / "demo").exists()
    assert not (workspace / ".skill_state").exists()


def test_apply_preserves_manifest_mode_owner_and_group(tmp_path: Path) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")
    manifest_path = workspace / "skill.json"
    manifest_path.chmod(0o664)
    before = manifest_path.stat()

    apply_workspace_skill_layout_migration(tmp_path)

    after = manifest_path.stat()
    assert stat.S_IMODE(after.st_mode) == stat.S_IMODE(before.st_mode)
    assert after.st_uid == before.st_uid
    assert after.st_gid == before.st_gid


def test_apply_keeps_enabled_packages_active(tmp_path: Path) -> None:
    workspace = _legacy_workspace(
        tmp_path,
        "tenant-a",
        skills={"demo": {"enabled": True, "channels": ["all"]}},
    )

    apply_workspace_skill_layout_migration(tmp_path)

    assert (workspace / "skills" / "demo" / "SKILL.md").exists()
    assert not (workspace / ".disabled_skills" / "demo").exists()


def test_ready_workspace_preserves_and_does_not_back_up_skill_state_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")
    state_file = workspace / ".skill_state" / "notes.txt"
    state_file.parent.mkdir(parents=True)
    state_file.write_text("keep me", encoding="utf-8")
    copied_sources: list[Path] = []
    original_copy = migration._copy_backup_path

    def record_copy(source: Path, target: Path) -> None:
        copied_sources.append(source)
        original_copy(source, target)

    monkeypatch.setattr(migration, "_copy_backup_path", record_copy)

    report = apply_workspace_skill_layout_migration(tmp_path)

    assert report.workspaces[0].status == "migrated"
    assert state_file.read_text(encoding="utf-8") == "keep me"
    assert not (workspace / ".skill_state" / "manifest.json").exists()
    assert workspace / ".skill_state" not in copied_sources


def test_apply_is_idempotent(tmp_path: Path) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")
    manifest_path = workspace / "skill.json"
    manifest_path.chmod(0o664)
    first = apply_workspace_skill_layout_migration(tmp_path)
    before_second_layout = _snapshot_paths(workspace)
    before_second_bytes = manifest_path.read_bytes()
    before_second_mode = stat.S_IMODE(manifest_path.stat().st_mode)

    second = apply_workspace_skill_layout_migration(tmp_path)

    assert first.workspaces[0].status == "migrated"
    assert second.workspaces[0].status == "already_migrated"
    assert second.workspaces[0].workspace == workspace
    assert _snapshot_paths(workspace) == before_second_layout
    assert manifest_path.read_bytes() == before_second_bytes
    assert stat.S_IMODE(manifest_path.stat().st_mode) == before_second_mode


def test_check_rejects_obsolete_manifest_before_writing_any_workspace(
    tmp_path: Path,
) -> None:
    valid = _legacy_workspace(tmp_path, "tenant-a")
    mixed = _legacy_workspace(tmp_path, "tenant-b")
    _write_obsolete_v2_manifest(mixed, {"demo": {"enabled": True}})
    before = _snapshot_paths(valid)

    with pytest.raises(SkillLayoutMigrationError, match="mixed layout"):
        check_workspace_skill_layout_migration(tmp_path)

    assert _snapshot_paths(valid) == before


def test_check_rejects_obsolete_manifest_without_root_manifest(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "tenant-a" / "workspaces" / "default"
    _write_skill(workspace / ".disabled_skills" / "demo")
    _write_obsolete_v2_manifest(workspace, {"demo": {"enabled": False}})

    with pytest.raises(SkillLayoutMigrationError, match="mixed layout"):
        check_workspace_skill_layout_migration(tmp_path)


def test_missing_layout_version_is_treated_as_legacy(tmp_path: Path) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")

    report = check_workspace_skill_layout_migration(tmp_path)

    assert report.workspaces[0].workspace == workspace
    assert report.workspaces[0].status == "ready"


def test_null_layout_version_is_unsupported(tmp_path: Path) -> None:
    workspace = tmp_path / "tenant-a" / "workspaces" / "default"
    _write_skill(workspace / "skills" / "demo")
    _write_v2_manifest(
        workspace,
        {"demo": {"enabled": False}},
        layout_version=None,
    )

    with pytest.raises(
        SkillLayoutMigrationError,
        match="unsupported layout_version None",
    ):
        check_workspace_skill_layout_migration(tmp_path)


@pytest.mark.parametrize("layout_version", [1, 3, 2.0, "2", False, True])
def test_check_rejects_unsupported_non_null_layout_version(
    tmp_path: Path,
    layout_version: object,
) -> None:
    workspace = tmp_path / "tenant-a" / "workspaces" / "default"
    _write_skill(workspace / "skills" / "demo")
    _write_v2_manifest(
        workspace,
        {"demo": {"enabled": True}},
        layout_version=layout_version,
    )

    with pytest.raises(
        SkillLayoutMigrationError,
        match="unsupported layout_version",
    ):
        check_workspace_skill_layout_migration(tmp_path)


@pytest.mark.parametrize("enabled", ["false", 0, 1, None, [], {}])
def test_check_rejects_non_boolean_enabled_values(
    tmp_path: Path,
    enabled: object,
) -> None:
    workspace = tmp_path / "tenant-a" / "workspaces" / "default"
    _write_skill(workspace / "skills" / "demo")
    skills: dict[str, dict[str, Any]] = {"demo": {"enabled": enabled}}
    _write_v2_manifest(workspace, skills)

    with pytest.raises(
        SkillLayoutMigrationError,
        match="enabled.*JSON boolean",
    ):
        check_workspace_skill_layout_migration(tmp_path)


def test_check_rejects_disabled_root_without_manifest(tmp_path: Path) -> None:
    workspace = tmp_path / "tenant-a" / "workspaces" / "default"
    _write_skill(workspace / ".disabled_skills" / "demo")

    with pytest.raises(SkillLayoutMigrationError, match="invalid partial"):
        check_workspace_skill_layout_migration(tmp_path)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{broken", "invalid JSON"),
        (json.dumps([]), "JSON object"),
        (json.dumps({"skills": []}), "skills.*object"),
        (
            json.dumps({"skills": {"demo": []}}),
            "entry.*JSON object",
        ),
    ],
)
def test_check_rejects_invalid_legacy_manifest(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    workspace = tmp_path / "tenant-a" / "workspaces" / "default"
    workspace.mkdir(parents=True)
    (workspace / "skill.json").write_text(content, encoding="utf-8")

    with pytest.raises(SkillLayoutMigrationError, match=message):
        check_workspace_skill_layout_migration(tmp_path)


def test_check_rejects_manifest_with_invalid_utf8(tmp_path: Path) -> None:
    workspace = tmp_path / "tenant-a" / "workspaces" / "default"
    workspace.mkdir(parents=True)
    (workspace / "skill.json").write_bytes(b'{"skills": {"demo": "\xff"}}')

    with pytest.raises(SkillLayoutMigrationError, match="invalid UTF-8"):
        check_workspace_skill_layout_migration(tmp_path)


def test_check_rejects_missing_registered_skill_document(
    tmp_path: Path,
) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")
    (workspace / "skills" / "demo" / "SKILL.md").unlink()

    with pytest.raises(SkillLayoutMigrationError, match="missing registered"):
        check_workspace_skill_layout_migration(tmp_path)


def test_check_accepts_valid_already_migrated_layout_and_ignores_unmanaged(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "tenant-a" / "workspaces" / "default"
    _write_skill(workspace / "skills" / "enabled")
    _write_skill(workspace / ".disabled_skills" / "disabled")
    _write_skill(workspace / "skills" / "unmanaged")
    _write_v2_manifest(
        workspace,
        {
            "enabled": {"enabled": True},
            "disabled": {"enabled": False},
        },
    )

    report = check_workspace_skill_layout_migration(tmp_path)

    assert report.workspaces[0].status == "already_migrated"


@pytest.mark.parametrize("case", ["missing", "wrong_root", "both_roots"])
def test_check_rejects_invalid_already_migrated_registered_state(
    tmp_path: Path,
    case: str,
) -> None:
    workspace = tmp_path / "tenant-a" / "workspaces" / "default"
    _write_v2_manifest(workspace, {"demo": {"enabled": False}})
    if case == "wrong_root":
        _write_skill(workspace / "skills" / "demo")
    elif case == "both_roots":
        _write_skill(workspace / "skills" / "demo")
        _write_skill(workspace / ".disabled_skills" / "demo")

    with pytest.raises(SkillLayoutMigrationError, match="registered skill"):
        check_workspace_skill_layout_migration(tmp_path)


def test_ready_layout_ignores_unregistered_skill_directories(
    tmp_path: Path,
) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")
    _write_skill(workspace / "skills" / "unmanaged")

    apply_workspace_skill_layout_migration(tmp_path)

    assert (workspace / "skills" / "unmanaged" / "SKILL.md").exists()
    assert (workspace / ".disabled_skills" / "demo" / "SKILL.md").exists()


def test_apply_preflights_all_workspaces_before_creating_backups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid = _legacy_workspace(tmp_path, "tenant-a")
    invalid = _legacy_workspace(tmp_path, "tenant-b")
    (invalid / "skills" / "demo" / "SKILL.md").unlink()
    temporary_directory_called = False

    def unexpected_temporary_directory(
        *args: object,
        **kwargs: object,
    ) -> None:
        nonlocal temporary_directory_called
        temporary_directory_called = True
        raise AssertionError("backup must not start before complete preflight")

    monkeypatch.setattr(
        migration.tempfile,
        "TemporaryDirectory",
        unexpected_temporary_directory,
    )
    before = _snapshot_paths(valid)

    with pytest.raises(SkillLayoutMigrationError, match="missing registered"):
        apply_workspace_skill_layout_migration(tmp_path)

    assert temporary_directory_called is False
    assert _snapshot_paths(valid) == before


@pytest.mark.parametrize(
    ("target_name", "permissions"),
    [
        ("workspace", stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH),
        ("workspace", stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH),
        ("skills", stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH),
        ("skills", stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH),
    ],
)
def test_check_rejects_ready_workspace_without_required_directory_access(
    tmp_path: Path,
    target_name: str,
    permissions: int,
) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")
    target = workspace if target_name == "workspace" else workspace / "skills"
    before = _snapshot_paths(workspace)
    original_mode = _remove_directory_permissions(target, permissions)
    restricted_mode = stat.S_IMODE(target.stat().st_mode)
    try:
        with pytest.raises(
            SkillLayoutMigrationError,
            match="write and execute access",
        ):
            check_workspace_skill_layout_migration(tmp_path)

        assert stat.S_IMODE(target.stat().st_mode) == restricted_mode
    finally:
        target.chmod(original_mode)
    assert _snapshot_paths(workspace) == before


@pytest.mark.parametrize(
    ("relative_path", "permissions", "message"),
    [
        (
            Path("skills/demo"),
            stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH,
            "read and execute access",
        ),
        (
            Path("skills/demo/SKILL.md"),
            stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH,
            "read access",
        ),
    ],
)
def test_check_rejects_unreadable_backup_tree_before_mutation(
    tmp_path: Path,
    relative_path: Path,
    permissions: int,
    message: str,
) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")
    target = workspace / relative_path
    before = _snapshot_paths(workspace)
    original_mode = stat.S_IMODE(target.lstat().st_mode)
    target.chmod(original_mode & ~permissions)
    restricted_mode = stat.S_IMODE(target.lstat().st_mode)
    try:
        with pytest.raises(SkillLayoutMigrationError, match=message):
            check_workspace_skill_layout_migration(tmp_path)

        assert stat.S_IMODE(target.lstat().st_mode) == restricted_mode
    finally:
        target.chmod(original_mode)
    assert _snapshot_paths(workspace) == before


@pytest.mark.parametrize("mismatch", ["owner", "group"])
def test_check_rejects_backup_tree_identity_non_root_cannot_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mismatch: str,
) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")
    target = workspace / "skills" / "demo" / "SKILL.md"
    before = _snapshot_paths(workspace)
    original_lstat = Path.lstat
    original_stat = Path.stat
    effective_uid = 1201
    effective_gid = 1202

    def simulated_lstat(path: Path) -> os.stat_result:
        result = original_lstat(path)
        values = list(result)
        values[4] = (
            2201 if path == target and mismatch == "owner" else effective_uid
        )
        values[5] = (
            2202 if path == target and mismatch == "group" else effective_gid
        )
        return os.stat_result(values)

    def simulated_stat(
        path: Path,
        *,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        result = original_stat(path, follow_symlinks=follow_symlinks)
        values = list(result)
        values[4] = (
            2201 if path == target and mismatch == "owner" else effective_uid
        )
        values[5] = (
            2202 if path == target and mismatch == "group" else effective_gid
        )
        return os.stat_result(values)

    monkeypatch.setattr(Path, "lstat", simulated_lstat)
    monkeypatch.setattr(Path, "stat", simulated_stat)
    monkeypatch.setattr(migration.os, "geteuid", lambda: effective_uid)
    monkeypatch.setattr(migration.os, "getegid", lambda: effective_gid)
    monkeypatch.setattr(migration.os, "getgroups", lambda: [1203])

    with pytest.raises(
        SkillLayoutMigrationError,
        match=f"cannot restore backup {mismatch}",
    ):
        check_workspace_skill_layout_migration(tmp_path)

    assert _snapshot_paths(workspace) == before


def test_check_allows_backup_tree_identity_for_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")
    target = workspace / "skills" / "demo" / "SKILL.md"
    original_lstat = Path.lstat

    def simulated_lstat(path: Path) -> os.stat_result:
        result = original_lstat(path)
        if path != target:
            return result
        values = list(result)
        values[4] = result.st_uid + 1000
        values[5] = result.st_gid + 1000
        return os.stat_result(values)

    monkeypatch.setattr(Path, "lstat", simulated_lstat)
    monkeypatch.setattr(migration.os, "geteuid", lambda: 0)

    report = check_workspace_skill_layout_migration(tmp_path)

    assert report.workspaces[0].status == "ready"


@pytest.mark.skipif(
    not hasattr(os, "mkfifo"),
    reason="FIFO creation is unavailable",
)
def test_check_rejects_special_file_in_backup_tree_without_mutation(
    tmp_path: Path,
) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")
    fifo = workspace / "skills" / "demo" / "unsupported.fifo"
    os.mkfifo(fifo)
    manifest = workspace / "skill.json"
    manifest_before = manifest.read_bytes()

    with pytest.raises(
        SkillLayoutMigrationError,
        match="unsupported special file",
    ):
        check_workspace_skill_layout_migration(tmp_path)

    assert stat.S_ISFIFO(fifo.lstat().st_mode)
    assert manifest.read_bytes() == manifest_before
    assert not (workspace / ".disabled_skills").exists()


def test_apply_rolls_back_all_attempted_workspaces_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspaces = [
        _legacy_workspace(tmp_path, "tenant-a"),
        _legacy_workspace(tmp_path, "tenant-b"),
    ]
    before = {
        workspace: _snapshot_paths(workspace) for workspace in workspaces
    }
    original_apply = migration._apply_workspace_migration
    call_count = 0

    def fail_on_second(workspace: Path, payload: dict[str, Any]) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            (workspace / "skills" / "partial.txt").write_text(
                "partial",
                encoding="utf-8",
            )
            raise OSError("second workspace failed")
        original_apply(workspace, payload)

    monkeypatch.setattr(
        migration,
        "_apply_workspace_migration",
        fail_on_second,
    )

    with pytest.raises(
        SkillLayoutMigrationError,
        match="second workspace failed",
    ):
        apply_workspace_skill_layout_migration(tmp_path)

    assert {
        workspace: _snapshot_paths(workspace) for workspace in workspaces
    } == (before)


@pytest.mark.skipif(
    not hasattr(os, "chown"),
    reason="numeric ownership restoration is unavailable",
)
def test_rollback_restores_captured_ownership_for_nested_paths_and_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")
    symlink = workspace / "skills" / "demo" / "skill-link"
    try:
        symlink.symlink_to("SKILL.md")
    except (NotImplementedError, OSError) as symlink_error:
        pytest.skip(f"symbolic links are unavailable: {symlink_error}")

    expected_paths = [
        workspace / "skill.json",
        workspace / "skills",
        workspace / "skills" / "demo",
        workspace / "skills" / "demo" / "SKILL.md",
        symlink,
    ]
    expected = {
        path.relative_to(workspace): (
            path.lstat().st_uid,
            path.lstat().st_gid,
            path.is_symlink(),
        )
        for path in expected_paths
    }
    chown_calls: list[tuple[Path, int, int, bool]] = []
    lchown_calls: list[tuple[Path, int, int]] = []
    original_lstat = Path.lstat

    def record_chown(
        path: os.PathLike[str] | str,
        uid: int,
        gid: int,
        *,
        follow_symlinks: bool = True,
    ) -> None:
        chown_calls.append((Path(path), uid, gid, follow_symlinks))

    monkeypatch.setattr(migration.os, "chown", record_chown)
    if hasattr(migration.os, "lchown"):

        def record_lchown(
            path: os.PathLike[str] | str,
            uid: int,
            gid: int,
        ) -> None:
            lchown_calls.append((Path(path), uid, gid))

        monkeypatch.setattr(migration.os, "lchown", record_lchown)

    def fail_after_removing_managed_paths(
        target_workspace: Path,
        payload: dict[str, Any],
    ) -> None:
        del payload
        migration._remove_path(target_workspace / "skill.json")
        migration._remove_path(target_workspace / "skills")

        def mismatched_restored_lstat(path: Path) -> os.stat_result:
            result = original_lstat(path)
            try:
                relative = path.relative_to(target_workspace)
            except ValueError:
                return result
            if relative.parts and relative.parts[0] in migration._BACKUP_PATHS:
                values = list(result)
                values[4] = result.st_uid + 1
                return os.stat_result(values)
            return result

        monkeypatch.setattr(Path, "lstat", mismatched_restored_lstat)
        raise OSError("force rollback")

    monkeypatch.setattr(
        migration,
        "_apply_workspace_migration",
        fail_after_removing_managed_paths,
    )

    with pytest.raises(SkillLayoutMigrationError, match="force rollback"):
        apply_workspace_skill_layout_migration(tmp_path)

    normal_calls = {
        path.relative_to(workspace): (uid, gid, follow_symlinks)
        for path, uid, gid, follow_symlinks in chown_calls
    }
    for relative, (uid, gid, is_symlink) in expected.items():
        if is_symlink and hasattr(migration.os, "lchown"):
            assert (workspace / relative, uid, gid) in lchown_calls
        else:
            assert normal_calls[relative] == (uid, gid, False)
    assert symlink.is_symlink()


def test_restore_symlink_identity_restores_lstat_mode_with_lchmod(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    target.write_text("target", encoding="utf-8")
    symlink = tmp_path / "link"
    try:
        symlink.symlink_to(target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")

    original_lstat = Path.lstat
    original_stat = original_lstat(symlink)
    simulated_mode = stat.S_IMODE(original_stat.st_mode)
    desired_mode = 0o700 if simulated_mode != 0o700 else 0o711
    lchmod_calls: list[tuple[Path, int]] = []

    def simulated_lstat(path: Path) -> os.stat_result:
        result = original_lstat(path)
        if path != symlink:
            return result
        values = list(result)
        values[0] = stat.S_IFLNK | simulated_mode
        return os.stat_result(values)

    def simulated_lchmod(
        path: os.PathLike[str] | str,
        mode: int,
    ) -> None:
        nonlocal simulated_mode
        lchmod_calls.append((Path(path), mode))
        simulated_mode = mode

    monkeypatch.setattr(Path, "lstat", simulated_lstat)
    monkeypatch.setattr(
        migration.os,
        "lchown",
        lambda path, uid, gid: None,
        raising=False,
    )
    monkeypatch.setattr(
        migration.os,
        "lchmod",
        simulated_lchmod,
        raising=False,
    )
    identity = migration._PathIdentity(
        relative_path=Path("link"),
        uid=original_stat.st_uid,
        gid=original_stat.st_gid,
        mode=stat.S_IFLNK | desired_mode,
    )

    migration._restore_path_identity(symlink, identity)

    assert lchmod_calls == [(symlink, desired_mode)]
    assert stat.S_IMODE(symlink.lstat().st_mode) == desired_mode


def test_restore_symlink_mode_succeeds_without_apis_when_already_equal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    target.write_text("target", encoding="utf-8")
    symlink = tmp_path / "link"
    try:
        symlink.symlink_to(target)
    except (NotImplementedError, OSError) as symlink_error:
        pytest.skip(f"symbolic links are unavailable: {symlink_error}")

    monkeypatch.delattr(migration.os, "lchmod", raising=False)
    monkeypatch.delattr(migration.os, "chmod", raising=False)

    migration._restore_symlink_mode(symlink, symlink.lstat().st_mode)


def test_restore_regular_identity_without_chown_when_owner_group_equal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "restored"
    path.write_text("restored", encoding="utf-8")
    path_stat = path.lstat()
    desired_mode = 0o640
    monkeypatch.delattr(migration.os, "chown", raising=False)
    identity = migration._PathIdentity(
        relative_path=Path("restored"),
        uid=path_stat.st_uid,
        gid=path_stat.st_gid,
        mode=stat.S_IFREG | desired_mode,
    )

    migration._restore_path_identity(path, identity)

    assert stat.S_IMODE(path.lstat().st_mode) == desired_mode


def test_restore_regular_identity_without_chown_rejects_different_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "restored"
    path.write_text("restored", encoding="utf-8")
    path_stat = path.lstat()
    monkeypatch.delattr(migration.os, "chown", raising=False)
    identity = migration._PathIdentity(
        relative_path=Path("restored"),
        uid=path_stat.st_uid + 1,
        gid=path_stat.st_gid,
        mode=path_stat.st_mode,
    )

    with pytest.raises(SkillLayoutMigrationError, match="path ownership"):
        migration._restore_path_identity(path, identity)


@pytest.mark.skipif(
    not hasattr(os, "chown"),
    reason="numeric ownership restoration is unavailable",
)
def test_rollback_reports_symlink_mode_when_all_apis_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")
    symlink = workspace / "skills" / "demo" / "skill-link"
    try:
        symlink.symlink_to("SKILL.md")
    except (NotImplementedError, OSError) as symlink_error:
        pytest.skip(f"symbolic links are unavailable: {symlink_error}")

    original_chmod = migration.os.chmod
    original_backup = migration._backup_workspace
    mode_attempts: list[str] = []

    def backup_with_different_symlink_mode(
        target_workspace: Path,
        backup_path: Path,
    ) -> migration._WorkspaceBackup:
        backup = original_backup(target_workspace, backup_path)
        identities: list[migration._PathIdentity] = []
        for identity in backup.identities:
            if identity.relative_path == Path("skills/demo/skill-link"):
                current_mode = stat.S_IMODE(identity.mode)
                desired_mode = 0o700 if current_mode != 0o700 else 0o711
                identity = migration._PathIdentity(
                    relative_path=identity.relative_path,
                    uid=identity.uid,
                    gid=identity.gid,
                    mode=stat.S_IFLNK | desired_mode,
                )
            identities.append(identity)
        return migration._WorkspaceBackup(backup.path, tuple(identities))

    def fail_lchmod(
        path: os.PathLike[str] | str,
        mode: int,
    ) -> None:
        del path, mode
        mode_attempts.append("lchmod")
        raise OSError("lchmod failed")

    def fail_nofollow_chmod(
        path: os.PathLike[str] | str,
        mode: int,
        *args: object,
        **kwargs: object,
    ) -> None:
        if kwargs.get("follow_symlinks") is False:
            mode_attempts.append("chmod")
            raise NotImplementedError("nofollow chmod unavailable")
        original_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr(
        migration.os,
        "lchown",
        lambda path, uid, gid: None,
        raising=False,
    )
    monkeypatch.setattr(
        migration,
        "_backup_workspace",
        backup_with_different_symlink_mode,
    )

    def fail_after_backup(workspace: Path, payload: dict[str, Any]) -> None:
        del workspace, payload
        monkeypatch.setattr(
            migration.os,
            "lchmod",
            fail_lchmod,
            raising=False,
        )
        monkeypatch.setattr(migration.os, "chmod", fail_nofollow_chmod)
        raise OSError("migration failed")

    monkeypatch.setattr(
        migration,
        "_apply_workspace_migration",
        fail_after_backup,
    )

    with pytest.raises(
        migration.SkillLayoutMigrationRollbackError,
    ) as exc_info:
        apply_workspace_skill_layout_migration(tmp_path)

    assert mode_attempts == ["lchmod", "chmod"]
    assert "symlink mode" in str(exc_info.value)
    assert "lchmod failed" in str(exc_info.value)
    assert "nofollow chmod unavailable" in str(exc_info.value)


@pytest.mark.skipif(
    not hasattr(os, "chown"),
    reason="numeric ownership restoration is unavailable",
)
def test_rollback_reports_all_ownership_restoration_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _legacy_workspace(tmp_path, "tenant-a")
    attempted_chowns: list[Path] = []
    original_lstat = Path.lstat

    def fail_chown(
        path: os.PathLike[str] | str,
        uid: int,
        gid: int,
        *,
        follow_symlinks: bool = True,
    ) -> None:
        del uid, gid, follow_symlinks
        attempted_chowns.append(Path(path))
        raise PermissionError("cannot restore ownership")

    monkeypatch.setattr(migration.os, "chown", fail_chown)

    def fail_with_mismatched_restored_ownership(
        target_workspace: Path,
        payload: dict[str, Any],
    ) -> None:
        del payload
        assert target_workspace == workspace

        def mismatched_restored_lstat(path: Path) -> os.stat_result:
            result = original_lstat(path)
            try:
                relative = path.relative_to(target_workspace)
            except ValueError:
                return result
            if relative.parts and relative.parts[0] in migration._BACKUP_PATHS:
                values = list(result)
                values[4] = result.st_uid + 1
                return os.stat_result(values)
            return result

        monkeypatch.setattr(Path, "lstat", mismatched_restored_lstat)
        raise OSError("migration failed")

    monkeypatch.setattr(
        migration,
        "_apply_workspace_migration",
        fail_with_mismatched_restored_ownership,
    )

    with pytest.raises(migration.SkillLayoutMigrationRollbackError) as exc:
        apply_workspace_skill_layout_migration(tmp_path)

    assert len(attempted_chowns) > 1
    assert "cannot restore ownership" in str(exc.value)


def test_atomic_manifest_failure_rolls_back_partially_moved_later_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspaces = [
        _legacy_workspace(tmp_path, "tenant-a"),
        _legacy_workspace(tmp_path, "tenant-b"),
    ]
    before = {
        workspace: _snapshot_paths(workspace) for workspace in workspaces
    }
    original_write = migration._write_manifest_atomic
    call_count = 0

    def fail_second_write(path: Path, payload: dict[str, Any]) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            assert not (workspaces[1] / "skills" / "demo").exists()
            assert (
                workspaces[1] / ".disabled_skills" / "demo" / "SKILL.md"
            ).exists()
            raise OSError("atomic manifest write failed")
        original_write(path, payload)

    monkeypatch.setattr(migration, "_write_manifest_atomic", fail_second_write)

    with pytest.raises(
        SkillLayoutMigrationError,
        match="atomic manifest write failed",
    ):
        apply_workspace_skill_layout_migration(tmp_path)

    assert {
        workspace: _snapshot_paths(workspace) for workspace in workspaces
    } == before


def test_rollback_failure_preserves_migration_and_rollback_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _legacy_workspace(tmp_path, "tenant-a")

    def fail_apply(workspace: Path, payload: dict[str, Any]) -> None:
        raise OSError("migration failed")

    def fail_restore(workspace: Path, backup: Path) -> None:
        raise PermissionError("rollback failed")

    monkeypatch.setattr(migration, "_apply_workspace_migration", fail_apply)
    monkeypatch.setattr(migration, "_restore_workspace_backup", fail_restore)

    with pytest.raises(SkillLayoutMigrationError) as exc_info:
        apply_workspace_skill_layout_migration(tmp_path)

    assert isinstance(exc_info.value.migration_error, OSError)
    assert str(exc_info.value.migration_error) == "migration failed"
    assert len(exc_info.value.rollback_errors) == 1
    assert isinstance(exc_info.value.rollback_errors[0], PermissionError)
    assert exc_info.value.__cause__ is exc_info.value.migration_error


def test_temporary_backup_is_removed_after_success_and_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[Path] = []

    class TrackingTemporaryDirectory(tempfile.TemporaryDirectory[str]):
        def __enter__(self) -> str:
            path = super().__enter__()
            created.append(Path(path))
            return path

    monkeypatch.setattr(
        migration.tempfile,
        "TemporaryDirectory",
        TrackingTemporaryDirectory,
    )
    _legacy_workspace(tmp_path, "tenant-a")
    apply_workspace_skill_layout_migration(tmp_path)
    assert created and all(not path.exists() for path in created)

    failure_root = tmp_path / "failure"
    _legacy_workspace(failure_root, "tenant-a")
    monkeypatch.setattr(
        migration,
        "_apply_workspace_migration",
        lambda workspace, payload: (_ for _ in ()).throw(OSError("boom")),
    )
    with pytest.raises(SkillLayoutMigrationError, match="boom"):
        apply_workspace_skill_layout_migration(failure_root)
    assert all(not path.exists() for path in created)
