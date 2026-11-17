# -*- coding: utf-8 -*-
"""Content evidence for fixed conversation entrances and exact identity files."""

from hashlib import sha256
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import json
import os
import stat

from .source_inputs import SourceInputInvalid, workspace_entries
from .tenant_errors import SourceChanged

_RETAINED_INPUTS = ContextVar(
    "conversation_retained_input_digests",
    default=None,
)


@contextmanager
def retained_input_digests(data, keys):
    from .isolation import unit_key

    token = _RETAINED_INPUTS.set(
        {
            unit_key(data, t): t.get("input_digest")
            for t in data["tenants"]
            if unit_key(data, t) in keys
        },
    )
    try:
        yield
    finally:
        _RETAINED_INPUTS.reset(token)


def _key(item):
    key = item["service_unit_id"], item["tenant_id"]
    return (*key, item["source_id"]) if "source_id" in item else key


def _file_digest(path):
    from .in_place_review import require_unpublished

    require_unpublished(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise SourceInputInvalid("tenant evidence must be a regular file")
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    current = path.lstat()
    fields = (
        "st_dev",
        "st_ino",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
        "st_mode",
    )
    if any(
        getattr(before, f) != getattr(after, f)
        or getattr(after, f) != getattr(current, f)
        for f in fields
    ):
        raise SourceChanged("tenant input changed while recording evidence")
    return digest.hexdigest()


def input_digest(data, key):
    from .inventory_v3 import _workspace_mappings

    selected = {
        **data,
        "workspaces": [
            w for w in data["workspaces"] if _key(w)[: len(key)] == key
        ],
    }
    entries = set()
    for mapping in _workspace_mappings(selected):
        entries.update(workspace_entries(mapping))
    for item in [*selected["workspaces"], *data.get("tenants", [])]:
        if _key(item)[: len(key)] == key:
            entries.update(Path(p) for p in item.get("evidence_refs", []))
    entries.update(
        Path(s["snapshot_path"])
        for s in data["shares"]
        if _key(s)[: len(key)] == key
    )
    digest = sha256()
    for path in sorted(entries):
        from .in_place_review import require_unpublished

        require_unpublished(path)
        details = path.lstat()
        if stat.S_ISDIR(details.st_mode):
            value = [str(path), "directory"]
        elif stat.S_ISREG(details.st_mode):
            value = [str(path), _file_digest(path)]
        else:
            raise SourceInputInvalid("tenant source object is unsafe")
        digest.update(json.dumps(value, ensure_ascii=False).encode())
    return digest.hexdigest()


def verify_input_digest(data, key):
    if data.get("freshness_protocol"):
        return
    tenant = next(t for t in data["tenants"] if _key(t)[: len(key)] == key)
    expected = tenant.get("input_digest")
    # Existing manifests retain their original source freshness contract.
    if expected is not None and input_digest(data, key) != expected:
        raise SourceChanged("tenant input changed after preparation")


def verify_chats_mtimes(data, key):
    """Check only the frozen chats.json timestamp for a new source job."""
    from .isolation import belongs

    for workspace in data["workspaces"]:
        if not belongs(workspace, key):
            continue
        verify_workspace_chats_mtime(workspace)


def verify_workspace_chats_mtime(workspace):
    registry = Path(workspace["root"]) / workspace.get(
        "registry_path",
        "chats.json",
    )
    if registry.is_symlink():
        raise SourceInputInvalid("chats.json cannot be a symlink")
    try:
        details = registry.lstat()
    except FileNotFoundError:
        raise SourceInputInvalid("chats.json is missing") from None
    if not stat.S_ISREG(details.st_mode):
        raise SourceInputInvalid("chats.json must be a regular file")
    if details.st_mtime_ns != workspace.get("chats_mtime_ns"):
        raise SourceChanged("chats.json changed after preparation")


def _capture_digest(item):
    from .spool import MigrationCapacityError

    data, key = item
    try:
        return input_digest(data, key)
    except (
        SourceInputInvalid,
        SourceChanged,
        MigrationCapacityError,
        FileNotFoundError,
    ) as error:
        return error


def capture_input_digests(report, mapper=None):
    retained = _RETAINED_INPUTS.get() or {}
    selected = []
    for tenant in report["tenants"]:
        if tenant["state"] == "failed":
            continue
        if _key(tenant) in retained:
            if retained[_key(tenant)] is not None:
                tenant["input_digest"] = retained[_key(tenant)]
            continue
        selected.append(tenant)
    items = ((report, _key(tenant)) for tenant in selected)
    results = (
        mapper(items, _capture_digest)
        if mapper
        else map(_capture_digest, items)
    )
    for tenant, result in zip(selected, results):
        if isinstance(result, Exception):
            blocker = {
                "code": "tenant_input_invalid",
                "position": json.dumps(_key(tenant)),
                "detail": str(result),
            }
            tenant["state"] = "failed"
            tenant["blockers"].append(blocker)
            report["blockers"].append(blocker)
        else:
            tenant["input_digest"] = result
    if report["blockers"]:
        report.update(ready=False, status="partial_success")
