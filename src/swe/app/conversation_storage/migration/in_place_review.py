# -*- coding: utf-8 -*-
"""Frozen ownership based pruning for a reviewed in-place tenant retry."""

from contextlib import contextmanager
from contextvars import ContextVar
import os
from pathlib import Path
from .isolation import unit_key

_PUBLISHED_ROOTS = ContextVar(
    "conversation_published_source_roots",
    default=(),
)
_PUBLISHED_INPUTS = ContextVar(
    "conversation_published_inputs",
    default=(),
)
_FROZEN_SHARE_SOURCES = ContextVar(
    "conversation_frozen_share_sources",
    default=None,
)


def frozen_share_source(token):
    return (_FROZEN_SHARE_SOURCES.get() or {}).get(token)


_FROZEN_SHARE_OWNERS = ContextVar(
    "conversation_frozen_share_owners",
    default=None,
)


def share_services(services, token):
    """Use frozen ownership when reviewing shares beside live tenants."""
    owners = _FROZEN_SHARE_OWNERS.get()
    if owners is None:
        return services
    candidates = owners.get(token, set())
    if len(candidates) != 1:
        raise ValueError(
            "share frozen service ownership is absent or ambiguous",
        )
    selected = [s for s in services if s["service_unit_id"] in candidates]
    if len(selected) != 1:
        raise ValueError(
            "share frozen service ownership is absent or ambiguous",
        )
    return selected


def require_unpublished(path, *, directory=False):
    """Reject explicit cross-owner inputs without resolving or touching them."""
    path = Path(os.path.abspath(path))
    for protected, subtree in _PUBLISHED_INPUTS.get():
        if (
            path == protected
            or (subtree and path.is_relative_to(protected))
            or (directory and protected.is_relative_to(path))
        ):
            raise ValueError(
                "candidate overlaps published tenant frozen ownership",
            )


def skipped(path):
    path = Path(path)
    return any(
        path == root or path.is_relative_to(root)
        for root in _PUBLISHED_ROOTS.get()
    )


@contextmanager
def published_pruning(data, published):
    roots = set()
    for service in data["services"]:
        base = Path(service.get("config_root") or service["source_root"])
        owners = {}
        candidates = list(data["workspaces"]) + list(data.get("tenants", []))
        for workspace in candidates:
            if workspace["service_unit_id"] != service["service_unit_id"]:
                continue
            key = unit_key(data, workspace)
            for ref in workspace.get("evidence_refs", []):
                path = Path(ref)
                if path.name != "config.json" or not path.is_relative_to(base):
                    continue
                parts = path.relative_to(base).parts
                if len(parts) == 2:
                    owners.setdefault(base / parts[0], set()).add(key)
        for root, keys in owners.items():
            if keys & published:
                if len(keys) != 1:
                    raise ValueError(
                        "published source directory has shared tenant ownership",
                    )
                roots.add(root)
        covered = {
            key
            for root, keys in owners.items()
            if root in roots
            for key in keys
        }
        if any(
            key[0] == service["service_unit_id"] and key not in covered
            for key in published
        ):
            raise ValueError(
                "published tenant lacks exclusive source directory evidence",
            )
    inputs = {(root, True) for root in roots}
    for item in [*data["workspaces"], *data.get("tenants", [])]:
        if unit_key(data, item) not in published:
            continue
        for field in ("root", "runtime_root"):
            if item.get(field):
                inputs.add((Path(item[field]), True))
        inputs.update(
            (Path(ref), False) for ref in item.get("evidence_refs", [])
        )
    for share in data.get("shares", []):
        if unit_key(data, share) in published:
            inputs.add((Path(share["snapshot_path"]), False))
    roots.update(path for path, directory in inputs if directory)
    share_owners = {}
    for share in data.get("shares", []):
        share_owners.setdefault(share["token"], set()).add(
            share["service_unit_id"],
        )
    token = _PUBLISHED_ROOTS.set(tuple(roots))
    input_token = _PUBLISHED_INPUTS.set(tuple(inputs))
    owner_token = _FROZEN_SHARE_OWNERS.set(share_owners)
    source_token = _FROZEN_SHARE_SOURCES.set(
        {
            s["token"]: s["source_id"]
            for s in data.get("shares", [])
            if data.get("source_isolation")
        },
    )
    try:
        yield
    finally:
        _FROZEN_SHARE_SOURCES.reset(source_token)
        _FROZEN_SHARE_OWNERS.reset(owner_token)
        _PUBLISHED_INPUTS.reset(input_token)
        _PUBLISHED_ROOTS.reset(token)
