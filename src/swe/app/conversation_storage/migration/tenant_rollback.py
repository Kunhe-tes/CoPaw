# -*- coding: utf-8 -*-
"""Reviewed partial-cutover rollback planning and stopped-writer export."""

from dataclasses import dataclass
from pathlib import Path
import json

from ..errors import IntegrityError
from ..identity import WorkspaceScope
from .exporter import OldFormatTarget, _stamp
from .manifest import SourceBoundary
from .source_inputs import safe_input_entries
from .isolation import unit_key, belongs


@dataclass(frozen=True)
class TenantRollbackEvidence:
    boundary: SourceBoundary
    writers_stopped_ref: str
    io_drained_ref: str
    current_config_review_ref: str

    def __post_init__(self):
        if not isinstance(self.boundary, SourceBoundary) or not all(
            isinstance(value, str) and value.strip()
            for value in (
                self.writers_stopped_ref,
                self.io_drained_ref,
                self.current_config_review_ref,
            )
        ):
            raise ValueError(
                "rollback requires reviewed stop, drain and config evidence",
            )


def _directory(value):
    root = Path(value)
    if (
        not root.is_absolute()
        or root.resolve(strict=True) != root
        or not root.is_dir()
    ):
        raise IntegrityError(
            "rollback mapping requires canonical existing directories",
        )
    return root


def validate_current_config(mapping, services):
    """Validate an explicitly reviewed live-config mapping, never guess scope IDs.

    One mapping binds one tenant/source config and its complete Agent profiles.
    Trusted service/tenant/source IDs must come from the operator's reviewed
    registration, not from the filename or the profile's user-controlled values.
    """
    expected = {
        "service_unit_id",
        "tenant_id",
        "source_id",
        "config_path",
        "review_ref",
    }
    if (
        set(mapping) != expected
        or not isinstance(mapping["review_ref"], str)
        or not mapping["review_ref"].strip()
    ):
        raise ValueError(
            "current config mapping requires explicit reviewed identity",
        )
    service = next(
        (
            item
            for item in services
            if item["service_unit_id"] == mapping["service_unit_id"]
        ),
        None,
    )
    if service is None:
        raise IntegrityError("current config service is not declared")
    original = _directory(service["original_root"])
    config = Path(mapping["config_path"])
    if not config.is_absolute() or not config.is_relative_to(original):
        raise IntegrityError(
            "current config must be within original runtime root",
        )
    entries = safe_input_entries(
        original,
        [config.relative_to(original)],
        recursive=False,
    )
    if config not in entries or not config.is_file():
        raise IntegrityError("current config must be a regular file")
    profiles = (
        json.loads(config.read_bytes()).get("agents", {}).get("profiles")
    )
    if not isinstance(profiles, dict):
        raise IntegrityError("current config profiles must be a mapping")
    bindings = []
    for key, profile in profiles.items():
        if not isinstance(profile, dict) or profile.get("id") != key:
            raise IntegrityError("current profile and Agent identity differ")
        root = _directory(profile["workspace_dir"])
        if not root.is_relative_to(original):
            raise IntegrityError(
                "current workspace is outside original runtime root",
            )
        agent = root / "agent.json"
        safe_input_entries(root, ["agent.json"], recursive=False)
        if (
            not agent.is_file()
            or json.loads(agent.read_bytes()).get("id") != key
        ):
            raise IntegrityError("current workspace Agent evidence differs")
        scope = WorkspaceScope(
            mapping["tenant_id"],
            mapping["source_id"],
            key,
            service_unit_id=mapping["service_unit_id"],
        )
        bindings.append({"root": str(root), "scope": list(scope.values)})
    return bindings


def _scope_key(data, scope):
    return tuple(scope[:3] if data.get("source_isolation") else scope[:2])


