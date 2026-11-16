# -*- coding: utf-8 -*-
"""Frozen discovery manifest; SQL, never this file, assigns import identities."""

from pathlib import Path
import re
import time
from uuid import UUID

from ..identity import WorkspaceScope, service_unit_bytes
from .isolation import unit_key
from .disk_manifest import DiskSet, load_disk_manifest
from .manifest import (
    MigrationManifest,
    SourceBoundary,
    KINDS,
    TRANSITIONS,
    migration_workflow,
)


class V3Manifest(MigrationManifest):
    """Retain the durable manifest API without a local integer allocator."""

    @classmethod
    def load(cls, path):
        return cls(path, load_disk_manifest(path))

    def _validate(self):
        if self.data.get("version") != 3:
            raise ValueError("unsupported direct migration manifest version")
        if migration_workflow(self.data) != "direct":
            raise ValueError("direct manifest requires direct workflow")
        if str(UUID(self.migration_id)) != self.migration_id:
            raise ValueError("invalid migration identity")
        SourceBoundary(**self.data["source_boundary"])
        services = self.data.get("services")
        if not isinstance(services, list) or not services:
            raise ValueError("direct manifest requires nonempty services")
        names = [item["service_unit_id"] for item in services]
        if not names or len(set(names)) != len(names):
            raise ValueError("unique explicit migration services are required")
        for name in names:
            service_unit_bytes(name)
        self._validate_modes(services)
        tenant_scopes = set()
        if self.data.get("tenant_isolation"):
            tenants = self.data.get("tenants")
            if not isinstance(tenants, list):
                raise ValueError("tenant isolation requires frozen tenants")
            for tenant in tenants:
                scope = WorkspaceScope(
                    tenant["tenant_id"],
                    (
                        tenant["source_id"]
                        if self.data.get("source_isolation")
                        else ""
                    ),
                    "",
                    service_unit_id=tenant["service_unit_id"],
                )
                key = unit_key(self.data, tenant)
                if key in tenant_scopes or scope.service_unit_id not in names:
                    raise ValueError("duplicate or undeclared frozen tenant")
                tenant_scopes.add(key)
        self._validate_in_place_evidence()
        for item in self.data["workspaces"]:
            if (
                self.data.get("tenant_isolation")
                and unit_key(self.data, item) not in tenant_scopes
            ):
                raise ValueError("workspace tenant is not declared")
            if item["service_unit_id"] not in names:
                raise ValueError("workspace service is not declared")
            WorkspaceScope(
                item["tenant_id"],
                item["source_id"],
                item["agent_id"],
                service_unit_id=item["service_unit_id"],
            )
        if self.data.get("source_isolation"):
            for share in self.data["shares"]:
                if unit_key(self.data, share) not in tenant_scopes:
                    raise ValueError("share source is not declared")
        for kind, assignments in self.data["assignments"].items():
            if kind not in KINDS:
                raise ValueError("unknown assignment kind")
            identities = DiskSet()
            for source, assignment in assignments.items():
                self._validate_assignment(
                    kind,
                    source,
                    assignment,
                    identities,
                )
        if any(
            value not in TRANSITIONS for value in self.data["batches"].values()
        ):
            raise ValueError("invalid batch state")
        timestamps = self.data.get("tenant_sync_started_at_ns", {})
        if not isinstance(timestamps, dict) or any(
            not isinstance(key, str) or type(value) is not int or value <= 0
            for key, value in timestamps.items()
        ):
            raise ValueError("invalid tenant source mtime cutoff")
        if not isinstance(self.data.get("source_change_blockers", []), list):
            raise ValueError("invalid source change blocker journal")
        if self.data.get("target") is not None:
            self._validate_target(self.data["target"])

    def _validate_modes(self, services):
        if (
            "tenant_isolation" in self.data
            and type(self.data["tenant_isolation"]) is not bool
        ):
            raise ValueError("tenant isolation must be an explicit boolean")
        if "in_place" in self.data and (
            type(self.data["in_place"]) is not bool
            or not self.data.get("tenant_isolation")
        ):
            raise ValueError(
                "in-place mode requires explicit tenant isolation",
            )
        if self.data.get("source_isolation") is not None and (
            self.data["source_isolation"] is not True
            or not self.data.get("tenant_isolation")
        ):
            raise ValueError("invalid source isolation mode")
        if self.data.get("in_place"):
            for service in services:
                roots = {
                    service.get(key)
                    for key in (
                        "source_root",
                        "config_root",
                        "snapshot_root",
                        "original_root",
                    )
                }
                if len(roots) != 1 or None in roots:
                    raise ValueError("in-place roots must be identical")

    def _validate_in_place_evidence(self):
        if self.data.get("in_place"):
            failed = {
                unit_key(self.data, item)
                for item in self.data["tenants"]
                if item["state"] == "failed"
            }
            for item in [*self.data["workspaces"], *self.data["tenants"]]:
                if unit_key(self.data, item) in failed:
                    continue
                hashes = item.get("in_place_evidence")
                if (
                    not isinstance(hashes, dict)
                    or set(hashes) != set(item.get("evidence_refs", []))
                    or any(
                        not isinstance(value, str)
                        or not re.fullmatch(r"[a-f0-9]{64}", value)
                        for value in hashes.values()
                    )
                ):
                    raise ValueError(
                        "in-place frozen identity evidence is missing or invalid",
                    )

    def _validate_target(self, target):
        expected = {"schema", "nas_roots", "migration_id"}
        if (
            set(target) != expected
            or target["migration_id"] != self.migration_id
        ):
            raise ValueError("invalid direct migration target binding")
        schema = self.data["offline"]["application_schema"]
        if (
            not re.fullmatch(r"[a-zA-Z0-9_]{1,64}", schema)
            or target["schema"] != schema
        ):
            raise ValueError(
                "direct migration must select the application schema",
            )
        roots = {
            item["service_unit_id"]: item["nas_root"]
            for item in self.data["services"]
        }
        if target["nas_roots"] != roots:
            raise ValueError("direct migration service NAS binding changed")
        for value in roots.values():
            root = Path(value)
            if not root.is_absolute() or str(root.resolve()) != value:
                raise ValueError("invalid direct NAS root")

    def allocate(self, kind, source_position):
        try:
            return dict(self.data["assignments"][kind][source_position])
        except KeyError:
            raise ValueError(
                "direct migration IDs must be allocated by the SQL journal",
            ) from None

    def begin_tenant_sync(self, service_unit_id, tenant_id, source_id=None):
        from .freshness import tenant_key

        scope = (service_unit_id, tenant_id)
        if self.data.get("source_isolation"):
            if source_id is None:
                raise ValueError(
                    "source synchronization requires source identity",
                )
            scope += (source_id,)
        key = tenant_key(*scope)
        return self.begin_tenant_syncs([scope])[key]

    def begin_tenant_syncs(self, tenants):
        """Fix all tenant cutoffs in one durable manifest update before import."""
        from .freshness import tenant_key

        keys = [tenant_key(*scope) for scope in sorted(set(tenants))]
        with self._lock():
            self._refresh()
            timestamps = self.data.setdefault("tenant_sync_started_at_ns", {})
            missing = [key for key in keys if key not in timestamps]
            if missing:
                started_at_ns = time.time_ns()
                timestamps.update({key: started_at_ns for key in missing})
                self._persist()
            return {key: timestamps[key] for key in keys}

    def record_source_change(self, blocker):
        with self._lock():
            self._refresh()
            values = self.data.setdefault("source_change_blockers", [])
            if blocker not in values:
                values.append(blocker)
                self._persist()
            return list(values)

    def _refresh(self):
        current = self.load(self.path)
        for key in (
            "services",
            "fingerprints",
            "shares",
            "discovery_version",
            "tenant_isolation",
            "source_isolation",
            "in_place",
            "tenants",
            "source_shares",
            "declared_services",
            "tenant_review_revision",
        ):
            if current.data.get(key) != self.data.get(key):
                raise ValueError("frozen source discovery binding changed")
        current_timestamps = current.data.get("tenant_sync_started_at_ns", {})
        if any(
            current_timestamps.get(key) != value
            for key, value in self.data.get(
                "tenant_sync_started_at_ns",
                {},
            ).items()
        ):
            raise ValueError("tenant source mtime cutoff changed")
        super()._refresh(current=current)
