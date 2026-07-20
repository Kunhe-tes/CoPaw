# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .skills_manager import (
    WORKSPACE_SKILL_LAYOUT_VERSION,
    get_workspace_disabled_skills_dir,
    get_workspace_skill_manifest_path,
)


class SkillLayoutMigrationError(RuntimeError):
    """Report an invalid layout or a failed Workspace layout migration."""


class SkillLayoutMigrationRollbackError(SkillLayoutMigrationError):
    """Report a migration failure whose rollback also failed."""

    def __init__(
        self,
        migration_error: Exception,
        rollback_errors: tuple[Exception, ...],
    ) -> None:
        super().__init__(
            "Workspace skill layout migration failed and rollback also "
            f"failed: {migration_error}; rollback errors: "
            + "; ".join(str(error) for error in rollback_errors),
        )
        self.migration_error = migration_error
        self.rollback_errors = rollback_errors


@dataclass(frozen=True)
class WorkspaceMigrationResult:
    workspace: Path
    status: str


@dataclass(frozen=True)
class SkillLayoutMigrationReport:
    success: bool
    workspaces: tuple[WorkspaceMigrationResult, ...]


@dataclass(frozen=True)
class _WorkspaceMigrationPlan:
    workspace: Path
    status: str
    payload: dict[str, Any] | None = None


_BACKUP_PATHS = (
    "skill.json",
    "skills",
    ".disabled_skills",
    ".skill_state",
)
_OBSOLETE_V2_MANIFEST_PATH = Path(".skill_state") / "manifest.json"


def _reject_symbolic_link(path: Path, description: str) -> None:
    if path.is_symlink():
        raise SkillLayoutMigrationError(
            f"Refusing symbolic link for {description}: {path}",
        )


def _discover_workspaces(working_dir: Path) -> list[Path]:
    release_root = Path(working_dir).expanduser()
    if not release_root.exists():
        return []
    _reject_symbolic_link(release_root, "release root")
    if not release_root.is_dir():
        raise SkillLayoutMigrationError(
            f"Release root is not a directory: {release_root}",
        )

    discovered: list[Path] = []
    for tenant in sorted(release_root.iterdir()):
        _reject_symbolic_link(tenant, "tenant")
        if not tenant.is_dir():
            continue
        workspaces_root = tenant / "workspaces"
        _reject_symbolic_link(workspaces_root, "tenant workspaces root")
        if not workspaces_root.is_dir():
            continue
        for workspace in sorted(workspaces_root.iterdir()):
            _reject_symbolic_link(workspace, "Workspace")
            if workspace.is_dir():
                discovered.append(workspace)
    return discovered


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SkillLayoutMigrationError(
            f"Manifest contains invalid JSON: {path}: {exc}",
        ) from exc
    except OSError as exc:
        raise SkillLayoutMigrationError(
            f"Unable to read Workspace skill manifest: {path}: {exc}",
        ) from exc

    if not isinstance(payload, dict):
        raise SkillLayoutMigrationError(
            f"Manifest must be a JSON object: {path}",
        )
    skills = payload.get("skills")
    if not isinstance(skills, dict):
        raise SkillLayoutMigrationError(
            f"Manifest skills must be a JSON object: {path}",
        )
    for skill_name, entry in skills.items():
        if not isinstance(skill_name, str) or not skill_name:
            raise SkillLayoutMigrationError(
                f"Manifest skill name must be a non-empty string: {path}",
            )
        if (
            Path(skill_name).name != skill_name
            or skill_name in {".", ".."}
            or "/" in skill_name
            or "\\" in skill_name
        ):
            raise SkillLayoutMigrationError(
                f"Manifest contains unsafe registered skill name "
                f"{skill_name!r}: {path}",
            )
        if not isinstance(entry, dict):
            raise SkillLayoutMigrationError(
                f"Manifest entry for {skill_name!r} must be a JSON object: "
                f"{path}",
            )
    return payload


def _validate_ready_workspace(
    workspace: Path,
    payload: dict[str, Any],
) -> None:
    active_root = workspace / "skills"
    for skill_name in payload["skills"]:
        skill_package = active_root / skill_name
        skill_document = skill_package / "SKILL.md"
        _reject_symbolic_link(skill_package, "registered skill package")
        _reject_symbolic_link(skill_document, "registered skill document")
        if not skill_document.is_file():
            raise SkillLayoutMigrationError(
                f"Workspace {workspace} is missing registered skill "
                f"document: skills/{skill_name}/SKILL.md",
            )


