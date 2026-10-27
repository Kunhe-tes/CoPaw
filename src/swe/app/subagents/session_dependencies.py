# -*- coding: utf-8 -*-
"""Chat-scoped frozen dependency views for received community experts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
from uuid import UUID

from ...agents.skills_manager import (
    _build_signature,
    get_skill_freshness_token,
)
from ...config.config import AgentProfileConfig
from .agent_definitions import AgentOwnedDefinitionRepository
from .launch_snapshot import (
    _copy_skill_tree_no_symlinks,
    _diagnostics,
    _remove_snapshot_tree,
    _snapshot_frozen_mcps,
    _write_private_mcp_snapshot,
    skill_tree_is_regular,
)
from .models import SubAgentDefinition, SubAgentLaunchDiagnostics

_EXPERT_SESSION_ROOT_NAME = ".expert_sessions"
_BINDING_FILE_NAME = ".binding.json"


class ExpertDependencyViewError(OSError):
    """A selected received expert has no valid private dependency view."""


def initialize_community_expert_dependency_view(
    *,
    workspace_dir: Path,
    chat_id: str,
    definition: SubAgentDefinition,
) -> Path | None:
    """Create a Chat-local immutable copy the first time it is selected.

    The received package remains the source of record.  This temporary view
    prevents an administrator update from changing dependencies midway through
    an existing Chat, while keeping the package out of Agent Profile runtime
    Skill/MCP registries.
    """
    metadata = definition.agent_owned
    community = getattr(metadata, "community", None)
    if metadata is None or community is None:
        return None

    definition_id = _canonical_uuid(metadata.definition_id, "definition id")
    canonical_chat_id = _canonical_uuid(chat_id, "chat id")
    workspace = Path(workspace_dir).resolve()
    source = workspace / "agents" / f"{definition_id}.dependencies"
    _validate_frozen_dependency_root(source, definition)
    target = (
        workspace
        / _EXPERT_SESSION_ROOT_NAME
        / canonical_chat_id
        / definition_id
    )
    binding = _binding_payload(definition)
    if _view_matches_definition(target, definition_id, community.item_id):
        _validate_frozen_dependency_root(
            target,
            definition,
            dependency_names=_view_dependency_names(target, definition),
        )
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{definition_id}-",
            dir=target.parent,
        ),
    )
    try:
        _copy_regular_tree(source, temporary)
        _write_binding(temporary / _BINDING_FILE_NAME, binding)
        try:
            os.replace(temporary, target)
        except OSError:
            if not _view_matches_definition(
                target,
                definition_id,
                community.item_id,
            ):
                raise
            _validate_frozen_dependency_root(
                target,
                definition,
                dependency_names=_view_dependency_names(target, definition),
            )
    finally:
        _remove_snapshot_tree(temporary)
    return target


def resolve_community_expert_dependency_view(
    *,
    workspace_dir: Path,
    chat_id: str,
    definition: SubAgentDefinition,
    view_root: str | Path | None,
) -> Path | None:
    """Accept only the selected expert's own initialized Chat view."""
    if view_root is None:
        return None
    metadata = definition.agent_owned
    community = getattr(metadata, "community", None)
    if metadata is None or community is None:
        return None
    definition_id = _canonical_uuid(metadata.definition_id, "definition id")
    canonical_chat_id = _canonical_uuid(chat_id, "chat id")
    workspace = Path(workspace_dir).resolve()
    expected = (
        workspace
        / _EXPERT_SESSION_ROOT_NAME
        / canonical_chat_id
        / definition_id
    )
    candidate = Path(view_root)
    try:
        if candidate.resolve() != expected.resolve():
            return None
    except OSError:
        return None
    if not _view_matches_definition(
        expected,
        definition_id,
        community.item_id,
    ):
        return None
    _validate_frozen_dependency_root(
        expected,
        definition,
        dependency_names=_view_dependency_names(expected, definition),
    )
    return expected


