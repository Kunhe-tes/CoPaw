# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import os
import stat
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


_OBSOLETE_V2_MANIFEST = Path(".skill_state") / "manifest.json"


def _reject_symbolic_link(path: Path, description: str) -> None:
    if path.is_symlink():
        raise SkillLayoutMigrationError(
            f"Refusing symbolic link for {description}: {path}",
        )


def _validate_managed_root(path: Path, description: str) -> None:
    _reject_symbolic_link(path, description)
    if path.exists() and not path.is_dir():
        raise SkillLayoutMigrationError(
            f"Workspace {description} must be a directory: {path}",
        )


def _permission_bits_for_effective_user(
    path: Path,
) -> tuple[int, int, int]:
    try:
        file_stat = path.stat()
    except OSError as exc:
        raise SkillLayoutMigrationError(
            f"Unable to inspect directory permissions: {path}: {exc}",
        ) from exc

    if not hasattr(os, "geteuid"):
        return (
            stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH,
            stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH,
            stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
        )

    effective_uid = os.geteuid()
    if effective_uid == 0:
        return (
            stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH,
            stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH,
            stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
        )
    if effective_uid == file_stat.st_uid:
        return stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR

    effective_groups = {os.getegid(), *os.getgroups()}
    if file_stat.st_gid in effective_groups:
        return stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP
    return stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH


def _has_directory_access(
    path: Path,
    *,
    require_read: bool,
    require_write: bool,
) -> bool:
    read_bit, write_bit, execute_bit = _permission_bits_for_effective_user(
        path,
    )
    mode = path.stat().st_mode
    required_access = (
        os.X_OK
        | (os.R_OK if require_read else 0)
        | (os.W_OK if require_write else 0)
    )
    try:
        allowed_by_system = os.access(
            path,
            required_access,
            effective_ids=True,
        )
    except (NotImplementedError, TypeError):
        allowed_by_system = os.access(path, required_access)
    has_required_bits = (
        bool(mode & execute_bit)
        and (not require_read or bool(mode & read_bit))
        and (not require_write or bool(mode & write_bit))
    )
    return allowed_by_system and has_required_bits


def _require_directory_access(
    path: Path,
    description: str,
    *,
    require_read: bool = False,
    require_write: bool,
) -> None:
    if not _has_directory_access(
        path,
        require_read=require_read,
        require_write=require_write,
    ):
        if require_read and require_write:
            access = "read, write, and execute"
        elif require_read:
            access = "read and execute"
        else:
            access = "write and execute"
        raise SkillLayoutMigrationError(
            f"Workspace migration requires {access} access for "
            f"{description}: {path}",
        )


def _require_file_read_access(path: Path, description: str) -> None:
    read_bit, _, _ = _permission_bits_for_effective_user(path)
    mode = path.stat().st_mode
    try:
        allowed_by_system = os.access(path, os.R_OK, effective_ids=True)
    except (NotImplementedError, TypeError):
        allowed_by_system = os.access(path, os.R_OK)
    if not allowed_by_system or not bool(mode & read_bit):
        raise SkillLayoutMigrationError(
            f"Workspace migration requires read access for {description}: "
            f"{path}",
        )


def _validate_manifest_metadata_preservation(path: Path) -> None:
    if not hasattr(os, "geteuid"):
        return
    manifest_stat = path.stat(follow_symlinks=False)
    effective_uid = os.geteuid()
    if effective_uid == 0:
        return
    if manifest_stat.st_uid != effective_uid:
        raise SkillLayoutMigrationError(
            f"Workspace migration cannot preserve manifest owner: {path}",
        )
    effective_groups = {os.getegid(), *os.getgroups()}
    if manifest_stat.st_gid not in effective_groups:
        raise SkillLayoutMigrationError(
            f"Workspace migration cannot preserve manifest group: {path}",
        )


