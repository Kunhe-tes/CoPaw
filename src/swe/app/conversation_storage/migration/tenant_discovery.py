# -*- coding: utf-8 -*-
"""Conservative failure attribution for independently published tenants."""

from copy import deepcopy
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import json
from pathlib import Path

from ..identity import WorkspaceScope
from .isolation import unit_key, belongs


def _tenant_semantic(selected, validator):
    from .inventory_v3 import inventory_discovery
    from .source_inputs import SourceInputInvalid
    from .spool import MigrationCapacityError, MigrationDiskCapacityError

    try:
        registry_stats = {}
        if selected.get("freshness_protocol"):
            for workspace in selected["workspaces"]:
                registry = Path(workspace["root"]) / workspace.get(
                    "registry_path",
                    "chats.json",
                )
                before = registry.lstat()
                registry_stats[workspace["position"]] = (
                    registry,
                    before.st_mtime_ns,
                )
        if selected.get("freshness_protocol"):
            _verify_readonly_evidence(selected)
        if selected.get("in_place") and not selected.get(
            "freshness_protocol",
        ):
            from .in_place_source import freeze_evidence

            for item in selected["workspaces"]:
                item["in_place_evidence"] = freeze_evidence(item)
        result = (validator or inventory_discovery)(selected)
        for workspace in selected["workspaces"]:
            entry = registry_stats.get(workspace.get("position"))
            if entry is None:
                continue
            registry, mtime_ns = entry
            after = registry.lstat()
            if after.st_mtime_ns != mtime_ns:
                raise SourceInputInvalid(
                    "chats.json changed during preparation",
                )
            workspace["chats_mtime_ns"] = mtime_ns
        return result
    except MigrationDiskCapacityError:
        raise
    except (
        MigrationCapacityError,
        SourceInputInvalid,
        FileNotFoundError,
    ) as error:
        return error


def map_tenant_semantics(
    items,
    *,
    workers=4,
    io_workers=4,
    memory_bytes=512 * 1024 * 1024,
):
    """Bound tenant parsers globally; yield only detached count summaries."""
    if not 1 <= workers <= 32 or not 1 <= io_workers <= 32:
        raise ValueError("workers and io-workers must be between 1 and 32")
    if memory_bytes // workers <= 0:
        raise ValueError("memory budget is smaller than worker count")
    allowance = memory_bytes // workers
    return map_tenant_calls(
        items,
        lambda data: _tenant_semantic(
            data,
            lambda selected: _compact_tenant_inventory(selected, allowance),
        ),
        workers=workers,
        io_workers=io_workers,
    )


def _compact_tenant_inventory(data, allowance):
    from .inventory_parallel import _preflight_workspace
    from .inventory_v3 import (
        inventory_workspace,
        _inventory_shares,
        _preflight_share_budget,
    )

    summaries, references, blockers = [], [], []
    for index, workspace in enumerate(data["workspaces"]):
        if data.get("source_binding_storage") != "manifest-v1":
            if data.get("freshness_protocol"):
                _preflight_workspace(
                    workspace,
                    allowance,
                    require_readonly=True,
                )
            else:
                _preflight_workspace(workspace, allowance)
        result = inventory_workspace(data, index)
        parsed = result["workspaces"][0]
        summaries.append(
            {
                "sessions": range(len(parsed["sessions"])),
                "chats": range(len(parsed["chats"])),
            },
        )
        blockers.extend(result["blockers"])
        if data["shares"]:
            references.append(
                {
                    "scope": parsed["scope"],
                    "chats": [
                        {
                            "position": chat["position"],
                            "spec": {"id": chat["spec"]["id"]},
                        }
                        for chat in parsed["chats"]
                    ],
                },
            )
        del result, parsed
    if data.get("source_binding_storage") != "manifest-v1":
        _preflight_share_budget(data, allowance)
    for source in data["shares"]:
        report = {"workspaces": references, "blockers": [], "shares": []}
        _inventory_shares({**data, "shares": [source]}, report)
        blockers.extend(report["blockers"])
    return {"blockers": blockers, "workspaces": summaries}


def _verify_readonly_evidence(data):
    from .source_inputs import SourceInputInvalid

    for workspace in data["workspaces"]:
        for value in workspace.get("evidence_refs", []):
            path = Path(value)
            details = path.lstat()
            if (
                not path.is_file()
                or path.is_symlink()
                or details.st_mode & 0o222
            ):
                raise SourceInputInvalid(
                    "identity evidence must be a read-only regular file",
                )


