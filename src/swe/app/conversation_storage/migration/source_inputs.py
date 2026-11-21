# -*- coding: utf-8 -*-
"""Explicit conversation inputs, shared by inventory and source fencing."""

from pathlib import Path
import os
import stat
import uuid

from ..bundle import MAX_BUNDLE_BYTES, MAX_READ_BYTES
from ..chat_mutations import load_metadata_json
from .spool import MigrationCapacityError


class SourceInputInvalid(ValueError):
    """Unsafe or malformed tenant source input, distinct from shared failures."""


def conversation_artifact_limit(
    path,
    root,
    *,
    sessions_dir="sessions",
    dialog_dir="dialog",
):
    """Use the bundle size limit for message-bearing legacy files."""
    relative = Path(path).relative_to(Path(root))
    if any(
        relative == Path(directory) or relative.is_relative_to(Path(directory))
        for directory in (sessions_dir, dialog_dir)
    ):
        return MAX_BUNDLE_BYTES
    return MAX_READ_BYTES


def _relative(value):
    path = Path(value)
    if not path.parts or path.is_absolute() or ".." in path.parts:
        raise SourceInputInvalid(
            "source path must be relative to trusted workspace",
        )
    return path


def _inspect_input_entry(
    path,
    *,
    explicit,
    trusted,
    allow_in_root_symlinks,
    skip_unselected_unsafe,
    found,
    entry_limit,
    max_file_bytes,
    max_total_file_bytes,
    total_file_bytes,
):
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode):
        if not allow_in_root_symlinks:
            raise SourceInputInvalid(
                "source contains symlink; explicit regular-file snapshot required",
            )
        try:
            resolved = path.resolve(strict=True)
        except FileNotFoundError:
            if skip_unselected_unsafe and path not in explicit:
                return None, total_file_bytes
            raise SourceInputInvalid(
                "selected source symlink is broken",
            ) from None
        if not resolved.is_relative_to(trusted):
            if skip_unselected_unsafe and path not in explicit:
                return None, total_file_bytes
            raise SourceInputInvalid("selected source path escapes workspace")
        details = resolved.stat()
    if not (stat.S_ISREG(details.st_mode) or stat.S_ISDIR(details.st_mode)):
        if skip_unselected_unsafe and path not in explicit:
            return None, total_file_bytes
        raise SourceInputInvalid(
            "source contains unsupported filesystem object",
        )
    if path not in found:
        if entry_limit is not None and len(found) >= entry_limit:
            raise MigrationCapacityError(
                "workspace source entries exceed migration memory allowance",
            )
        if stat.S_ISREG(details.st_mode) and (
            max_file_bytes is not None or max_total_file_bytes is not None
        ):
            size = details.st_size
            if max_file_bytes is not None and size > max_file_bytes:
                raise MigrationCapacityError(
                    "workspace source file exceeds the bounded reader limit: "
                    + str(path),
                )
            if max_total_file_bytes is not None:
                total_file_bytes += size
                if total_file_bytes > max_total_file_bytes:
                    raise MigrationCapacityError(
                        "workspace source exceeds its migration memory allowance",
                    )
        found[path] = details
    return details, total_file_bytes


def safe_input_entries(
    root,
    relative_roots,
    *,
    recursive=True,
    entry_limit=None,
    max_file_bytes=None,
    max_total_file_bytes=None,
    trusted_root=None,
    allow_in_root_symlinks=False,
    skip_unselected_unsafe=False,
):
    """Inspect selected entrances, never enumerate their unselected parents.

    Ancestor directories are included as shallow safety/freeze evidence.
    Missing entrances are allowed: the semantic reader checks required files.
    """
    root = Path(root).absolute()
    found = {}
    total_file_bytes = 0
    trusted = Path(trusted_root or root).resolve(strict=True)
    resolved_root = root.resolve(strict=True)
    if resolved_root != root and (
        not allow_in_root_symlinks or not resolved_root.is_relative_to(trusted)
    ):
        raise SourceInputInvalid(
            "source root contains a symlink or is not canonical",
        )
    selected = {_relative(value) for value in relative_roots}
    explicit = {root / value for value in selected}

    def inspect(path):
        nonlocal total_file_bytes
        details, total_file_bytes = _inspect_input_entry(
            path,
            explicit=explicit,
            trusted=trusted,
            allow_in_root_symlinks=allow_in_root_symlinks,
            skip_unselected_unsafe=skip_unselected_unsafe,
            found=found,
            entry_limit=entry_limit,
            max_file_bytes=max_file_bytes,
            max_total_file_bytes=max_total_file_bytes,
            total_file_bytes=total_file_bytes,
        )
        return details

    if not stat.S_ISDIR(inspect(root).st_mode):
        raise SourceInputInvalid("source root must be a directory")

    walked = set()

    def walk(path):
        pending = [path]
        while pending:
            current = pending.pop()
            details = inspect(current)
            if details is None:
                continue
            canonical = current.resolve(strict=True)
            if canonical in walked:
                continue
            walked.add(canonical)
            if stat.S_ISDIR(details.st_mode):
                children = []
                # Path.iterdir may materialize os.listdir before yielding.
                # Inspect and admit each entry while scandir is still bounded.
                with os.scandir(current) as entries:
                    for entry in entries:
                        child = current / entry.name
                        if inspect(child) is not None:
                            children.append(child)
                pending.extend(sorted(children, reverse=True))

    for relative in sorted(selected):
        path = root
        for part in relative.parts:
            path = path / part
            try:
                inspect(path)
            except FileNotFoundError:
                break
        else:
            if recursive:
                walk(path)
    return sorted(found)


def session_input_roots(
    root,
    session_paths=(),
    *,
    registry_path="chats.json",
    sessions_dir="sessions",
    dialog_dir="dialog",
    max_session_bytes=MAX_BUNDLE_BYTES,
):
    """Fixed conversation entrances plus reviewed Session/ledger overrides."""
    roots = [registry_path, sessions_dir, dialog_dir]
    values = (
        session_paths.values()
        if isinstance(session_paths, dict)
        else session_paths
    )
    root = Path(root).absolute()
    for value in values:
        relative = _relative(value)
        roots.append(relative)
        # Validate each component before reading an override outside sessions/.
        entries = safe_input_entries(root, [relative], recursive=False)
        path = root / relative
        if path in entries and not path.is_file():
            raise SourceInputInvalid(
                "Session override must name a regular file",
            )
        if (
            path not in entries
            or not path.is_file()
            or path.stat().st_size > max_session_bytes
        ):
            continue
        try:
            state = load_metadata_json(path.read_bytes())
        except (ValueError, UnicodeError) as error:
            raise SourceInputInvalid("Session override is invalid") from error
        if isinstance(state, dict) and state.get("schema_version") == 3:
            generation = state.get("session_generation")
            try:
                valid_generation = (
                    isinstance(generation, str)
                    and str(uuid.UUID(generation)) == generation
                )
            except ValueError:
                valid_generation = False
            if not valid_generation:
                raise SourceInputInvalid("Invalid session ledger generation")
            roots.append(relative.parent / ".turn-ledger" / generation)
    return tuple(roots)


def workspace_entries(mapping):
    return safe_input_entries(
        mapping.root,
        session_input_roots(
            mapping.root,
            mapping.session_paths,
            registry_path=mapping.registry_path,
            sessions_dir=mapping.sessions_dir,
            dialog_dir=mapping.dialog_dir,
        ),
    )


def workspace_files(mapping):
    return [path for path in workspace_entries(mapping) if path.is_file()]
