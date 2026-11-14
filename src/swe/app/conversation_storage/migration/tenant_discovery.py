# -*- coding: utf-8 -*-
"""Conservative failure attribution for independently published tenants."""

from copy import deepcopy
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import json
from pathlib import Path

from ..identity import WorkspaceScope


def _tenant_semantic(selected, validator):
    from .inventory_v3 import inventory_discovery
    from .source_inputs import SourceInputInvalid
    from .spool import MigrationCapacityError, MigrationDiskCapacityError

    try:
        if selected.get("in_place"):
            from .in_place_source import freeze_evidence

            for item in selected["workspaces"]:
                item["in_place_evidence"] = freeze_evidence(item)
        return (validator or inventory_discovery)(selected)
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
    _preflight_share_budget(data, allowance)
    for source in data["shares"]:
        report = {"workspaces": references, "blockers": [], "shares": []}
        _inventory_shares({**data, "shares": [source]}, report)
        blockers.extend(report["blockers"])
    return {"blockers": blockers, "workspaces": summaries}


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


def _configs(service):
    from .discovery import _identity

    root = Path(service["config_root"])
    from .failure_scope import config_candidates

    candidates = config_candidates(root)
    for path in candidates:
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
        yield path, tenant


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
        for config, tenant in _configs(service):
            key = (name, tenant)
            tenants.setdefault(key, [])
            evidence.setdefault(key, []).append(str(config))
            paths.append((config, key))
            relative = config.parent.relative_to(service["config_root"])
            if relative.parts:
                paths.append((Path(service["source_root"]) / relative, key))


def isolate_discovery(report, shares, validator):
    """Preserve all blockers and quarantine every affected tenant before parsing."""
    services = report["services"]
    tenants, paths, positions = {}, [], {}
    evidence = {}
    _collect_config_tenants(report, tenants, paths, evidence)
    for item in report["workspaces"]:
        key = (item["service_unit_id"], item["tenant_id"])
        tenants.setdefault(key, [])
        paths.append((Path(item["root"]), key))
        positions[item["position"]] = {key}
    for item in report["shares"]:
        key = (item["service_unit_id"], item["tenant_id"])
        tenants.setdefault(key, [])
        positions[item["position"]] = {key}
    # A missing/ambiguous snapshot cannot establish service ownership. Block the
    # same trustworthy account in every declared service, never guess one owner.
    for item in shares:
        tenant = item.get("tenant_id")
        if not isinstance(tenant, str):
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
            "workspaces": [
                w
                for w in report["workspaces"]
                if (w["service_unit_id"], w["tenant_id"]) == key
            ],
            "shares": [
                s
                for s in report["shares"]
                if (s["service_unit_id"], s["tenant_id"]) == key
            ],
        }

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
    _freeze_tenant_boundaries(report)
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


def _freeze_tenant_boundaries(report):
    from .source_inputs import SourceInputInvalid
    from .spool import MigrationCapacityError

    if report.get("in_place"):
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
                            (tenant["service_unit_id"], tenant["tenant_id"]),
                        ),
                        "detail": str(error),
                    }
                    tenant["state"] = "failed"
                    tenant["blockers"].append(blocker)
                    report["blockers"].append(blocker)
    if report.get("in_place"):
        from ..in_place_admission import tenant_write_boundaries
        from ..errors import IntegrityError

        for tenant in report["tenants"]:
            key = tenant["service_unit_id"], tenant["tenant_id"]
            try:
                tenant_write_boundaries(report, tenant=key)
            except IntegrityError as error:
                blocker = {
                    "code": "tenant_boundary_invalid",
                    "position": json.dumps(key),
                    "detail": str(error),
                }
                tenant["state"] = "failed"
                tenant["blockers"].append(blocker)
                report["blockers"].append(blocker)