def release_community_expert_dependency_views(
    *,
    workspace_dir: Path,
    definition_id: str,
) -> None:
    """Immediately discard all temporary dependency views for one expert."""
    canonical_definition_id = _canonical_uuid(definition_id, "definition id")
    root = Path(workspace_dir).resolve() / _EXPERT_SESSION_ROOT_NAME
    if not root.is_dir() or root.is_symlink():
        return
    for chat_root in root.iterdir():
        try:
            _canonical_uuid(chat_root.name, "chat id")
        except ExpertDependencyViewError:
            continue
        if not chat_root.is_dir() or chat_root.is_symlink():
            continue
        _remove_snapshot_tree(chat_root / canonical_definition_id)


def release_community_expert_dependency_view_for_chat(
    *,
    workspace_dir: Path,
    chat_id: str,
) -> None:
    """Release all received-expert bindings belonging to an ended Chat."""
    canonical_chat_id = _canonical_uuid(chat_id, "chat id")
    root = (
        Path(workspace_dir).resolve()
        / _EXPERT_SESSION_ROOT_NAME
        / canonical_chat_id
    )
    _remove_snapshot_tree(root)


def capture_community_expert_session_dependencies(
    *,
    run_store_dir: Path,
    run_id: str,
    dependency_view_root: Path,
    definition: SubAgentDefinition,
    parent_agent_config: AgentProfileConfig,
) -> tuple[list[str], str | None, SubAgentLaunchDiagnostics]:
    """Make one worker launch from a validated session dependency view."""
    del parent_agent_config
    metadata = definition.agent_owned
    if metadata is None or metadata.community is None:
        raise ExpertDependencyViewError(
            "expert is not a received community expert",
        )
    dependency_names = _view_dependency_names(dependency_view_root, definition)
    _validate_frozen_dependency_root(
        dependency_view_root,
        definition,
        dependency_names=dependency_names,
    )
    snapshot_root = run_store_dir / f"{run_id}.skills"
    loaded_skills: list[str] = []
    freshness_tokens: dict[str, str] = {}
    try:
        for skill_name in dependency_names[0]:
            source = dependency_view_root / "skills" / skill_name
            target = snapshot_root / skill_name
            _copy_skill_tree_no_symlinks(source, target)
            loaded_skills.append(skill_name)
            freshness_tokens[skill_name] = get_skill_freshness_token(source)
        mcp_payload, snapshotted_mcps, skipped_mcps = _snapshot_frozen_mcps(
            dependency_view_root,
            dependency_names[1],
        )
        private_path = _write_private_mcp_snapshot(
            run_store_dir,
            run_id,
            mcp_payload,
        )
    except OSError:
        _remove_snapshot_tree(snapshot_root)
        raise
    return (
        [str(snapshot_root / name) for name in loaded_skills],
        private_path,
        _diagnostics(
            loaded_skills,
            [],
            freshness_tokens,
            snapshotted_mcps,
            skipped_mcps,
        ),
    )


def _canonical_uuid(value: str, field_name: str) -> str:
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ExpertDependencyViewError(
            f"{field_name} must be a UUID",
        ) from exc
    if str(parsed) != str(value):
        raise ExpertDependencyViewError(
            f"{field_name} must use canonical UUID format",
        )
    return str(parsed)


def _binding_payload(definition: SubAgentDefinition) -> dict[str, Any]:
    metadata = definition.agent_owned
    assert metadata is not None and metadata.community is not None
    return {
        "definition_id": metadata.definition_id,
        "item_id": metadata.community.item_id,
        "version": metadata.community.version,
        "content_fingerprint": metadata.community.content_fingerprint,
        "declared_skills": list(metadata.declared_skills),
        "declared_mcps": list(metadata.declared_mcps or []),
    }


def _view_dependency_names(
    root: Path,
    definition: SubAgentDefinition,
) -> tuple[list[str], list[str]]:
    metadata = definition.agent_owned
    fallback = (
        list(metadata.declared_skills if metadata else []),
        list(
            (
                metadata.declared_mcps
                if metadata and metadata.declared_mcps
                else []
            ),
        ),
    )
    try:
        payload = json.loads(
            (root / _BINDING_FILE_NAME).read_text(encoding="utf-8"),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return fallback
    skills = payload.get("declared_skills")
    mcps = payload.get("declared_mcps")
    if not isinstance(skills, list) or not all(
        isinstance(item, str) for item in skills
    ):
        return fallback
    if not isinstance(mcps, list) or not all(
        isinstance(item, str) for item in mcps
    ):
        return fallback
    return list(skills), list(mcps)


def _view_matches_definition(
    root: Path,
    definition_id: str,
    item_id: str,
) -> bool:
    if not root.is_dir() or root.is_symlink():
        return False
    path = root / _BINDING_FILE_NAME
    if not path.is_file() or path.is_symlink():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("definition_id") == definition_id
        and payload.get("item_id") == item_id
    )