def map_tenant_calls(items, function, *, workers=4, io_workers=4):
    """Ordered bounded synchronous calls retaining read-only guard context."""
    if not 1 <= workers <= 32 or not 1 <= io_workers <= 32:
        raise ValueError("workers and io-workers must be between 1 and 32")
    iterator = iter(items)
    pending = deque()
    with ThreadPoolExecutor(
        max_workers=min(workers, io_workers),
        thread_name_prefix="migration-discovery",
    ) as pool:
        try:
            for _ in range(min(workers, io_workers)):
                item = next(iterator, None)
                if item is None:
                    break
                pending.append(pool.submit(copy_context().run, function, item))
            while pending:
                yield pending.popleft().result()
                item = next(iterator, None)
                if item is not None:
                    pending.append(
                        pool.submit(copy_context().run, function, item),
                    )
        finally:
            for future in pending:
                future.cancel()


def _source_configs(service):
    from .discovery import _identity, _is_default_scope_encoding

    root = Path(service["config_root"])
    from .failure_scope import config_candidates

    candidates = config_candidates(root)
    for path in candidates:
        if path == root / "config.json":
            continue
        component = path.parent.relative_to(root).parts[0]
        if _is_default_scope_encoding(component):
            continue
        if (
            not path.parent.is_symlink()
            and not path.is_symlink()
            and not path.exists()
        ):
            continue
        try:
            tenant, source = _identity(path, service)
            WorkspaceScope(
                tenant,
                source,
                "",
                service_unit_id=service["service_unit_id"],
            )
        except (ValueError, TypeError, KeyError):
            continue
        yield path, tenant, source


def _configs(service):
    for path, tenant, _source in _source_configs(service):
        yield path, tenant


def _candidate_identity(service, path):
    """Return a candidate's explicit tenant/source identity, if available."""
    from .discovery import _identity, _is_default_scope_encoding

    try:
        relative = Path(path).relative_to(Path(service["source_root"]))
    except ValueError:
        return None
    if not relative.parts:
        return None
    if _is_default_scope_encoding(relative.parts[0]):
        return None
    config = Path(service["config_root"]) / relative.parts[0] / "config.json"
    try:
        return _identity(config, service)
    except (ValueError, TypeError, KeyError):
        return None


def _candidate_key(report, service, path):
    identity = _candidate_identity(service, path)
    if identity is None:
        return None
    key = (service["service_unit_id"], *identity)
    if report.get("source_isolation"):
        return key
    legacy_key = key[:2]
    return legacy_key


def _under_declared_input(path, services):
    return any(
        path == Path(service[key]) or path.is_relative_to(Path(service[key]))
        for service in services
        for key in ("source_root", "config_root")
    )


def _path(position, services):
    try:
        parts = json.loads(position)
    except (ValueError, TypeError):
        return Path(position) if isinstance(position, str) else None
    if isinstance(parts, list) and len(parts) == 3 and parts[0] == "workspace":
        service = next(
            (s for s in services if s["service_unit_id"] == parts[1]),
            None,
        )
        if service:
            return Path(service["source_root"]) / parts[2]
    return None


def _collect_config_tenants(report, tenants, paths, evidence):
    from .discovery import _overlaps

    services = report["services"]
    for service in services:
        name = service["service_unit_id"]
        for frozen in services:
            for key in ("source_root", "config_root", "snapshot_root"):
                if (
                    not report.get("in_place")
                    and frozen.get(key)
                    and _overlaps(
                        Path(service["original_root"]),
                        Path(frozen[key]),
                    )
                ):
                    raise ValueError(
                        "tenant isolation requires frozen inputs separate from runtime roots",
                    )
        for config, tenant, source in _source_configs(service):
            key = unit_key(
                report,
                {
                    "service_unit_id": name,
                    "tenant_id": tenant,
                    "source_id": source,
                },
            )
            tenants.setdefault(key, [])
            evidence.setdefault(key, []).append(str(config))
            paths.append((config, key))
            relative = config.parent.relative_to(service["config_root"])
            if relative.parts:
                paths.append((Path(service["source_root"]) / relative, key))


