# -*- coding: utf-8 -*-
"""Audited zero-data tenant evidence revision under the schema migration lock.

Callers must hold the existing schema named lock for both public operations.
A pending revision is retained across every uncertain SQL/file outcome.
"""

import asyncio
from hashlib import sha256
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from .discovery import discover_services
from .disk_manifest import DiskMap, iter_json
from .journal import BUSINESS_TABLES, JOBS, ENTRIES, MigrationJournal
from .tenant_state import TenantState, _json
from .v3_manifest import V3Manifest
from .isolation import state_store
from contextvars import ContextVar
from contextlib import contextmanager

_SOURCE_MODE = ContextVar("source_review_mode", default=False)
_REVIEW_TICKETS = ContextVar("review_ticket_ownership", default=None)


@contextmanager
def _ticket_analysis():
    # Reuse only during read-only retention. The final transaction rereads SQL.
    analysis = {"task": asyncio.current_task()}
    token = _REVIEW_TICKETS.set(analysis)
    try:
        yield
    finally:
        _REVIEW_TICKETS.reset(token)
        if "owners" in analysis:
            analysis["owners"].close()


def _states(db, manifest):
    if not manifest.data.get("source_isolation"):
        return TenantState(db, manifest.migration_id)
    return state_store(db, manifest)


_FIELDS = (
    "services",
    "declared_services",
    "workspaces",
    "shares",
    "source_shares",
    "tenants",
    "blockers",
    "ready",
    "status",
    "overrides",
    "fingerprints",
    "discovery_version",
    "tenant_isolation",
    "source_isolation",
    "in_place",
)


_REVIEW_REASONS = {
    "tenant_boundary_invalid": "租户会话目录或配置证据存在边界冲突，修复后重新审核",
    "config_invalid": "租户配置无效，修复后重新审核",
    "share_invalid": "租户分享记录或正文未通过校验",
    "tenant_input_invalid": "租户会话输入未通过校验，修复后重新审核",
    "tenant_capacity_exceeded": "租户会话输入超过迁移容量或条目预算",
    "tenant_evidence_locked": "租户已有迁移数据或票据，已保留原迁移证据",
}


def _review_failure(tenant):
    codes = {item.get("code") for item in tenant.get("blockers", [])}
    code = next(
        (key for key in _REVIEW_REASONS if key in codes),
        "tenant_input_invalid",
    )
    return {
        "service_unit_id": tenant["service_unit_id"],
        "tenant_id": tenant["tenant_id"],
        **({"source_id": tenant["source_id"]} if _SOURCE_MODE.get() else {}),
        "stage": "retry-review",
        "code": code,
        "reason": _REVIEW_REASONS[code],
    }


def _review_failures(report, published):
    return {
        _key(tenant): _review_failure(tenant)
        for tenant in report["tenants"]
        if tenant["state"] == "failed" and _key(tenant) not in published
    }


class _TenantReviewHasData(ValueError):
    """The tenant must retain its committed frozen evidence."""


def _digest(data):
    digest = sha256()
    for chunk in iter_json(data):
        digest.update(chunk.encode())
    return digest.hexdigest()


def _write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        for chunk in iter_json(data):
            stream.write(chunk)
        stream.flush()
        os.fsync(stream.fileno())
    _sync(path.parent)