def _write_binding(path: Path, payload: dict[str, str]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _validate_frozen_dependency_root(
    root: Path,
    definition: SubAgentDefinition,
    *,
    dependency_names: tuple[list[str], list[str]] | None = None,
) -> None:
    metadata = definition.agent_owned
    assert metadata is not None
    if (
        not root.is_dir()
        or root.is_symlink()
        or not skill_tree_is_regular(root)
    ):
        raise ExpertDependencyViewError(
            "frozen expert dependency directory is missing or invalid",
        )
    declared_skills, declared_mcps = dependency_names or (
        list(metadata.declared_skills),
        list(metadata.declared_mcps or []),
    )
    for skill_name in declared_skills:
        _validate_dependency_name(skill_name, "skill")
        skill_root = root / "skills" / skill_name
        if (
            not skill_root.is_dir()
            or skill_root.is_symlink()
            or not skill_tree_is_regular(skill_root)
        ):
            raise ExpertDependencyViewError(
                f"frozen expert dependency is missing: skill {skill_name}",
            )
    for mcp_name in declared_mcps:
        _validate_dependency_name(mcp_name, "MCP")
    _snapshot_frozen_mcps(root, declared_mcps)


def _validate_dependency_name(name: str, dependency_type: str) -> None:
    if not isinstance(name, str) or not name or name in {".", ".."}:
        raise ExpertDependencyViewError(
            f"frozen expert {dependency_type} name is unsafe: {name!r}",
        )
    if any(separator in name for separator in ("/", "\\", "\x00")):
        raise ExpertDependencyViewError(
            f"frozen expert {dependency_type} name is unsafe: {name!r}",
        )


def _copy_regular_tree(source: Path, target: Path) -> None:
    """Copy a checked regular package tree without preserving symlinks."""
    if source.is_symlink() or not skill_tree_is_regular(source):
        raise ExpertDependencyViewError("frozen expert dependency is invalid")
    for entry in source.iterdir():
        destination = target / entry.name
        if entry.is_dir():
            shutil.copytree(entry, destination)
        elif entry.is_file():
            shutil.copy2(entry, destination)
        else:
            raise ExpertDependencyViewError(
                f"frozen expert dependency has unsupported entry: {entry.name}",
            )


def initialize_community_expert_main_dependency_view(
    *,
    workspace_dir: Path,
    chat_id: str,
    definition: SubAgentDefinition,
) -> Path | None:
    """Publish a versioned view without changing legacy Chat freezing.

    The marketplace stages a temporary definition before swapping dependencies,
    then publishes the definition last. Reject that window and source changes
    during copying rather than mixing instructions and resources.
    """
    metadata = definition.agent_owned
    if metadata is None or metadata.community is None:
        return None
    definition_id = _canonical_uuid(metadata.definition_id, "definition id")
    canonical_chat_id = _canonical_uuid(chat_id, "chat id")
    workspace = Path(workspace_dir).resolve()
    source = workspace / "agents" / f"{definition_id}.dependencies"
    binding = _binding_payload(definition)
    before = _main_dependency_source_state(workspace, definition)
    binding["dependency_signature"] = before[2]
    identity = hashlib.sha256(
        json.dumps(binding, sort_keys=True).encode("utf-8"),
    ).hexdigest()
    parent = (
        workspace
        / _EXPERT_SESSION_ROOT_NAME
        / canonical_chat_id
        / ".main"
        / definition_id
    )
    _validate_main_view_parent(workspace, parent)
    target = parent / identity
    if _main_view_matches(target, binding):
        _validate_frozen_dependency_root(target, definition)
        _validate_main_skill_entrypoints(target, definition)
        if _main_dependency_content_signature(target) != before[2]:
            raise ExpertDependencyViewError("expert dependency view changed")
        _require_main_dependency_source_state(workspace, definition, before)
        return target
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = Path(
        tempfile.mkdtemp(prefix=".main-", suffix=".tmp", dir=parent),
    )
    try:
        temporary.rmdir()
        _copy_skill_tree_no_symlinks(source, temporary)
        _validate_frozen_dependency_root(temporary, definition)
        if _main_dependency_content_signature(temporary) != before[2]:
            raise ExpertDependencyViewError(
                "expert dependencies changed during capture",
            )
        _write_binding(temporary / _BINDING_FILE_NAME, binding)
        _require_main_dependency_source_state(workspace, definition, before)
        try:
            os.replace(temporary, target)
        except OSError:
            if not _main_view_matches(target, binding):
                raise
            _validate_frozen_dependency_root(target, definition)
        _require_main_dependency_source_state(workspace, definition, before)
        return target
    finally:
        _remove_snapshot_tree(temporary)


def _validate_main_view_parent(workspace: Path, parent: Path) -> None:
    candidate = parent
    while candidate != workspace:
        if candidate.is_symlink():
            raise ExpertDependencyViewError(
                "expert dependency view path is invalid",
            )
        candidate = candidate.parent


def _main_view_matches(root: Path, binding: dict[str, Any]) -> bool:
    if not root.is_dir() or root.is_symlink():
        return False
    path = root / _BINDING_FILE_NAME
    if path.is_symlink():
        return False
    try:
        return json.loads(path.read_text(encoding="utf-8")) == binding
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False


def _main_dependency_source_state(
    workspace: Path,
    definition: SubAgentDefinition,
) -> tuple[str, tuple[int, int], str]:
    metadata = definition.agent_owned
    assert metadata is not None
    root = workspace / "agents"
    if root.is_symlink():
        raise ExpertDependencyViewError("expert definition root is invalid")
    definition_id = _canonical_uuid(metadata.definition_id, "definition id")
    if any(root.glob(f".{definition_id}.toml.*.tmp")) or any(
        root.glob(f".{definition_id}.dependencies.backup-*"),
    ):
        raise ExpertDependencyViewError("expert update is in progress")
    definition_path = root / f"{definition_id}.toml"
    if definition_path.is_symlink():
        raise ExpertDependencyViewError("expert definition path is invalid")
    repository = AgentOwnedDefinitionRepository(
        root,
        owner_scope=definition.owner_scope,
    )
    package = repository.get(definition_id)
    if (
        package is None
        or package.definition is None
        or not package.definition.enabled
    ):
        raise ExpertDependencyViewError("expert definition is unavailable")
    excluded = {"created_at", "updated_at"}
    if package.definition.model_dump(
        exclude=excluded,
    ) != definition.model_dump(exclude=excluded):
        raise ExpertDependencyViewError(
            "expert definition changed during capture",
        )
    source = root / f"{definition_id}.dependencies"
    _validate_frozen_dependency_root(source, definition)
    _validate_main_skill_entrypoints(source, definition)
    stat = source.stat()
    return (
        package.revision,
        (stat.st_dev, stat.st_ino),
        _main_dependency_content_signature(source),
    )


def _validate_main_skill_entrypoints(
    root: Path,
    definition: SubAgentDefinition,
) -> None:
    for name in definition.agent_owned.declared_skills:
        entrypoint = root / "skills" / name / "SKILL.md"
        if not entrypoint.is_file() or entrypoint.is_symlink():
            raise ExpertDependencyViewError(
                f"frozen expert dependency is missing: skill {name}",
            )


def _main_dependency_content_signature(root: Path) -> str:
    payload = [_build_signature(root / name) for name in ("skills", "mcp")]
    return hashlib.sha256(json.dumps(payload).encode("utf-8")).hexdigest()


def _require_main_dependency_source_state(
    workspace: Path,
    definition: SubAgentDefinition,
    expected: tuple[str, tuple[int, int], str],
) -> None:
    if _main_dependency_source_state(workspace, definition) != expected:
        raise ExpertDependencyViewError(
            "expert dependencies changed during capture",
        )