async def _publication_states(database, manifest):
    source_mode = manifest.data.get("source_isolation", False)
    fields = ("service_unit_key", "tenant_key", "source_key")[
        : 3 if source_mode else 2
    ]
    table = (
        "swe_conversation_migration_sources"
        if source_mode
        else "swe_conversation_migration_tenants"
    )
    selected = (
        (*fields, "state", "evidence_text", "verification_text")
        if source_mode
        else (*fields, "state")
    )
    rows = await database.fetch_all(
        "SELECT "
        + ",".join(selected)
        + " FROM "
        + table
        + " WHERE migration_id=%s",
        (manifest.migration_id.encode(),),
    )
    states = {
        tuple(_text(row[key]) for key in fields): row["state"] for row in rows
    }
    if len(states) != len(rows):
        raise IntegrityError("rollback publication state is duplicated")
    if source_mode:
        for row in rows:
            _validate_source_state(manifest, row)
    return states


def _validate_source_state(manifest, row):
    from .authority import validate_source_verification
    from .source_state import SourceState

    key = tuple(
        _text(row[field])
        for field in ("service_unit_key", "tenant_key", "source_key")
    )
    data = manifest.data
    service = next(
        (s for s in data["services"] if s["service_unit_id"] == key[0]),
        None,
    )
    expected = {
        "service": service,
        "workspaces": [
            w for w in data.get("workspaces", []) if belongs(w, key)
        ],
        "shares": [s for s in data.get("shares", []) if belongs(s, key)],
    }
    try:
        if service is None or json.loads(row["evidence_text"]) != expected:
            raise ValueError("source frozen evidence differs")
        if row["state"] == "published":
            proof, _level = validate_source_verification(
                row["verification_text"],
            )
            if proof["migration_id"] != manifest.migration_id or set(
                proof["services"],
            ) != {key[0]}:
                raise ValueError("source publication job differs")
            SourceState._validate_evidence(row, *key, proof)
    except (ValueError, TypeError, KeyError) as error:
        raise IntegrityError(
            "rollback source frozen or publication evidence differs",
        ) from error


def _frozen_configs(data, service):
    from .tenant_discovery import _source_configs

    for config, tenant, source in _source_configs(service):
        yield config, unit_key(
            data,
            {
                "service_unit_id": service["service_unit_id"],
                "tenant_id": tenant,
                "source_id": source,
            },
        )


async def plan_tenant_rollback(
    database,
    manifest,
    destination,
    target,
    evidence,
    *,
    current_configs,
):
    """Inspect reviewed inputs only; return explicit unresolved safety gates.

    The planner does not create destination, mutate SQL, copy content or grant
    permission to start the old image. Even a complete plan is not rollback-ready.
    """
    if not isinstance(target, OldFormatTarget) or not isinstance(
        evidence,
        TenantRollbackEvidence,
    ):
        raise ValueError(
            "rollback requires explicit target and reviewed evidence",
        )
    if target.image_digest != evidence.boundary.old_image_digest:
        raise IntegrityError(
            "rollback target differs from stopped boundary image",
        )
    data = manifest.data
    if data.get("tenant_isolation") is not True:
        raise ValueError("tenant rollback planner requires partial migration")
    destination = Path(destination)
    if not destination.is_absolute() or destination.resolve() != destination:
        raise IntegrityError(
            "rollback destination must be canonical and absolute",
        )
    if destination.exists() and (
        not destination.is_dir() or any(destination.iterdir())
    ):
        raise IntegrityError("rollback destination must be empty")
    for service in data["services"]:
        for key in (
            "source_root",
            "config_root",
            "snapshot_root",
            "nas_root",
            "original_root",
        ):
            if service.get(key):
                root = Path(service[key]).resolve()
                if (
                    destination == root
                    or destination.is_relative_to(root)
                    or root.is_relative_to(destination)
                ):
                    raise IntegrityError(
                        "rollback destination overlaps protected roots",
                    )
    bindings = []
    for mapping in current_configs:
        bindings.extend(validate_current_config(mapping, data["services"]))
    scopes = [tuple(item["scope"]) for item in bindings]
    roots = [item["root"] for item in bindings]
    if len(set(scopes)) != len(scopes) or len(set(roots)) != len(roots):
        raise IntegrityError(
            "current config scope or workspace mapping is duplicated",
        )
    states = await _publication_states(database, manifest)
    registered = {unit_key(data, item) for item in data["tenants"]}
    blockers = []
    if set(states) != registered:
        blockers.append("tenant_state_coverage_differs")
    mapped = {_scope_key(data, scope) for scope in scopes}
    for key, state in states.items():
        if state == "published" and key not in mapped:
            blockers.append("published_tenant_current_config_missing")
    if any(key not in registered for key in mapped):
        blockers.append("unregistered_current_config_tenant")
    blockers.extend(
        (
            "current_sql_scope_coverage_not_verified",
            "new_scope_backup_authority_not_verified",
            "unpublished_frozen_source_closure_not_verified",
            "mixed_authority_share_merge_not_verified",
            "whole_service_export_not_verified",
            "pinned_old_image_read_and_continue_write_not_verified",
        ),
    )
    return {
        "version": 1,
        "migration_id": manifest.migration_id,
        "operation": "tenant_rollback_preflight",
        "passed": False,
        "rollback_ready": False,
        "image_verified": False,
        "mutated": False,
        "current_workspace_count": len(bindings),
        "published_tenants": sum(
            state == "published" for state in states.values()
        ),
        "unresolved_blockers": sorted(set(blockers)),
    }