def _sync(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _pending(manifest):
    return manifest.path.with_name(manifest.path.name + ".review-pending.json")


def _key(item):
    key = item["service_unit_id"], item["tenant_id"]
    return (*key, item["source_id"]) if _SOURCE_MODE.get() else key


def _evidence(data, key):
    return {
        "workspaces": [w for w in data["workspaces"] if _key(w) == key],
        "shares": [s for s in data["shares"] if _key(s) == key],
        "service": next(
            s for s in data["services"] if s["service_unit_id"] == key[0]
        ),
    }


def _without_counts(value):
    if isinstance(value, dict):
        return {
            k: _without_counts(v)
            for k, v in value.items()
            if k not in ("counts", "empty")
        }
    if isinstance(value, list):
        return [_without_counts(v) for v in value]
    return value


def _source(data):
    # Reuse the exact journal canonical binding contract.
    from types import SimpleNamespace

    return MigrationJournal(
        None,
        SimpleNamespace(data=data, migration_id=data["migration_id"]),
    )._bindings()[1]


def _ticket_owner(row, workspaces=(), shares=()):
    details = row.get("details_text")
    raw_position = row["source_key"]
    if isinstance(raw_position, bytes):
        raw_position = raw_position.decode()
    if _SOURCE_MODE.get():
        owners = {_key(s) for s in shares if s.get("position") == raw_position}
        if len(owners) == 1:
            return owners.pop()
        if len(owners) > 1:
            raise ValueError("journal share ownership is ambiguous")
    if details:
        value = json.loads(details)
        if row.get("entry_kind") in ("retention", b"retention"):
            if (
                _SOURCE_MODE.get()
                and value.get("scope_kind") == "legacy_share"
            ):
                raise ValueError(
                    "legacy retention requires publication ownership check",
                )
            if isinstance(value.get("service_unit_key"), str) and isinstance(
                value.get("tenant_key"),
                str,
            ):
                return (
                    (
                        value["service_unit_key"],
                        value["tenant_key"],
                        value["source_key"],
                    )
                    if _SOURCE_MODE.get()
                    else (value["service_unit_key"], value["tenant_key"])
                )
        scope = value.get("scope")
        if _SOURCE_MODE.get() and value.get("scope_kind") == "legacy_share":
            raise ValueError("journal legacy share ownership cannot be proved")
        if isinstance(scope, list) and len(scope) == 4:
            return tuple(scope[:3] if _SOURCE_MODE.get() else scope[:2])
    raw = row["source_key"]
    if isinstance(raw, bytes):
        raw = raw.decode()
    if row.get("entry_kind") in ("share", b"share"):
        owners = {_key(share) for share in shares if share["token"] == raw}
        if len(owners) == 1:
            return owners.pop()
        raise ValueError("journal share ownership cannot be proved")
    # Entity source keys consist of a JSON identity followed by an optional
    # occurrence suffix. Decode only the leading JSON, never split on slashes
    # that may legally occur inside domain identities.
    try:
        value, end = json.JSONDecoder().raw_decode(raw)
    except ValueError as error:
        raise ValueError(
            "journal ticket ownership cannot be proved",
        ) from error
    if isinstance(value, list) and value and value[0] == "workspace":
        owners = {_key(w) for w in workspaces if w["position"] == raw[:end]}
        if len(owners) == 1 and (not raw[end:] or raw[end:].startswith("/")):
            return owners.pop()
    if raw[end:] and not raw[end:].startswith("/"):
        raise ValueError("journal source key has unknown suffix")
    if (
        isinstance(value, list)
        and value[0] in ("session", "chat")
        and len(value) >= 5
    ):
        return tuple(value[1:4] if _SOURCE_MODE.get() else value[1:3])
    raise ValueError("journal ticket ownership cannot be proved")


async def _no_data(
    db,
    migration_id,
    keys,
    workspaces=(),
    shares=(),
    *,
    exclude_historical_shares=False,
):
    analysis = _REVIEW_TICKETS.get()
    if analysis is not None and analysis["task"] is not asyncio.current_task():
        raise RuntimeError("review ownership proof requires original SQL task")
    for key in keys:
        service, tenant = key[:2]
        source = key[2] if len(key) == 3 else None
        for table in BUSINESS_TABLES:
            if table == "swe_conversation_turns":
                orphan = await db.fetch_one(
                    "SELECT b.id FROM "
                    + table
                    + " b LEFT JOIN swe_conversation_sessions s ON s.id=b.session_id AND s.service_unit_key=b.service_unit_key WHERE s.id IS NULL LIMIT 1",
                )
                if orphan:
                    raise ValueError(
                        "tenant review cannot attribute orphan business row",
                    )
                query = (
                    "SELECT b.id FROM "
                    + table
                    + " b JOIN swe_conversation_sessions s ON s.id=b.session_id AND s.service_unit_key=b.service_unit_key WHERE s.service_unit_key=%s AND s.tenant_key=%s LIMIT 1"
                )
            else:
                query = (
                    "SELECT id FROM "
                    + table
                    + " WHERE service_unit_key=%s AND tenant_key=%s LIMIT 1"
                )
            values = (service.encode(), tenant.encode())
            if source is not None:
                prefix = "s." if table == "swe_conversation_turns" else ""
                query = query.replace(
                    " LIMIT 1",
                    " AND " + prefix + "source_key=%s LIMIT 1",
                )
                values += (source.encode(),)
                if table in (
                    "swe_conversation_publications",
                    "swe_conversation_retentions",
                ):
                    query = query.replace(
                        " LIMIT 1",
                        " AND scope_kind<>'legacy_share' LIMIT 1",
                    )
            row = await db.fetch_one(query, values)
            if row:
                raise _TenantReviewHasData(
                    "tenant evidence cannot change after business data exists",
                )
        if source is not None and not exclude_historical_shares:
            await _no_legacy_data(db, migration_id, key, shares)
    await _no_tickets(db, migration_id, keys, workspaces, shares)


async def _ticket_rows(db, migration_id):
    after = 0
    while True:
        rows = await db.fetch_all(
            "SELECT id,entry_kind,source_key,target_id,details_text FROM "
            + ENTRIES
            + " WHERE migration_id=%s AND id>%s ORDER BY id LIMIT 1000",
            (migration_id.encode(), after),
        )
        if not rows:
            return
        yield rows
        after = rows[-1]["id"]


async def _ticket_ownership(db, migration_id, row, workspaces, shares):
    # Runtime-ID tickets are unrelated reservations by published writers.
    if row.get("entry_kind") in ("runtime_id", b"runtime_id"):
        return None
    if _SOURCE_MODE.get() and row.get("entry_kind") in (
        "retention",
        b"retention",
    ):
        return await _retention_owner(db, migration_id, row, shares)
    return _ticket_owner(row, workspaces, shares)


async def _no_tickets(db, migration_id, keys, workspaces, shares):
    analysis = _REVIEW_TICKETS.get()
    if analysis is None:
        async for rows in _ticket_rows(db, migration_id):
            for row in rows:
                owner = await _ticket_ownership(
                    db,
                    migration_id,
                    row,
                    workspaces,
                    shares,
                )
                if owner in keys:
                    raise _TenantReviewHasData(
                        "tenant evidence cannot change after a journal ticket exists",
                    )
        return
    identity = (
        id(db),
        migration_id,
        id(workspaces),
        id(shares),
        _SOURCE_MODE.get(),
    )
    if analysis.get("identity") != identity:
        if "owners" in analysis:
            analysis.pop("owners").close()
        owners = DiskMap()
        analysis["owners"] = owners
        # Mark complete only after every ticket has a proven owner.
        async for rows in _ticket_rows(db, migration_id):
            for row in rows:
                owner = await _ticket_ownership(
                    db,
                    migration_id,
                    row,
                    workspaces,
                    shares,
                )
                if owner is not None:
                    owners[_json(owner)] = True
        analysis["identity"] = identity
    if any(_json(key) in analysis["owners"] for key in keys):
        raise _TenantReviewHasData(
            "tenant evidence cannot change after a journal ticket exists",
        )


async def _legacy_publication_owner(db, migration_id, publication_id, shares):
    ticket = await db.fetch_one(
        "SELECT entry_kind,source_key,details_text FROM "
        + ENTRIES
        + " WHERE migration_id=%s AND entry_kind='publication' AND target_id=%s AND id=target_id",
        (migration_id.encode(), publication_id),
    )
    if ticket is None:
        raise ValueError("legacy publication has no migration ticket")
    return _ticket_owner(ticket, shares=shares)


async def _retention_owner(db, migration_id, ticket, shares):
    details = json.loads(ticket["details_text"])
    if details.get("scope_kind") != "legacy_share":
        return _ticket_owner(ticket, shares=shares)
    if details.get("source_key") or details.get("agent_key"):
        raise ValueError("legacy retention scope differs")
    if details.get("publication_id") is not None:
        owner = await _legacy_publication_owner(
            db,
            migration_id,
            details["publication_id"],
            shares,
        )
        if owner[:2] != (details["service_unit_key"], details["tenant_key"]):
            raise ValueError("legacy retention publication tenant differs")
        return owner
    # A shared guard is not owned by the real empty-source unit. Validate its
    # immutable SQL identity instead of attributing it to any one source.
    current = await db.fetch_one(
        "SELECT * FROM swe_conversation_retentions WHERE id=%s",
        (ticket["target_id"],),
    )
    if (
        details.get("kind") != "gc_guard"
        or current is None
        or any(
            (
                current.get(key).decode()
                if isinstance(current.get(key), bytes)
                else current.get(key)
            )
            != value
            for key, value in details.items()
        )
    ):
        raise ValueError("shared legacy retention guard differs")
    return None


async def _no_legacy_data(db, migration_id, key, shares):
    service, tenant, _source = key
    for table in ("publications", "retentions"):
        after = -1
        while True:
            rows = await db.fetch_all(
                "SELECT * FROM swe_conversation_"
                + table
                + " WHERE service_unit_key=%s AND tenant_key=%s AND scope_kind='legacy_share' AND source_key='' AND id>%s ORDER BY id LIMIT 1000",
                (service.encode(), tenant.encode(), after),
            )
            for row in rows:
                publication_id = (
                    row["id"]
                    if table == "publications"
                    else row.get("publication_id")
                )
                if publication_id is None:
                    if row.get("kind") != "gc_guard" or row.get("agent_key"):
                        raise ValueError("unknown shared legacy retention")
                    ticket = await db.fetch_one(
                        "SELECT entry_kind,source_key,target_id,details_text FROM "
                        + ENTRIES
                        + " WHERE migration_id=%s AND entry_kind='retention' AND target_id=%s",
                        (migration_id.encode(), row["id"]),
                    )
                    if ticket is None:
                        raise ValueError(
                            "shared legacy retention guard has no ticket",
                        )
                    await _retention_owner(db, migration_id, ticket, shares)
                    continue
                owner = await _legacy_publication_owner(
                    db,
                    migration_id,
                    publication_id,
                    shares,
                )
                if owner[:2] != key[:2]:
                    raise ValueError("legacy publication tenant differs")
                if owner == key:
                    raise _TenantReviewHasData(
                        "source evidence cannot change after legacy share data exists",
                    )
            if len(rows) < 1000:
                break
            after = rows[-1]["id"]


def _review_semantic(
    data,
    manifest,
    published,
    retained_only=(),
    validator=None,
):
    from .inventory_v3 import inventory_discovery

    keys = {_key(w) for w in data["workspaces"]}
    keys.update(_key(s) for s in data["shares"])
    if keys and keys.issubset(retained_only):
        return {
            "blockers": [],
            "workspaces": [
                {"sessions": (), "chats": ()} for _ in data["workspaces"]
            ],
        }
    if keys and keys.issubset(published):
        # The immutable frozen mapping must agree, but live tenant bodies
        # are never re-inventoried by a retry of another account.
        for key in keys:
            if key in retained_only:
                continue
            if _without_counts(_evidence(data, key)) != _without_counts(
                _evidence(manifest.data, key),
            ):
                raise ValueError("published tenant metadata cannot change")
        return {
            "blockers": [],
            "workspaces": [
                {
                    "sessions": range(
                        next(
                            old
                            for old in manifest.data["workspaces"]
                            if old["position"] == w["position"]
                        )["counts"]["sessions"],
                    ),
                    "chats": range(
                        next(
                            old
                            for old in manifest.data["workspaces"]
                            if old["position"] == w["position"]
                        )["counts"]["chats"],
                    ),
                }
                for w in data["workspaces"]
            ],
        }
    return (validator or inventory_discovery)(data)


def _review_validator(manifest, published, retained_only, validator):
    def semantic(data):
        return _review_semantic(
            data,
            manifest,
            published,
            retained_only,
            validator,
        )

    if validator is not None and hasattr(validator, "map_tenants"):

        def map_tenants(items):
            items = list(items)
            candidates, slots = [], []
            results = [None] * len(items)
            for index, data in enumerate(items):
                keys = {_key(w) for w in data["workspaces"]}
                keys.update(_key(s) for s in data["shares"])
                if keys and keys.issubset(published | set(retained_only)):
                    results[index] = semantic(data)
                else:
                    candidates.append(data)
                    slots.append(index)
            for index, result in zip(slots, validator.map_tenants(candidates)):
                results[index] = result
            return iter(results)

        semantic.map_tenants = map_tenants
    if validator is not None and hasattr(validator, "map_input_digests"):
        semantic.map_input_digests = validator.map_input_digests
    return semantic


def _discover_review(
    manifest,
    reviewed_report,
    published,
    retained_only=(),
    semantic_validator=None,
):
    from contextlib import nullcontext
    from .in_place_review import published_pruning
    from .tenant_inputs import retained_input_digests

    in_place = manifest.data.get("in_place", False)
    published_positions = {
        item["position"]
        for item in manifest.data["workspaces"]
        if _key(item) in published
    }
    context = (
        published_pruning(manifest.data, published)
        if in_place
        else nullcontext()
    )
    with context, retained_input_digests(manifest.data, published):
        shares = reviewed_report["source_shares"]
        if in_place:
            old_owners = {s["token"]: _key(s) for s in manifest.data["shares"]}
            shares = [
                s
                for s in shares
                if old_owners.get(s["token"]) not in published
            ]
        overrides = reviewed_report.get("overrides", [])
        if in_place:
            overrides = [
                entry
                for entry in overrides
                if entry.get("position") not in published_positions
            ]
        result = discover_services(
            reviewed_report["declared_services"],
            shares=shares,
            overrides=overrides,
            tenant_isolation=True,
            source_isolation=manifest.data.get("source_isolation", False),
            in_place=in_place,
            semantic_validator=_review_validator(
                manifest,
                published,
                retained_only,
                semantic_validator,
            ),
        )
    if in_place:
        for field in ("workspaces", "shares", "tenants"):
            result[field].extend(
                item
                for item in manifest.data[field]
                if _key(item) in published
            )
        result["workspaces"].sort(
            key=lambda item: item["position"].encode(),
        )
        result["shares"].sort(key=lambda item: item["position"].encode())
        result["tenants"].sort(key=_key)
        result["source_shares"] = manifest.data["source_shares"]
        result["overrides"].extend(
            entry
            for entry in manifest.data.get("overrides", [])
            if entry.get("position") in published_positions
        )
        _review_boundaries(result, published, manifest.data)
    return result


def _restore_tenant(report, old, key):
    from copy import deepcopy

    positions = {
        item["position"]
        for data in (report, old)
        for item in data["workspaces"]
        if _key(item) == key
    }
    for field in ("workspaces", "shares", "tenants"):
        report[field] = [item for item in report[field] if _key(item) != key]
        report[field].extend(
            deepcopy(item) for item in old[field] if _key(item) == key
        )
    report["overrides"] = [
        entry
        for entry in report.get("overrides", [])
        if entry.get("position") not in positions
    ] + [
        deepcopy(entry)
        for entry in old.get("overrides", [])
        if entry.get("position") in positions
    ]


async def _retain_committed_failures(db, manifest, report, published=()):
    failures = {}
    old_tenants = {_key(item): item for item in manifest.data["tenants"]}
    with _ticket_analysis():
        for tenant in list(report["tenants"]):
            key = _key(tenant)
            if key in published or (
                tenant == old_tenants[key]
                and _evidence(report, key) == _evidence(manifest.data, key)
            ):
                continue
            try:
                await _no_data(
                    db,
                    manifest.migration_id,
                    {key},
                    manifest.data["workspaces"],
                    manifest.data["shares"],
                    exclude_historical_shares=(
                        "historical_shares"
                        in manifest.data.get("excluded_scopes", [])
                    ),
                )
            except _TenantReviewHasData:
                # Do not revise already committed evidence merely to record a new
                # failed candidate. The report's top-level blocker remains auditable.
                failure = (
                    tenant
                    if tenant["state"] == "failed"
                    else {
                        **tenant,
                        "blockers": [{"code": "tenant_evidence_locked"}],
                    }
                )
                failures[key] = _review_failure(failure)
                _restore_tenant(report, manifest.data, key)
    return failures


def _review_boundaries(report, published, old):
    from ..errors import IntegrityError
    from ..in_place_admission import tenant_write_boundaries

    for tenant in list(report["tenants"]):
        key = _key(tenant)
        if key in published:
            continue
        try:
            tenant_write_boundaries(report, tenant=key)
        except IntegrityError as error:
            # Check the same candidate against published ownership alone. This
            # resolves only the candidate's paths, never live published files.
            if "share mutable" in str(error) and published:
                scoped = {
                    **report,
                    **{
                        field: [
                            item
                            for item in report[field]
                            if _key(item) in published or _key(item) == key
                        ]
                        for field in ("workspaces", "tenants")
                    },
                }
                try:
                    tenant_write_boundaries(scoped, tenant=key)
                except IntegrityError:
                    _restore_tenant(report, old, key)
                    tenant = next(
                        item for item in report["tenants"] if _key(item) == key
                    )
            blocker = {
                "code": "tenant_boundary_invalid",
                "position": json.dumps(key),
                "detail": str(error),
            }
            tenant["state"] = "failed"
            if blocker not in tenant["blockers"]:
                tenant["blockers"].append(blocker)
            if blocker not in report["blockers"]:
                report["blockers"].append(blocker)
    if report["blockers"]:
        report.update(ready=False, status="partial_success")


def _settle_review_boundaries(report, old, protected):
    """Restore conflicting candidates until final ownership is stable."""
    from ..errors import IntegrityError
    from ..in_place_admission import tenant_write_boundaries

    protected = set(protected)
    failures = {}
    while True:
        for tenant in list(report["tenants"]):
            key = _key(tenant)
            if key in protected:
                continue
            try:
                tenant_write_boundaries(report, tenant=key)
            except IntegrityError as error:
                _restore_tenant(report, old, key)
                restored = next(
                    item for item in report["tenants"] if _key(item) == key
                )
                blocker = {
                    "code": "tenant_boundary_invalid",
                    "position": json.dumps(key),
                    "detail": str(error),
                }
                restored["state"] = "failed"
                if blocker not in restored["blockers"]:
                    restored["blockers"].append(blocker)
                if blocker not in report["blockers"]:
                    report["blockers"].append(blocker)
                failures[key] = _review_failure(restored)
                protected.add(key)
                # Restoring a root can invalidate an earlier candidate. Each
                # restart protects another tenant, which bounds this loop.
                break
        else:
            if failures:
                report.update(ready=False, status="partial_success")
            return failures


async def _review_owners(db, manifest, eligible):
    states = _states(db, manifest)
    published = set()
    for tenant in manifest.data["tenants"]:
        row = await states.get(*_key(tenant))
        if row is not None and row["state"] == "published":
            published.add(_key(tenant))
    preserved = set(published)
    if eligible is not None:
        known = {_key(t) for t in manifest.data["tenants"]}
        if not set(eligible).issubset(known - published):
            raise ValueError("automatic review tenant eligibility differs")
        preserved.update(known - set(eligible))

    return published, preserved


async def _review_retry(
    db,
    manifest,
    reviewed_report,
    eligible=None,
    *,
    semantic_validator=None,
):
    """Revise only failed/discovered zero-data tenants; never rewrite live scopes."""
    if not manifest.data.get("tenant_isolation"):
        raise ValueError("tenant review requires isolated migration")
    if _pending(manifest).exists():
        raise ValueError("pending tenant review must be recovered first")
    published, preserved = await _review_owners(db, manifest, eligible)

    arguments = (manifest, reviewed_report, preserved)
    if eligible is not None:
        arguments += (preserved - published,)
    if semantic_validator is not None:
        if eligible is None:
            arguments += ((),)
        arguments += (semantic_validator,)
    current = await asyncio.to_thread(_discover_review, *arguments)
    if eligible is not None and not manifest.data.get("in_place"):
        for key in preserved:
            _restore_tenant(current, manifest.data, key)
    if (
        eligible is None
        and not manifest.data.get("in_place")
        and current != reviewed_report
    ):
        raise ValueError(
            "review report differs from current complete discovery",
        )
    old = manifest.data
    if (
        current["services"] != old["services"]
        or current["declared_services"] != old["declared_services"]
    ):
        raise ValueError(
            "tenant review cannot change services or storage roots",
        )
    old_tenants = {_key(t): t for t in old["tenants"]}
    new_tenants = {_key(t): t for t in current["tenants"]}
    if set(old_tenants) != set(new_tenants):
        raise ValueError("tenant review cannot add or remove tenants")
    if current["source_shares"] != old["source_shares"]:
        raise ValueError("tenant review cannot change original share records")
    failures = _review_failures(current, published)
    retained_keys = []
    if old.get("in_place") or eligible is not None:
        retained = await _retain_committed_failures(
            db,
            manifest,
            current,
            preserved,
        )
        failures.update(retained)
        retained_keys = [list(key) for key in sorted(retained)]
        if old.get("in_place"):
            failures.update(
                _settle_review_boundaries(
                    current,
                    old,
                    preserved | retained.keys(),
                ),
            )
        new_tenants = {_key(t): t for t in current["tenants"]}
    changed = {
        k
        for k in old_tenants
        if _evidence(old, k) != _evidence(current, k)
        or old_tenants[k] != new_tenants[k]
    }
    if changed & preserved:
        raise ValueError("protected tenant evidence cannot change")
    if not changed:
        if failures:
            return {
                "outcome": "unchanged",
                "failures": list(failures.values()),
                "retained_keys": retained_keys,
            }
        if eligible is not None:
            return {
                "outcome": "unchanged",
                "failures": [],
                "retained_keys": retained_keys,
            }
        raise ValueError("tenant review contains no changed tenant evidence")
    revision = str(uuid4())
    new = _review_manifest(old, current, changed, failures, revision)
    await _commit_review(
        db,
        manifest,
        old,
        new,
        changed,
        new_tenants,
        revision,
    )
    outcome = await recover_pending_review(db, manifest)
    return {
        **outcome,
        "failures": list(failures.values()),
        "retained_keys": retained_keys,
    }


def _review_manifest(old, current, changed, failures, revision):
    new = {
        **old,
        **{k: current[k] for k in _FIELDS if k in current},
        "tenant_review_revision": revision,
        "tenant_review_failures": list(failures.values()),
    }
    from .freshness import tenant_key

    cutoff = time.time_ns()
    new["tenant_sync_started_at_ns"] = {
        **old.get("tenant_sync_started_at_ns", {}),
        **{tenant_key(*key): cutoff for key in changed},
    }
    new["source_change_blockers"] = [
        blocker
        for blocker in old.get("source_change_blockers", [])
        if tuple(blocker.get("scope", [])) not in changed
    ]
    return new


async def _commit_review(
    db,
    manifest,
    old,
    new,
    changed,
    new_tenants,
    revision,
):
    old_tenants = {_key(t): t for t in old["tenants"]}
    old_source, new_source = _source(old), _source(new)
    states = _states(db, manifest)
    async with db.transaction():
        job = await db.fetch_one(
            "SELECT * FROM " + JOBS + " WHERE migration_id=%s FOR UPDATE",
            (manifest.migration_id.encode(),),
        )
        if job is None or job["source_binding_text"] != old_source:
            raise ValueError("tenant review job binding changed")
        records = []
        for key in sorted(old_tenants):
            row = await states.get(*key, locked=True)
            if row is None:
                raise ValueError("tenant review requires registered tenants")
            if key in changed:
                if row["state"] not in ("failed", "discovered"):
                    raise ValueError(
                        "only failed or discovered tenants can be reviewed",
                    )
                if row["evidence_text"] != _json(_evidence(old, key)):
                    raise ValueError("tenant review old evidence differs")
                if new_tenants[key]["state"] not in ("discovered", "failed"):
                    raise ValueError(
                        "invalid reviewed tenant state",
                    )
                records.append(
                    {
                        "service": key[0],
                        "tenant": key[1],
                        **({"source": key[2]} if len(key) == 3 else {}),
                        "old": row["evidence_text"],
                        "new": _json(_evidence(new, key)),
                        "old_state": row["state"],
                        "new_state": new_tenants[key]["state"],
                        "failure": (
                            _json(new_tenants[key]["blockers"])
                            if new_tenants[key]["state"] == "failed"
                            else None
                        ),
                    },
                )
        await _no_data(
            db,
            manifest.migration_id,
            changed,
            old["workspaces"],
            old["shares"],
            exclude_historical_shares=(
                "historical_shares" in old.get("excluded_scopes", [])
            ),
        )
        files = {}
        for label, data in (("old", old), ("new", new)):
            path = manifest.path.with_name(
                manifest.path.name
                + ".review-"
                + revision
                + "."
                + label
                + ".json",
            )
            _write(path, data)
            files[label] = {"name": path.name, "sha256": _digest(data)}
        pending = {
            "version": 1,
            "migration_id": manifest.migration_id,
            "revision": revision,
            "files": files,
            "old_source": old_source,
            "new_source": new_source,
            "tenants": records,
        }
        _write(_pending(manifest), pending)
        verification = json.loads(job["verification_text"] or "{}")
        history = verification.setdefault("tenant_reviews", [])
        history.append(
            {
                "revision": revision,
                "old_source_sha256": sha256(old_source.encode()).hexdigest(),
                "new_source_sha256": sha256(new_source.encode()).hexdigest(),
                "tenants": [list(k) for k in sorted(changed)],
            },
        )
        verification["tenant_review_revision"] = revision
        changed_rows = await db.execute(
            "UPDATE "
            + JOBS
            + " SET source_binding_text=%s,verification_text=%s,updated_at=UTC_TIMESTAMP(6) WHERE migration_id=%s AND source_binding_text=%s",
            (
                new_source,
                _json(verification),
                manifest.migration_id.encode(),
                old_source,
            ),
        )
        if changed_rows != 1:
            raise ValueError("tenant review job compare-and-set failed")
        for record in records:
            changed_rows = await db.execute(
                "UPDATE "
                + (
                    "swe_conversation_migration_sources"
                    if _SOURCE_MODE.get()
                    else "swe_conversation_migration_tenants"
                )
                + " SET evidence_text=%s,state=%s,failure_text=%s,verification_text='{}',updated_at=UTC_TIMESTAMP(6) WHERE migration_id=%s AND service_unit_key=%s AND tenant_key=%s"
                + (" AND source_key=%s" if _SOURCE_MODE.get() else "")
                + " AND state=%s AND evidence_text=%s",
                (
                    record["new"],
                    record["new_state"],
                    record["failure"],
                    manifest.migration_id.encode(),
                    record["service"].encode(),
                    record["tenant"].encode(),
                    *(
                        (record["source"].encode(),)
                        if "source" in record
                        else ()
                    ),
                    record["old_state"],
                    record["old"],
                ),
            )
            if changed_rows != 1:
                raise ValueError(
                    "tenant review evidence compare-and-set failed",
                )


async def _recover_pending_review(db, manifest):
    """Resolve only provable old/new SQL outcomes; leave unknown outcomes intact."""
    path = _pending(manifest)
    if not path.exists():
        return None
    if path.is_symlink():
        raise ValueError("tenant review pending file cannot be a symlink")
    pending = json.loads(path.read_text())
    if pending["migration_id"] != manifest.migration_id:
        raise ValueError("tenant review migration differs")
    async with db.transaction():
        job = await db.fetch_one(
            "SELECT * FROM " + JOBS + " WHERE migration_id=%s FOR UPDATE",
            (manifest.migration_id.encode(),),
        )
        if job is None:
            raise ValueError("tenant review job is missing")
        verification = json.loads(job["verification_text"] or "{}")
        if (
            job["source_binding_text"] == pending["new_source"]
            and verification.get("tenant_review_revision")
            == pending["revision"]
        ):
            outcome = "new"
        elif (
            job["source_binding_text"] == pending["old_source"]
            and verification.get("tenant_review_revision")
            != pending["revision"]
        ):
            outcome = "old"
        else:
            raise ValueError("tenant review SQL outcome is unknown")
        states = _states(db, manifest)
        for record in pending["tenants"]:
            row = await states.get(
                record["service"],
                record["tenant"],
                *((record["source"],) if "source" in record else ()),
                locked=True,
            )
            expected_state = (
                record.get("new_state", "discovered")
                if outcome == "new"
                else record["old_state"]
            )
            if (
                row is None
                or row["evidence_text"] != record[outcome]
                or row["state"] != expected_state
            ):
                raise ValueError("tenant review SQL evidence outcome differs")
        snapshot = pending["files"][outcome]
        if Path(snapshot["name"]).name != snapshot["name"]:
            raise ValueError("tenant review snapshot path is unsafe")
        source = path.parent / snapshot["name"]
        if source.is_symlink():
            raise ValueError("tenant review snapshot cannot be a symlink")
        restored = V3Manifest.load(source)
        if (
            restored.migration_id != manifest.migration_id
            or _digest(restored.data) != snapshot["sha256"]
            or _source(restored.data) != pending[outcome + "_source"]
        ):
            raise ValueError("tenant review snapshot evidence differs")
        # A revision may repair either pre/post-commit manifest, never overwrite
        # unrelated later edits or a manifest belonging to another revision.
        if _source(manifest.data) not in (
            pending["old_source"],
            pending["new_source"],
        ):
            raise ValueError("tenant review local manifest diverged")
        manifest.data = restored.data
        manifest._persist()
        archive = path.with_name(
            manifest.path.name
            + ".review-"
            + pending["revision"]
            + "."
            + outcome
            + ".audit.json",
        )
        if archive.exists():
            if archive.read_bytes() != path.read_bytes():
                raise ValueError("tenant review audit archive differs")
        else:
            os.link(path, archive)
        path.unlink()
        _sync(path.parent)
    return {
        "revision": pending["revision"],
        "outcome": outcome,
        "failures": (
            manifest.data.get("tenant_review_failures", [])
            if outcome == "new"
            else []
        ),
    }


async def review_retry(
    db,
    manifest,
    reviewed_report,
    eligible=None,
    *,
    semantic_validator=None,
):
    token = _SOURCE_MODE.set(manifest.data.get("source_isolation", False))
    try:
        return await _review_retry(
            db,
            manifest,
            reviewed_report,
            eligible,
            semantic_validator=semantic_validator,
        )
    finally:
        _SOURCE_MODE.reset(token)


async def recover_pending_review(db, manifest):
    token = _SOURCE_MODE.set(manifest.data.get("source_isolation", False))
    try:
        return await _recover_pending_review(db, manifest)
    finally:
        _SOURCE_MODE.reset(token)