def _validate_migrated_workspace(
    workspace: Path,
    payload: dict[str, Any],
) -> None:
    if payload.get("layout_version") != WORKSPACE_SKILL_LAYOUT_VERSION:
        raise SkillLayoutMigrationError(
            f"Workspace {workspace} has unsupported layout_version "
            f"{payload.get('layout_version')!r}",
        )

    active_root = workspace / "skills"
    disabled_root = get_workspace_disabled_skills_dir(workspace)
    for skill_name, entry in payload["skills"].items():
        active = active_root / skill_name
        disabled = disabled_root / skill_name
        _reject_symbolic_link(active, "registered active skill package")
        _reject_symbolic_link(disabled, "registered disabled skill package")
        _reject_symbolic_link(
            active / "SKILL.md",
            "registered active skill document",
        )
        _reject_symbolic_link(
            disabled / "SKILL.md",
            "registered disabled skill document",
        )
        if active.exists() and disabled.exists():
            raise SkillLayoutMigrationError(
                f"Workspace {workspace} has ambiguous registered skill "
                f"{skill_name!r} in both managed roots",
            )

        enabled = bool(entry.get("enabled", False))
        desired = active if enabled else disabled
        undesired = disabled if enabled else active
        if not (desired / "SKILL.md").is_file():
            raise SkillLayoutMigrationError(
                f"Workspace {workspace} registered skill {skill_name!r} "
                f"is missing from its {'enabled' if enabled else 'disabled'} "
                "root",
            )
        if undesired.exists():
            raise SkillLayoutMigrationError(
                f"Workspace {workspace} registered skill {skill_name!r} "
                "exists in the wrong managed root",
            )


def _preflight_workspace(workspace: Path) -> _WorkspaceMigrationPlan:
    _reject_symbolic_link(workspace, "Workspace")
    legacy_manifest = get_workspace_skill_manifest_path(workspace)
    v2_manifest = workspace / _OBSOLETE_V2_MANIFEST_PATH
    state_root = v2_manifest.parent
    disabled_root = get_workspace_disabled_skills_dir(workspace)
    active_root = workspace / "skills"
    _reject_symbolic_link(active_root, "active skills root")
    _reject_symbolic_link(disabled_root, "disabled skills root")
    _reject_symbolic_link(state_root, "skill state root")
    _reject_symbolic_link(legacy_manifest, "legacy skill manifest")
    _reject_symbolic_link(v2_manifest, "v2 skill manifest")
    legacy_exists = legacy_manifest.exists()
    v2_exists = v2_manifest.exists()

    if legacy_exists and v2_exists:
        raise SkillLayoutMigrationError(
            f"Workspace {workspace} has mixed layout: both legacy and v2 "
            "manifests exist",
        )

    if legacy_exists:
        if disabled_root.exists():
            raise SkillLayoutMigrationError(
                f"Workspace {workspace} has mixed layout: legacy manifest "
                "exists with the disabled skill root",
            )
        payload = _read_manifest(legacy_manifest)
        _validate_ready_workspace(workspace, payload)
        return _WorkspaceMigrationPlan(workspace, "ready", payload)

    if v2_exists:
        payload = _read_manifest(v2_manifest)
        _validate_migrated_workspace(workspace, payload)
        return _WorkspaceMigrationPlan(
            workspace,
            "already_migrated",
            payload,
        )

    if state_root.exists() or disabled_root.exists():
        raise SkillLayoutMigrationError(
            f"Workspace {workspace} has invalid partial skill layout state",
        )

    return _WorkspaceMigrationPlan(workspace, "not_applicable")


def _preflight_workspaces(working_dir: Path) -> list[_WorkspaceMigrationPlan]:
    plans: list[_WorkspaceMigrationPlan] = []
    errors: list[SkillLayoutMigrationError] = []
    for workspace in _discover_workspaces(working_dir):
        try:
            plans.append(_preflight_workspace(workspace))
        except SkillLayoutMigrationError as exc:
            errors.append(exc)
    if errors:
        raise SkillLayoutMigrationError(
            "Workspace skill layout preflight failed: "
            + "; ".join(str(error) for error in errors),
        ) from errors[0]
    return plans


def check_workspace_skill_layout_migration(
    working_dir: Path,
) -> SkillLayoutMigrationReport:
    """Read and validate every Workspace without changing the filesystem."""
    plans = _preflight_workspaces(working_dir)
    return SkillLayoutMigrationReport(
        success=True,
        workspaces=tuple(
            WorkspaceMigrationResult(plan.workspace, plan.status)
            for plan in plans
        ),
    )