@dataclass(frozen=True)
class RollbackBackupAuthorization:
    """Administrative-only exact binding; ordinary backups cannot infer this."""

    evidence: TenantRollbackEvidence
    manifest: object
    current_configs: tuple
    scope: WorkspaceScope
    workspace_root: str


async def validate_backup_authorization(authorization, database, scope):
    from ..tenant_admission import partial_admission

    if (
        not isinstance(authorization, RollbackBackupAuthorization)
        or authorization.scope != scope
    ):
        raise IntegrityError(
            "rollback backup requires exact reviewed scope authority",
        )
    if not isinstance(authorization.evidence, TenantRollbackEvidence):
        raise IntegrityError("rollback backup lacks stop and drain evidence")
    bindings = []
    for mapping in authorization.current_configs:
        bindings.extend(
            validate_current_config(
                mapping,
                authorization.manifest.data["services"],
            ),
        )
    if {
        "root": authorization.workspace_root,
        "scope": list(scope.values),
    } not in bindings:
        raise IntegrityError(
            "rollback backup scope lacks current workspace evidence",
        )
    admission = await partial_admission(database, scope)
    if (
        admission is None
        or admission.document["migration_id"]
        != authorization.manifest.migration_id
    ):
        raise IntegrityError("rollback backup job authority differs")
    # Published state is mandatory, but the current Agent scope may be newer than
    # the immutable migration receipt. Only the reviewed mapping permits that.
    await admission.require(scope.tenant_id, scope.source_id)


def _copy_exact(source, destination):
    import hashlib
    import stat

    source = Path(source)
    if source.is_symlink() or not stat.S_ISREG(source.lstat().st_mode):
        raise IntegrityError("rollback copy requires regular source files")
    raw = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_symlink() or destination.read_bytes() != raw:
            raise IntegrityError("rollback output collision")
    else:
        with destination.open("xb") as output:
            output.write(raw)
    if destination.read_bytes() != raw:
        raise IntegrityError("rollback copied content differs")
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _copy_workspace_inputs(workspace, destination):
    from .source_inputs import session_input_roots

    root = Path(workspace["root"])
    entrances = session_input_roots(
        root,
        [item["path"] for item in workspace.get("session_paths", [])],
        registry_path=workspace.get("registry_path", "chats.json"),
        sessions_dir=workspace.get("sessions_dir", "sessions"),
        dialog_dir=workspace.get("dialog_dir", "dialog"),
    )
    entries = safe_input_entries(root, entrances)
    if any(path.stat().st_mode & 0o222 for path in entries):
        raise IntegrityError(
            "unpublished rollback source must remain read-only",
        )
    entries.extend(safe_input_entries(root, ["agent.json"], recursive=False))
    verified = []
    for path in dict.fromkeys(entries):
        relative = path.relative_to(root)
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            verified.append(
                {"path": str(relative), **_copy_exact(path, target)},
            )
    return verified


