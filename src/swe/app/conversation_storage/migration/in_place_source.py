# -*- coding: utf-8 -*-
"""Precise evidence fencing for an explicitly selected in-place migration."""

from hashlib import sha256
from pathlib import Path
import os
import stat

from .source_inputs import SourceInputInvalid, safe_input_entries


def shared_service_roots(data):
    if data.get("in_place") is not True:
        return set()
    return {
        str(Path(service[key]))
        for service in data["services"]
        for key in (
            "source_root",
            "config_root",
            "snapshot_root",
            "original_root",
        )
        if service.get(key)
    }


def evidence_paths(data, workspace):
    """Ignore only shared root mtime, retaining exact files and private parents."""
    shared = shared_service_roots(data)
    result = []
    for value in workspace.get("evidence_refs", []):
        path = Path(value)
        result.append(str(path))
        if str(path.parent) not in shared:
            result.append(str(path.parent))
    return result


def freeze_evidence(workspace):
    """Hash explicit config and Agent evidence; never scan their parents."""
    result = {}
    for value in workspace.get("evidence_refs", []):
        path = Path(value)
        entries = safe_input_entries(
            path.parent,
            [path.name],
            recursive=False,
        )
        before = path.lstat() if path in entries else None
        if before is None or not stat.S_ISREG(before.st_mode):
            raise SourceInputInvalid(
                "in-place identity evidence must be a file",
            )
        if before.st_mode & 0o222:
            raise SourceInputInvalid("in-place identity evidence is writable")
        digest = sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(64 * 1024):
                digest.update(chunk)
            after = os.fstat(stream.fileno())
        fields = (
            "st_dev",
            "st_ino",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
            "st_mode",
        )
        current = path.lstat()
        if any(
            getattr(before, key) != getattr(after, key) for key in fields
        ) or any(
            getattr(after, key) != getattr(current, key) for key in fields
        ):
            raise SourceInputInvalid(
                "in-place identity evidence changed while reading",
            )
        result[str(path)] = digest.hexdigest()
    return result


def verify_evidence(data, workspace):
    if data.get("in_place") is not True:
        return
    frozen = workspace.get("in_place_evidence")
    if frozen is None:
        # Initial discovery assembles evidence before freezing the report.
        return
    if not isinstance(frozen, dict) or set(frozen) != set(
        workspace.get("evidence_refs", []),
    ):
        raise SourceInputInvalid("in-place identity evidence set differs")
    if freeze_evidence(workspace) != frozen:
        raise SourceInputInvalid("in-place identity evidence changed")