def _copy_backup_path(source: Path, target: Path) -> None:
    if source.is_dir() and not source.is_symlink():
        shutil.copytree(source, target, symlinks=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target, follow_symlinks=False)


def _backup_workspace(workspace: Path, backup: Path) -> None:
    backup.mkdir(parents=True, exist_ok=True)
    for relative in _BACKUP_PATHS:
        source = workspace / relative
        if source.exists() or source.is_symlink():
            _copy_backup_path(source, backup / relative)


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _restore_workspace_backup(workspace: Path, backup: Path) -> None:
    for relative in _BACKUP_PATHS:
        _remove_path(workspace / relative)
    for relative in _BACKUP_PATHS:
        source = backup / relative
        if source.exists() or source.is_symlink():
            _copy_backup_path(source, workspace / relative)


def _write_manifest_atomic(path: Path, payload: dict[str, Any]) -> None:
    temp_path: Path | None = None
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=path.parent,
            prefix=f".{path.stem}_",
            suffix=path.suffix,
            delete=False,
            encoding="utf-8",
        ) as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            temp_path = Path(handle.name)
        temp_path.replace(path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _apply_workspace_migration(
    workspace: Path,
    payload: dict[str, Any],
) -> None:
    """Migrate one preflighted Workspace; callers provide rollback."""
    migrated_payload = copy.deepcopy(payload)
    migrated_payload["layout_version"] = WORKSPACE_SKILL_LAYOUT_VERSION
    active_root = workspace / "skills"
    disabled_root = get_workspace_disabled_skills_dir(workspace)

    for skill_name, entry in migrated_payload["skills"].items():
        if bool(entry.get("enabled", False)):
            continue
        source = active_root / skill_name
        target = disabled_root / skill_name
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)

    _write_manifest_atomic(
        workspace / _OBSOLETE_V2_MANIFEST_PATH,
        migrated_payload,
    )
    get_workspace_skill_manifest_path(workspace).unlink()


def apply_workspace_skill_layout_migration(
    working_dir: Path,
) -> SkillLayoutMigrationReport:
    """Migrate all ready Workspaces atomically as one release operation."""
    plans = _preflight_workspaces(working_dir)
    ready = [plan for plan in plans if plan.status == "ready"]
    if not ready:
        return SkillLayoutMigrationReport(
            success=True,
            workspaces=tuple(
                WorkspaceMigrationResult(plan.workspace, plan.status)
                for plan in plans
            ),
        )

    try:
        with tempfile.TemporaryDirectory(
            prefix="workspace-skill-layout-migration-",
        ) as temporary_directory:
            backup_root = Path(temporary_directory)
            backups: dict[Path, Path] = {}
            for index, plan in enumerate(ready):
                backup = backup_root / str(index)
                _backup_workspace(plan.workspace, backup)
                backups[plan.workspace] = backup

            attempted: list[_WorkspaceMigrationPlan] = []
            try:
                for plan in ready:
                    attempted.append(plan)
                    if plan.payload is None:  # pragma: no cover - invariant
                        raise SkillLayoutMigrationError(
                            f"Missing preflight payload for {plan.workspace}",
                        )
                    _apply_workspace_migration(plan.workspace, plan.payload)
            except Exception as migration_error:
                rollback_errors: list[Exception] = []
                for plan in reversed(attempted):
                    try:
                        _restore_workspace_backup(
                            plan.workspace,
                            backups[plan.workspace],
                        )
                    except Exception as rollback_error:
                        rollback_errors.append(rollback_error)
                if rollback_errors:
                    raise SkillLayoutMigrationRollbackError(
                        migration_error,
                        tuple(rollback_errors),
                    ) from migration_error
                raise SkillLayoutMigrationError(
                    "Workspace skill layout migration failed: "
                    f"{migration_error}",
                ) from migration_error
    except SkillLayoutMigrationError:
        raise
    except Exception as exc:
        raise SkillLayoutMigrationError(
            f"Workspace skill layout migration failed: {exc}",
        ) from exc

    return SkillLayoutMigrationReport(
        success=True,
        workspaces=tuple(
            WorkspaceMigrationResult(
                plan.workspace,
                "migrated" if plan.status == "ready" else plan.status,
            )
            for plan in plans
        ),
    )