def _rollback_input_digest(data, published, current_configs):
    import hashlib
    from .source_inputs import session_input_roots

    paths = set()
    for workspace in data["workspaces"]:
        if unit_key(data, workspace) in published:
            continue
        root = Path(workspace["root"])
        entrances = session_input_roots(
            root,
            [item["path"] for item in workspace.get("session_paths", [])],
            registry_path=workspace.get("registry_path", "chats.json"),
            sessions_dir=workspace.get("sessions_dir", "sessions"),
            dialog_dir=workspace.get("dialog_dir", "dialog"),
        )
        paths.update(safe_input_entries(root, entrances))
        paths.update(safe_input_entries(root, ["agent.json"], recursive=False))
    for service in data["services"]:
        for config, key in _frozen_configs(data, service):
            if key not in published:
                paths.update(
                    safe_input_entries(
                        Path(service["config_root"]),
                        [config.relative_to(service["config_root"])],
                        recursive=False,
                    ),
                )
    shares = (
        data["shares"]
        if data.get("source_isolation")
        else data.get("source_shares", data.get("shares", []))
    )
    for row in shares:
        candidates = [
            service
            for service in data["services"]
            if (
                not data.get("source_isolation")
                or service["service_unit_id"] == row["service_unit_id"]
            )
            and unit_key(
                data,
                {**row, "service_unit_id": service["service_unit_id"]},
            )
            not in published
            and service.get("snapshot_root")
        ]
        for service in candidates:
            root = Path(service["snapshot_root"])
            path = root / row["snapshot_key"]
            if path.exists():
                paths.update(
                    safe_input_entries(
                        root,
                        [row["snapshot_key"]],
                        recursive=False,
                    ),
                )
    for mapping in current_configs:
        paths.add(Path(mapping["config_path"]))
        for binding in validate_current_config(mapping, data["services"]):
            paths.add(Path(binding["root"]) / "agent.json")
    result = []
    for path in sorted(paths):
        if path.is_file():
            result.append(
                (
                    str(path),
                    path.stat().st_mode,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                ),
            )
        else:
            result.append((str(path), path.stat().st_mode, "directory"))
    return result


def _text(value):
    return value.decode() if isinstance(value, bytes) else value


def _share_owner(data, row, frozen_owners):
    key = _text(row.get("service_unit_key")), row["tenant_id"]
    if not data.get("source_isolation"):
        return key
    source = _text(row.get("source_key"))
    if row.get("scope_kind") == "legacy_share":
        owner = frozen_owners.get(row["token"])
        if source != "" or owner is None or owner[:2] != key:
            raise IntegrityError("legacy share source ownership is unproven")
        return owner
    return (*key, source)


def _select_share_records(context, actual):
    from .discovery import SHARE_FIELDS

    owners = {}
    for share in context.data["shares"]:
        token = share["token"]
        owner = unit_key(context.data, share)
        if token in owners:
            raise IntegrityError(
                "frozen share token service ownership is ambiguous",
            )
        owners[token] = owner
    frozen = {
        share["token"]: share
        for share in context.data.get("source_shares", context.data["shares"])
    }
    actual_owners = {
        row["token"]: _share_owner(context.data, row, owners) for row in actual
    }
    if len(actual_owners) != len(actual):
        raise IntegrityError("SQL share tokens are duplicated")
    if any(
        owner in context.published and actual_owners.get(token) != owner
        for token, owner in owners.items()
    ):
        raise IntegrityError(
            "published frozen share token is missing or has different ownership",
        )
    merged = {service: {} for service in context.service_roots}
    for row in actual:
        service = _text(row.get("service_unit_key"))
        key = actual_owners[row["token"]]
        if key in context.published:
            if row["token"] in owners and owners[row["token"]] != key:
                raise IntegrityError(
                    "published share service ownership differs",
                )
            merged[service][row["token"]] = {
                field: row[field] for field in SHARE_FIELDS
            }
            continue
        owner = owners.get(row["token"])
        source = frozen.get(row["token"])
        if owner is None or source is None:
            raise IntegrityError("SQL share has unexplained service ownership")
        if owner in context.published or owner not in context.registered:
            raise IntegrityError("SQL share has unexplained service ownership")
        if (
            service not in (None, owner[0])
            or row["tenant_id"] != owner[1]
            or (len(owner) == 3 and key[2] not in (None, owner[2]))
        ):
            raise IntegrityError("SQL share has unexplained service ownership")
        if any(
            (
                _stamp(row[field]) != _stamp(source[field])
                if field.endswith("_at")
                else row[field] != source[field]
            )
            for field in SHARE_FIELDS
        ):
            raise IntegrityError(
                "unpublished SQL share differs from frozen authority",
            )
    return owners, merged


