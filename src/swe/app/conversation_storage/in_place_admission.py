# -*- coding: utf-8 -*-
"""Reject shared mutable tenant boundaries before admitting in-place writers."""

from pathlib import Path

from .errors import IntegrityError


def _overlaps(left, right):
    return (
        left == right
        or left.is_relative_to(right)
        or right.is_relative_to(left)
    )


def tenant_write_boundaries(source, *, tenant=None):
    """Frozen workspace/config ownership, independent of parent directory mtime.

    Ordinary parent directories are not ownership units: two tenant directories
    under one service root are expected. Exact config/Agent evidence files and
    whole workspace subtrees are ownership units and cannot cross tenants.
    """
    services = {
        item["service_unit_id"]: item for item in source.get("services", [])
    }
    in_place = set()
    for name, service in services.items():
        if Path(service["source_root"]) == Path(service["original_root"]):
            in_place.add(name)
    boundaries = []
    for workspace in source.get("workspaces", []):
        name = workspace["service_unit_id"]
        if name not in in_place:
            continue
        owner = name, workspace["tenant_id"]
        root = Path(workspace["runtime_root"])
        if (tenant is None or tenant == owner) and (
            not root.is_absolute() or root != root.resolve()
        ):
            raise IntegrityError(
                "in-place workspace boundary is not canonical",
            )
        boundaries.append((owner, root, True))
        for reference in workspace.get("evidence_refs", []):
            path = Path(reference)
            if (tenant is None or tenant == owner) and (
                not path.is_absolute() or path != path.resolve()
            ):
                raise IntegrityError(
                    "in-place evidence boundary is not canonical",
                )
            boundaries.append((owner, path, False))
    for tenant_record in source.get("tenants", []):
        name = tenant_record["service_unit_id"]
        if name not in in_place:
            continue
        owner = name, tenant_record["tenant_id"]
        for reference in tenant_record.get("evidence_refs", []):
            path = Path(reference)
            if (tenant is None or tenant == owner) and (
                not path.is_absolute() or path != path.resolve()
            ):
                raise IntegrityError(
                    "in-place tenant evidence is not canonical",
                )
            boundaries.append((owner, path, False))
            original = Path(services[name]["original_root"])
            relative = (
                path.relative_to(original)
                if path.is_relative_to(original)
                else None
            )
            if relative is not None and len(relative.parts) >= 2:
                boundaries.append((owner, original / relative.parts[0], True))
    selected = (
        boundaries
        if tenant is None
        else [item for item in boundaries if item[0] == tenant]
    )
    for owner, path, directory in selected:
        for other_owner, other, other_directory in boundaries:
            if owner == other_owner:
                continue
            if (
                path == other
                or (directory and other.is_relative_to(path))
                or (other_directory and path.is_relative_to(other))
            ):
                raise IntegrityError(
                    "in-place tenants share mutable workspace or config evidence",
                )
    return boundaries


def require_workspace_boundary(source, scope, root):
    owner = scope.service_unit_id, scope.tenant_id
    boundaries = tenant_write_boundaries(source, tenant=owner)
    root = Path(root)
    for other_owner, path, directory in boundaries:
        if other_owner == owner:
            continue
        if (
            _overlaps(root, path)
            if directory
            else (path == root or path.is_relative_to(root))
        ):
            raise IntegrityError(
                "workspace would write another tenant migration inputs",
            )