def _discover_workspaces(working_dir: Path) -> list[Path]:
    release_root = Path(working_dir).expanduser()
    _reject_symbolic_link(release_root, "release root")
    if not release_root.exists():
        return []
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
    except UnicodeError as exc:
        raise SkillLayoutMigrationError(
            f"Manifest contains invalid UTF-8: {path}: {exc}",
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
        if "enabled" in entry and not isinstance(entry["enabled"], bool):
            raise SkillLayoutMigrationError(
                f"Manifest entry for {skill_name!r} enabled must be a JSON "
                f"boolean: {path}",
            )
    return payload


def _normalize_legacy_payload(
    workspace: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    normalized = copy.deepcopy(payload)
    active_root = workspace / "skills"
    disabled_root = get_workspace_disabled_skills_dir(workspace)
    for skill_name, entry in list(normalized["skills"].items()):
        active = active_root / skill_name
        disabled = disabled_root / skill_name
        active_document = active / "SKILL.md"
        disabled_document = disabled / "SKILL.md"
        if active.exists():
            _require_directory_access(
                active,
                "registered active skill package",
                require_read=True,
                require_write=False,
            )
        if disabled.exists():
            _require_directory_access(
                disabled,
                "registered disabled skill package",
                require_read=True,
                require_write=False,
            )
        _reject_symbolic_link(active, "registered active skill package")
        _reject_symbolic_link(
            active_document,
            "registered active skill document",
        )
        _reject_symbolic_link(
            disabled,
            "registered disabled skill package",
        )
        _reject_symbolic_link(
            disabled_document,
            "registered disabled skill document",
        )
        active_exists = active_document.is_file()
        disabled_exists = disabled_document.is_file()
        if active_exists:
            _require_file_read_access(
                active_document,
                "registered active skill document",
            )
        if disabled_exists:
            _require_file_read_access(
                disabled_document,
                "registered disabled skill document",
            )
        if not active_exists and not disabled_exists:
            del normalized["skills"][skill_name]
            continue
        if active_exists and disabled_exists:
            raise SkillLayoutMigrationError(
                f"Workspace {workspace} has ambiguous registered skill "
                f"{skill_name!r} in both managed roots",
            )
        if entry.get("enabled", False) is True and not active_exists:
            raise SkillLayoutMigrationError(
                f"Workspace {workspace} registered enabled skill "
                f"{skill_name!r} is missing from the active root",
            )
    return normalized


def _validate_migrated_workspace(
    workspace: Path,
    payload: dict[str, Any],
) -> None:
    layout_version = payload.get("layout_version")
    if (
        not isinstance(layout_version, int)
        or isinstance(layout_version, bool)
        or layout_version != WORKSPACE_SKILL_LAYOUT_VERSION
    ):
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

        enabled = entry.get("enabled", False) is True
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
    _require_directory_access(
        workspace,
        "Workspace root",
        require_write=False,
    )
    manifest = get_workspace_skill_manifest_path(workspace)
    obsolete_manifest = workspace / _OBSOLETE_V2_MANIFEST
    state_root = obsolete_manifest.parent
    disabled_root = get_workspace_disabled_skills_dir(workspace)
    active_root = workspace / "skills"
    _validate_managed_root(active_root, "active skills root")
    _validate_managed_root(disabled_root, "disabled skills root")
    _validate_managed_root(state_root, "skill state root")
    _reject_symbolic_link(manifest, "Workspace skill manifest")
    _reject_symbolic_link(obsolete_manifest, "obsolete v2 skill manifest")

    if obsolete_manifest.exists():
        raise SkillLayoutMigrationError(
            f"Workspace {workspace} has mixed layout: obsolete manifest "
            f"exists at {_OBSOLETE_V2_MANIFEST}",
        )

    if not manifest.exists():
        if disabled_root.exists():
            raise SkillLayoutMigrationError(
                f"Workspace {workspace} has invalid partial skill layout "
                "state",
            )
        return _WorkspaceMigrationPlan(workspace, "not_applicable")

    if not stat.S_ISREG(manifest.lstat().st_mode):
        raise SkillLayoutMigrationError(
            f"Workspace skill manifest must be a regular file: " f"{manifest}",
        )

    payload = _read_manifest(manifest)
    layout_version = payload.get("layout_version")
    if "layout_version" not in payload:
        _require_directory_access(
            workspace,
            "Workspace root",
            require_write=True,
        )
        if active_root.exists():
            _require_directory_access(
                active_root,
                "active skills root",
                require_read=True,
                require_write=any(
                    entry.get("enabled", False) is not True
                    for entry in payload["skills"].values()
                ),
            )
        if disabled_root.exists():
            _require_directory_access(
                disabled_root,
                "disabled skills root",
                require_read=True,
                require_write=False,
            )
        payload = _normalize_legacy_payload(workspace, payload)
        if disabled_root.exists() and any(
            entry.get("enabled", False) is not True
            and not (disabled_root / skill_name / "SKILL.md").is_file()
            for skill_name, entry in payload["skills"].items()
        ):
            _require_directory_access(
                disabled_root,
                "disabled skills root",
                require_write=True,
            )
        _validate_manifest_metadata_preservation(manifest)
        return _WorkspaceMigrationPlan(workspace, "ready", payload)

    if (
        isinstance(layout_version, int)
        and not isinstance(layout_version, bool)
        and layout_version == WORKSPACE_SKILL_LAYOUT_VERSION
    ):
        _validate_migrated_workspace(workspace, payload)
        return _WorkspaceMigrationPlan(
            workspace,
            "already_migrated",
            payload,
        )

    raise SkillLayoutMigrationError(
        f"Workspace {workspace} has unsupported layout_version "
        f"{layout_version!r}",
    )


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


def _write_manifest_atomic(path: Path, payload: dict[str, Any]) -> None:
    temp_path: Path | None = None
    manifest_stat = path.stat(follow_symlinks=False)
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
        temp_stat = temp_path.stat(follow_symlinks=False)
        if (
            temp_stat.st_uid != manifest_stat.st_uid
            or temp_stat.st_gid != manifest_stat.st_gid
        ):
            if not hasattr(os, "chown"):
                raise SkillLayoutMigrationError(
                    f"Unable to preserve manifest owner/group: {path}",
                )
            try:
                os.chown(
                    temp_path,
                    manifest_stat.st_uid,
                    manifest_stat.st_gid,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise SkillLayoutMigrationError(
                    f"Unable to preserve manifest owner/group: {path}: "
                    f"{exc}",
                ) from exc
        try:
            temp_path.chmod(stat.S_IMODE(manifest_stat.st_mode))
        except OSError as exc:
            raise SkillLayoutMigrationError(
                f"Unable to preserve manifest mode: {path}: {exc}",
            ) from exc
        temp_path.replace(path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _apply_workspace_migration(
    workspace: Path,
    payload: dict[str, Any],
) -> None:
    """Migrate one preflighted Workspace without creating backups."""
    migrated_payload = copy.deepcopy(payload)
    migrated_payload["layout_version"] = WORKSPACE_SKILL_LAYOUT_VERSION
    active_root = workspace / "skills"
    disabled_root = get_workspace_disabled_skills_dir(workspace)

    for skill_name, entry in migrated_payload["skills"].items():
        if entry.get("enabled", False) is True:
            continue
        source = active_root / skill_name
        target = disabled_root / skill_name
        if (target / "SKILL.md").is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)

    _write_manifest_atomic(
        get_workspace_skill_manifest_path(workspace),
        migrated_payload,
    )


def apply_workspace_skill_layout_migration(
    working_dir: Path,
) -> SkillLayoutMigrationReport:
    """Migrate ready Workspaces in order without rolling back progress."""
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

    for plan in ready:
        try:
            if plan.payload is None:  # pragma: no cover - invariant
                raise SkillLayoutMigrationError(
                    f"Missing preflight payload for {plan.workspace}",
                )
            _apply_workspace_migration(plan.workspace, plan.payload)
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