async def _merge_shares(context):
    from ..backup import _atomic_json
    from .discovery import SHARE_FIELDS

    if context.data.get("source_isolation"):
        query = (
            "SELECT "
            + ",".join("s." + field for field in SHARE_FIELDS)
            + ",s.service_unit_key,p.source_key,p.scope_kind FROM swe_chat_shares s "
            + "LEFT JOIN swe_conversation_publications p ON p.id=s.publication_id "
            + "AND p.service_unit_key=s.service_unit_key AND p.tenant_key=s.tenant_id"
            + " AND p.state='committed' AND p.gc_state='live'"
        )
    else:
        query = (
            "SELECT "
            + ",".join((*SHARE_FIELDS, "service_unit_key"))
            + " FROM swe_chat_shares"
        )
    actual = await context.database.fetch_all(query)

    owners, merged = _select_share_records(context, actual)
    for row in context.data.get("source_shares", context.data["shares"]):
        owner = owners.get(row["token"])
        if owner is None or owner not in context.registered:
            raise IntegrityError(
                "frozen share has no unique service ownership",
            )
        if owner in context.published:
            continue
        service = owner[0]
        merged[service][row["token"]] = {
            field: row[field] for field in SHARE_FIELDS
        }
        declared = next(
            (
                item
                for item in context.data["services"]
                if item["service_unit_id"] == service
            )
        )
        source = Path(declared["snapshot_root"]) / row["snapshot_key"]
        safe_input_entries(
            Path(declared["snapshot_root"]),
            [row["snapshot_key"]],
            recursive=False,
        )
        _copy_exact(
            source,
            context.service_roots[service] / row["snapshot_key"],
        )
    for service, shares in merged.items():
        for binding in context.by_scope.values():
            scope = binding["scope"]
            if (
                scope[0] != service
                or _scope_key(context.data, scope) not in context.published
            ):
                continue
            declared = next(
                (
                    item
                    for item in context.data["services"]
                    if item["service_unit_id"] == service
                )
            )
            root = context.service_roots[service] / Path(
                binding["root"],
            ).relative_to(declared["original_root"])
            for row in shares.values():
                candidate = root / row["snapshot_key"]
                if candidate.is_file():
                    _copy_exact(
                        candidate,
                        context.service_roots[service] / row["snapshot_key"],
                    )
        for row in shares.values():
            if not (
                context.service_roots[service] / row["snapshot_key"]
            ).is_file():
                raise IntegrityError("merged share body is absent")
        _atomic_json(
            context.service_roots[service] / "shares.json",
            [
                {
                    key: _stamp(value) if key.endswith("_at") else value
                    for key, value in row.items()
                }
                for row in shares.values()
            ],
        )