def isolate_discovery(
    report,
    shares,
    validator,
    *,
    semantic_inventory=True,
):
    """Preserve all blockers and quarantine every affected tenant before parsing."""
    services = report["services"]
    tenants, paths, positions = {}, [], {}
    evidence = {}
    _collect_config_tenants(report, tenants, paths, evidence)
    for item in report["workspaces"]:
        key = unit_key(report, item)
        tenants.setdefault(key, [])
        paths.append((Path(item["root"]), key))
        positions[item["position"]] = {key}
    for item in report["shares"]:
        key = unit_key(report, item)
        tenants.setdefault(key, [])
        positions[item["position"]] = {key}
    # A missing/ambiguous snapshot cannot establish service ownership. Block the
    # same trustworthy account in every declared service, never guess one owner.
    for item in shares:
        tenant = item.get("tenant_id")
        if not isinstance(tenant, str):
            continue
        if report.get("source_isolation"):
            matched = [
                s for s in report["shares"] if s["token"] == item.get("token")
            ]
            candidates = (
                {unit_key(report, s) for s in matched}
                if matched
                else {key for key in tenants if key[1] == tenant}
            )
            positions.setdefault(
                str(item.get("token", "share")),
                set(),
            ).update(candidates)
            continue
        matched = [
            s for s in report["shares"] if s["token"] == item.get("token")
        ]
        candidates = {
            (s["service_unit_id"], tenant) for s in (matched or services)
        }
        for key in candidates:
            tenants.setdefault(key, [])
        positions.setdefault(str(item.get("token", "share")), set()).update(
            candidates,
        )
    _attribute_blockers(report, services, tenants, paths, positions)
    keys = [key for key in sorted(tenants) if not tenants[key]]

    def select(key):
        return {
            **report,
            "blockers": [],
            "workspaces": [w for w in report["workspaces"] if belongs(w, key)],
            "shares": [s for s in report["shares"] if belongs(s, key)],
        }

    if semantic_inventory:
        mapper = getattr(validator, "map_tenants", None)
        selected = [select(key) for key in keys]
        results = (
            mapper(selected)
            if mapper is not None
            else (_tenant_semantic(item, validator) for item in selected)
        )
        for key, item, semantic in zip(keys, selected, results):
            if isinstance(semantic, Exception):
                blocker = {
                    "code": "tenant_input_invalid",
                    "position": json.dumps(key),
                    "detail": str(semantic),
                }
                tenants[key].append(blocker)
                report["blockers"].append(blocker)
                continue
            tenants[key].extend(semantic["blockers"])
            report["blockers"].extend(semantic["blockers"])
            for mapped, workspace in zip(
                item["workspaces"],
                semantic["workspaces"],
            ):
                mapped["counts"] = {
                    "sessions": len(workspace["sessions"]),
                    "chats": len(workspace["chats"]),
                }
                mapped["empty"] = not any(mapped["counts"].values())
    report["tenants"] = [
        {
            "service_unit_id": key[0],
            "tenant_id": key[1],
            **({"source_id": key[2]} if len(key) == 3 else {}),
            "state": "failed" if failures else "discovered",
            "blockers": deepcopy(failures),
            **(
                {"evidence_refs": evidence.get(key, [])}
                if report.get("in_place")
                else {}
            ),
        }
        for key, failures in sorted(tenants.items())
    ]
    _freeze_tenant_boundaries(
        report,
        freeze_identity_evidence=semantic_inventory,
    )
    report["status"] = "partial_success" if report["blockers"] else "success"


def _attribute_blockers(report, services, tenants, paths, positions):
    for blocker in report["blockers"]:
        position = blocker["position"]
        owners = positions.get(position, set())
        path = _path(position, services)
        if not owners and path is not None:
            matches = [
                (p, k) for p, k in paths if path == p or path.is_relative_to(p)
            ]
            # Longest verified directory wins; a root config must not swallow
            # a nested tenant's candidate.
            if matches:
                depth = max(len(p.parts) for p, _ in matches)
                owners = {k for p, k in matches if len(p.parts) == depth}
        if not owners and path is not None:
            for service in services:
                if not _under_declared_input(path, [service]):
                    continue
                owner = _candidate_key(report, service, path)
                if owner is not None:
                    tenants.setdefault(owner, [])
                    owners = {owner}
                else:
                    # An input under a declared root without a verified source
                    # owner is outside the migration set.
                    owners = set()
                break
            if not owners and _under_declared_input(path, services):
                continue
        if not owners:
            affected = {
                s["service_unit_id"]
                for s in services
                if position == s["service_unit_id"]
                or (
                    path is not None
                    and any(
                        path.is_relative_to(Path(s[k]))
                        for k in ("source_root", "config_root")
                    )
                )
            }
            owners = {k for k in tenants if not affected or k[0] in affected}
        for key in owners:
            tenants[key].append(blocker)


def _freeze_tenant_boundaries(report, *, freeze_identity_evidence=True):
    from .source_inputs import SourceInputInvalid
    from .spool import MigrationCapacityError

    if (
        report.get("in_place")
        and freeze_identity_evidence
        and not report.get("freshness_protocol")
    ):
        from .in_place_source import freeze_evidence

        for tenant in report["tenants"]:
            if tenant["state"] == "discovered":
                try:
                    tenant["in_place_evidence"] = freeze_evidence(tenant)
                except (
                    SourceInputInvalid,
                    MigrationCapacityError,
                    FileNotFoundError,
                ) as error:
                    blocker = {
                        "code": "tenant_input_invalid",
                        "position": json.dumps(
                            unit_key(report, tenant),
                        ),
                        "detail": str(error),
                    }
                    tenant["state"] = "failed"
                    tenant["blockers"].append(blocker)
                    report["blockers"].append(blocker)
