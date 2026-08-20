# -*- coding: utf-8 -*-
"""Chat-scoped frozen dependency views for received community experts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
from uuid import UUID

from ...agents.skills_manager import get_skill_freshness_token
from ...config.config import AgentProfileConfig
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
    if _view_matches(target, binding):
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
        if target.exists() or target.is_symlink():
            _remove_snapshot_tree(target)
        os.replace(temporary, target)
    except BaseException:
        _remove_snapshot_tree(temporary)
        raise
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
    if not _view_matches(expected, _binding_payload(definition)):
        return None
    _validate_frozen_dependency_root(expected, definition)
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
    _validate_frozen_dependency_root(dependency_view_root, definition)
    snapshot_root = run_store_dir / f"{run_id}.skills"
    loaded_skills: list[str] = []
    freshness_tokens: dict[str, str] = {}
    try:
        for skill_name in metadata.declared_skills:
            source = dependency_view_root / "skills" / skill_name
            target = snapshot_root / skill_name
            _copy_skill_tree_no_symlinks(source, target)
            loaded_skills.append(skill_name)
            freshness_tokens[skill_name] = get_skill_freshness_token(source)
        mcp_payload, snapshotted_mcps, skipped_mcps = _snapshot_frozen_mcps(
            dependency_view_root,
            metadata.declared_mcps,
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


def _binding_payload(definition: SubAgentDefinition) -> dict[str, str]:
    metadata = definition.agent_owned
    assert metadata is not None and metadata.community is not None
    return {
        "definition_id": metadata.definition_id,
        "item_id": metadata.community.item_id,
        "version": metadata.community.version,
        "content_fingerprint": metadata.community.content_fingerprint,
    }


def _view_matches(root: Path, expected: dict[str, str]) -> bool:
    if not root.is_dir() or root.is_symlink():
        return False
    path = root / _BINDING_FILE_NAME
    if not path.is_file() or path.is_symlink():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return payload == expected


def _write_binding(path: Path, payload: dict[str, str]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _validate_frozen_dependency_root(
    root: Path,
    definition: SubAgentDefinition,
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
    for skill_name in metadata.declared_skills:
        skill_root = root / "skills" / skill_name
        if (
            not skill_root.is_dir()
            or skill_root.is_symlink()
            or not skill_tree_is_regular(skill_root)
        ):
            raise ExpertDependencyViewError(
                f"frozen expert dependency is missing: skill {skill_name}",
            )
    _snapshot_frozen_mcps(root, metadata.declared_mcps)


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