def _copy_unpublished(context):
    copied = []

    frozen_configs = set()
    for service in context.data["services"]:
        for config, key in _frozen_configs(context.data, service):
            if key in context.registered and key not in context.published:
                if not config.is_relative_to(service["source_root"]):
                    raise IntegrityError(
                        "frozen config needs explicit output mapping",
                    )
                safe_input_entries(
                    Path(service["source_root"]),
                    [config.relative_to(service["source_root"])],
                    recursive=False,
                )
                if config.stat().st_mode & 146:
                    raise IntegrityError(
                        "frozen rollback config must remain read-only",
                    )
                _copy_exact(
                    config,
                    context.service_roots[key[0]]
                    / config.relative_to(service["source_root"]),
                )
                frozen_configs.add(key)
    if any(
        (
            key not in frozen_configs
            for key in context.registered - context.published
        )
    ):
        raise IntegrityError("unpublished tenant has no trusted frozen config")
    for workspace in context.data["workspaces"]:
        key = unit_key(context.data, workspace)
        if key in context.published:
            continue
        service = next(
            (
                item
                for item in context.data["services"]
                if item["service_unit_id"] == key[0]
            )
        )
        output = context.service_roots[key[0]] / Path(
            workspace["root"],
        ).relative_to(service["source_root"])
        copied.extend(_copy_workspace_inputs(workspace, output))
        for ref in workspace.get("evidence_refs", []):
            path = Path(ref)
            if not path.is_relative_to(service["source_root"]):
                raise IntegrityError(
                    "frozen config evidence outside source root needs explicit mapping",
                )
            safe_input_entries(
                Path(service["source_root"]),
                [path.relative_to(service["source_root"])],
                recursive=False,
            )
            _copy_exact(
                path,
                context.service_roots[key[0]]
                / path.relative_to(service["source_root"]),
            )
    return copied


async def _export_published(context):
    import asyncio
    import hashlib
    from ..backup import ConversationBackup
    from ..bundle import BundleStore
    from .exporter import ConversationExporter

    reports = []
    for scope_values, binding in context.by_scope.items():
        if _scope_key(context.data, scope_values) not in context.published:
            continue
        scope = WorkspaceScope.from_values(scope_values)
        service = next(
            (
                item
                for item in context.data["services"]
                if item["service_unit_id"] == scope.service_unit_id
            )
        )
        relative = Path(binding["root"]).relative_to(service["original_root"])
        output = context.service_roots[scope.service_unit_id] / relative
        backup = (
            context.destination
            / "backups"
            / hashlib.sha256(json.dumps(scope_values).encode()).hexdigest()
        )
        authorization = RollbackBackupAuthorization(
            context.evidence,
            context.manifest,
            tuple(context.current_configs),
            scope,
            binding["root"],
        )
        captured = await ConversationBackup(
            context.database,
            BundleStore(service["nas_root"]),
            scope,
        ).capture(backup, rollback_authorization=authorization)
        if not captured.get("content_verified"):
            raise IntegrityError("rollback backup content verification failed")
        report = await asyncio.to_thread(
            ConversationExporter(
                backup,
                context.target,
                service_unit_id=scope.service_unit_id,
            ).export,
            output,
        )
        if not report.get("passed"):
            raise IntegrityError(
                "rollback workspace export verification failed",
            )
        reports.append(report)
        _copy_exact(
            Path(binding["root"]) / "agent.json",
            output / "agent.json",
        )
    return reports


async def _select_authorities(context):
    attributed = [
        blocker
        for tenant in context.data["tenants"]
        for blocker in tenant.get("blockers", [])
    ]
    if any(
        (
            blocker not in attributed
            for blocker in context.data.get("blockers", [])
        )
    ):
        raise IntegrityError("unassigned discovery blocker prevents rollback")
    if context.data.get("unassigned_blockers") or context.data.get(
        "service_blockers",
    ):
        raise IntegrityError(
            "unassigned source evidence prevents complete rollback",
        )
    states = await _publication_states(context.database, context.manifest)
    registered = {
        unit_key(context.data, item) for item in context.data["tenants"]
    }
    if set(states) != registered:
        raise IntegrityError("rollback tenant coverage differs")
    if any(
        (item.get("state") == "failed" for item in context.data["tenants"])
    ):
        raise IntegrityError(
            "failed discovery tenant has unproven source closure",
        )
    bindings = []
    for mapping in context.current_configs:
        bindings.extend(
            validate_current_config(mapping, context.data["services"]),
        )
    by_scope = {tuple(item["scope"]): item for item in bindings}
    if any(
        _scope_key(context.data, scope) not in registered for scope in by_scope
    ):
        raise IntegrityError(
            "current config publication unit is not registered",
        )
    published = {key for key, state in states.items() if state == "published"}
    sql_scopes = set()
    for table in ("sessions", "chats", "publications"):
        for row in await context.database.fetch_all(
            (
                "SELECT DISTINCT service_unit_key,tenant_key,source_key,agent_key,scope_kind FROM swe_conversation_"
                + table
                if table == "publications"
                else "SELECT DISTINCT service_unit_key,tenant_key,source_key,agent_key FROM swe_conversation_"
                + table
            ),
        ):
            scope = tuple(
                (
                    _text(row[key])
                    for key in (
                        "service_unit_key",
                        "tenant_key",
                        "source_key",
                        "agent_key",
                    )
                )
            )
            if (
                _scope_key(context.data, scope) in published
                and row.get("scope_kind", "workspace") == "workspace"
            ):
                sql_scopes.add(scope)
    if not sql_scopes.issubset(by_scope):
        raise IntegrityError(
            "published SQL scope lacks reviewed current config",
        )
    if any(
        (
            key not in {_scope_key(context.data, scope) for scope in by_scope}
            for key in published
        )
    ):
        raise IntegrityError("published tenant lacks current config")
    return (registered, by_scope, published)


async def compose_tenant_rollback(
    database,
    manifest,
    destination,
    target,
    evidence,
    *,
    current_configs,
    image_verifier=None,
):
    """Produce a reviewable staged export; only a real whole-image check grants readiness.

    Caller must actually stop all writers, GC and migration IO before invoking.
    Evidence is an explicit administrative attestation, not a stop mechanism.
    """
    import asyncio
    import hashlib
    from types import SimpleNamespace
    from ..backup import _atomic_json, _new_directory

    await plan_tenant_rollback(
        database,
        manifest,
        destination,
        target,
        evidence,
        current_configs=current_configs,
    )
    data = manifest.data
    context = SimpleNamespace(
        data=data,
        database=database,
        manifest=manifest,
        current_configs=current_configs,
        evidence=evidence,
        target=target,
    )

    registered, by_scope, published = await _select_authorities(context)
    context.registered, context.by_scope, context.published = (
        registered,
        by_scope,
        published,
    )
    source_before = _rollback_input_digest(data, published, current_configs)
    destination = _new_directory(destination)
    service_roots = {}
    for service in data["services"]:
        name = hashlib.sha256(service["service_unit_id"].encode()).hexdigest()
        service_roots[service["service_unit_id"]] = (
            destination / "services" / name
        )
        service_roots[service["service_unit_id"]].mkdir(parents=True)

    context.destination, context.service_roots = destination, service_roots
    reports = await _export_published(context)
    for mapping in current_configs:
        key = unit_key(data, mapping)
        if key in published:
            service = next(
                item
                for item in data["services"]
                if item["service_unit_id"] == key[0]
            )
            _copy_exact(
                Path(mapping["config_path"]),
                service_roots[key[0]]
                / Path(mapping["config_path"]).relative_to(
                    service["original_root"],
                ),
            )

    copied = _copy_unpublished(context)

    await _merge_shares(context)
    if source_before != _rollback_input_digest(
        data,
        published,
        current_configs,
    ):
        raise IntegrityError(
            "rollback source or reviewed current config changed during export",
        )
    image_evidence = []
    if image_verifier is not None:
        for service, root in service_roots.items():
            verified = await asyncio.to_thread(
                image_verifier,
                target.image_digest,
                root,
            )
            if (
                not isinstance(verified, dict)
                or verified.get("image_digest") != target.image_digest
                or not verified.get("passed")
                or not verified.get("read_and_continue_write")
            ):
                raise IntegrityError(
                    "whole-service pinned image verification failed",
                )
            image_evidence.append(verified)
    result = {
        "version": 1,
        "migration_id": manifest.migration_id,
        "passed": True,
        "content_verified": True,
        "rollback_ready": bool(image_verifier),
        "image_verified": bool(image_verifier),
        "image_evidence": image_evidence,
        "workspace_reports": reports,
        "copied_files": copied,
        "services": {key: str(value) for key, value in service_roots.items()},
        "limitations": (
            []
            if image_verifier
            else ["pinned_old_image_read_and_continue_write_not_verified"]
        ),
    }
    _atomic_json(destination / "rollback-report.json", result)
    return result
