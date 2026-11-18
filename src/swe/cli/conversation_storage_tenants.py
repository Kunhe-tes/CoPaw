# -*- coding: utf-8 -*-
"""Tenant-isolated direct migration, retaining the original job and SQL tickets."""

from contextlib import nullcontext, asynccontextmanager
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
import time
from types import SimpleNamespace

from swe.app.conversation_storage.bundle import BundleStore
from swe.app.conversation_storage.migration.direct_import import (
    DirectImporter,
    DirectTarget,
)
from swe.app.conversation_storage.migration.inventory_v3 import (
    inventories_equal,
    inventory_v3_spooled,
)
from swe.app.conversation_storage.migration.journal import (
    BUSINESS_TABLES,
    MigrationJournal,
    JournalRecovery,
    JOBS,
)
from swe.app.conversation_storage.migration.parallel import MigrationIO
from swe.app.conversation_storage.migration.tenant_errors import (
    TenantInputError,
)
from swe.app.conversation_storage.migration.preflight import (
    DMLDatabase,
    check_schema,
    check_migration_schema,
)
from swe.app.conversation_storage.migration.spool import (
    InventorySpool,
    MigrationCapacityError,
    MigrationDiskCapacityError,
)
from swe.app.conversation_storage.migration.tenant_state import TenantState
from swe.app.conversation_storage.migration.isolation import (
    unit_key,
    belongs,
    state_store,
)
from swe.app.conversation_storage.migration.verify import verify_import
from swe.app.conversation_storage.migration.progress import current_progress


def _stage(name):
    progress = current_progress()
    if progress is not None:
        progress.stage(name)


def _states(db, manifest):
    if not manifest.data.get("source_isolation"):
        return TenantState(db, manifest.migration_id)
    return state_store(db, manifest)


def _manifest_source_binding(data):
    return data.get("source_binding_storage") == "manifest-v1"


class TenantFailure(ValueError):
    """An explicitly identified tenant data failure, never a shared SQL error."""


class VerificationFailure(TenantFailure):
    def __init__(self, result):
        super().__init__(
            (
                "tenant semantic verification failed"
                if result.get("verification_level") == "full"
                else "tenant fast verification failed"
            ),
        )
        self.result = result


_VIEW_FIELDS = ("tenants", "workspaces", "shares", "source_change_blockers")


def _grouped_view(parent, key):
    """Index positions, not evidence copies, under the command's disk budget."""
    from swe.app.conversation_storage.migration.disk_manifest import DiskGroups

    signature = (
        parent.data.get("source_isolation"),
        parent.data.get("tenant_review_revision"),
        *(
            (id(parent.data.get(name)), len(parent.data.get(name, [])))
            for name in _VIEW_FIELDS
        ),
    )
    cached = getattr(parent, "_source_view_index", None)
    if cached is None or cached[0] != signature or cached[1].closed:
        if cached is not None:
            cached[1].close()
        positions = DiskGroups()
        try:
            for name in _VIEW_FIELDS:
                for offset, item in enumerate(parent.data.get(name, [])):
                    scope = (
                        tuple(item.get("scope", []))
                        if name == "source_change_blockers"
                        else tuple(
                            item.get(field)
                            for field in (
                                "service_unit_id",
                                "tenant_id",
                                "source_id",
                            )[: len(key)]
                        )
                    )
                    group = json.dumps((name, scope))
                    positions.add(group, offset)
        except BaseException:
            positions.close()
            raise
        parent._source_view_index = signature, positions
    else:
        positions = cached[1]
    return {
        name: [
            parent.data[name][offset]
            for offset in positions.positions(json.dumps((name, key)))
        ]
        for name in _VIEW_FIELDS
    }


async def _state_rows(states, data):
    keys = (unit_key(data, tenant) for tenant in data["tenants"])
    async for key, row in states.get_many(keys):
        yield key, row


class TenantManifest:
    """A filtered parser view; persist only the complete parent manifest."""

    def __init__(self, parent, tenant):
        self.parent = parent
        self.migration_id, self.path = parent.migration_id, parent.path
        self.key = unit_key(parent.data, tenant)
        self.data = {**parent.data, **_grouped_view(parent, self.key)}

    def _persist(self):
        for name in ("assignments", "batches"):
            self.parent.data[name] = self.data[name]
        self.parent._persist()

    def record_source_change(self, blocker):
        self._persist()
        result = self.parent.record_source_change(blocker)
        self.data["source_change_blockers"] = [
            b for b in result if tuple(b.get("scope", [])) == self.key
        ]
        return self.data["source_change_blockers"]

    def set_batch_state(self, *_args):
        # SQL completion is authoritative; verification runs read-only.
        return None

    def bind_target(self, target):
        self.parent._validate_target(target)
        if self.parent.data.get("target") != target:
            raise ValueError("tenant migration target differs from frozen job")


def tenant_evidence(view):
    return {
        "workspaces": view.data["workspaces"],
        "shares": view.data["shares"],
        "service": next(
            s
            for s in view.data["services"]
            if s["service_unit_id"] == view.key[0]
        ),
    }


def tenant_receipt(view):
    from .conversation_storage_v3_cmd import authority_receipt

    proof = authority_receipt(view)
    proof["services"] = {view.key[0]: proof["services"][view.key[0]]}
    return proof


def _work_base(work_dir, data):
    from .conversation_storage_v3_cmd import validate_output

    choices = (
        (Path(work_dir),)
        if work_dir
        else (Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve())
    )
    for choice in choices:
        try:
            candidate = validate_output(choice, data)
        except ValueError:
            continue
        if candidate.is_dir():
            return candidate
    raise ValueError("no tenant work directory is separate from source roots")


def _spool(base, data, memory_bytes, workers):
    return InventorySpool(
        base,
        max_bytes=shutil.disk_usage(base).free * 3 // 4,
        record_limit=memory_bytes // workers,
        checksum=data.get("source_binding_storage") != "manifest-v1",
        protected=[
            s[k]
            for s in data["services"]
            for k in (
                "source_root",
                "config_root",
                "snapshot_root",
                "nas_root",
            )
            if s.get(k)
        ],
    )


def _source_roots_available(data):
    return all(
        Path(service[key]).is_dir()
        for service in data["services"]
        for key in ("source_root", "config_root", "snapshot_root")
        if service.get(key)
    )


async def _inventory(view, spool, resources):
    from swe.app.conversation_storage.migration.source_inputs import (
        SourceInputInvalid,
    )

    async def inspect(function, *args):
        shared = resources.get("_shared_resources")
        io = resources.get("_shared_io")
        async with shared.reserve() if shared else nullcontext():
            if io is None:
                return function(*args)
            return await io.call(function, *args)

    if view.data.get("in_place") and not _manifest_source_binding(view.data):
        from swe.app.conversation_storage.in_place_admission import (
            tenant_write_boundaries,
        )
        from swe.app.conversation_storage.errors import IntegrityError

        try:
            await inspect(
                lambda: tenant_write_boundaries(
                    view.parent.data,
                    tenant=view.key,
                ),
            )
        except IntegrityError as error:
            raise TenantFailure("tenant input ownership overlaps") from error
        from swe.app.conversation_storage.migration.in_place_source import (
            verify_evidence,
        )

        try:
            for tenant in view.data["tenants"]:
                if belongs(tenant, view.key):
                    await inspect(verify_evidence, view.data, tenant)
        except SourceInputInvalid as error:
            raise TenantFailure(
                "tenant source path is unsafe or invalid",
            ) from error
        except FileNotFoundError as error:
            if not _source_roots_available(view.data):
                raise
            raise TenantFailure("tenant input is missing") from error

    try:
        from swe.app.conversation_storage.migration.tenant_inputs import (
            verify_chats_mtimes,
            verify_input_digest,
        )

        if not _manifest_source_binding(view.data):
            function = (
                verify_chats_mtimes
                if view.data.get("freshness_protocol")
                else verify_input_digest
            )
            await inspect(function, view.data, view.key)
        result = await inventory_v3_spooled(
            view,
            spool,
            record_source_changes=False,
            **{k: v for k, v in resources.items() if not k.startswith("_")},
            shared_resources=resources.get("_shared_resources"),
        )
    except SourceInputInvalid as error:
        raise TenantFailure(
            "tenant source path is unsafe or invalid",
        ) from error
    except FileNotFoundError as error:
        path = Path(error.filename) if error.filename else None
        explicit = {
            Path(share["snapshot_path"]) for share in view.data["shares"]
        }
        explicit.update(
            Path(reference)
            for tenant in view.data["tenants"]
            for reference in tenant.get("evidence_refs", [])
        )
        if (
            path is None
            or not _source_roots_available(view.data)
            or not (
                path in explicit
                or any(
                    path.is_relative_to(Path(w["root"]))
                    for w in view.data["workspaces"]
                )
            )
        ):
            raise
        raise TenantFailure("tenant input is missing") from error
    if not result["ready"] or result["blockers"]:
        raise TenantFailure("tenant inventory contains blockers")
    from swe.app.conversation_storage.migration.importer import (
        extract_messages,
    )

    def validate_messages():
        for workspace in result["workspaces"]:
            for session in workspace["sessions"]:
                extract_messages(session["legacy"]["root"], context_epoch=0)

    try:
        await inspect(validate_messages)
    except (KeyError, TypeError, ValueError) as error:
        raise TenantFailure("tenant message data is invalid") from error
    return result


async def _verify(
    db,
    bundles,
    view,
    inventory,
    target,
    resources,
    guard,
    *,
    verification_level="fast",
):
    readonly = SimpleNamespace(
        data=view.data,
        migration_id=view.migration_id,
        set_batch_state=lambda *_: None,
    )
    async with (
        nullcontext(resources["_shared_io"])
        if resources.get("_shared_io")
        else MigrationIO(resources["io_workers"])
    ) as io:
        result = await verify_import(
            db,
            bundles,
            readonly,
            inventory,
            target,
            io=io,
            health_check=guard.check,
            verification_level=verification_level,
            **{k: v for k, v in resources.items() if not k.startswith("_")},
        )
    if not result["passed"]:
        raise VerificationFailure(result)
    return result


async def _final_source_check(view, inventory, base, resources):
    if _manifest_source_binding(view.data):
        return
    if view.data.get("freshness_protocol"):
        from swe.app.conversation_storage.migration.tenant_inputs import (
            verify_chats_mtimes,
        )

        try:
            await resources["_shared_io"].call(
                verify_chats_mtimes,
                view.data,
                view.key,
            )
        except TenantInputError as error:
            raise TenantFailure(str(error)) from error
        return
    with _spool(
        base,
        view.data,
        resources["memory_bytes"],
        resources["workers"],
    ) as check_spool:
        actual = await _inventory(view, check_spool, resources)
        if not inventories_equal(inventory, actual):
            raise TenantFailure("tenant source changed during operation")


async def _one_tenant(operation, view, db, states, guard, base, resources):
    from .conversation_storage_v3_cmd import validate_runtime_roots

    schema = view.data["offline"]["application_schema"]
    target = DirectTarget(schema, schema, view.migration_id)
    journal = MigrationJournal(
        db,
        view,
        server_uuid=guard.server_uuid,
        recovery=resources.get("_journal_recovery"),
    )
    journal.active_tenant = view.key
    journal.frozen_bindings_data = view.parent.data
    bundles = {
        s["service_unit_id"]: BundleStore(s["nas_root"])
        for s in view.data["services"]
    }
    verification_level = resources.get("_verification_level", "fast")
    verification_result = None
    with _spool(
        base,
        view.data,
        resources["memory_bytes"],
        resources["workers"],
    ) as spool:
        _stage("inventory")
        inventory = resources.get("_prefetched")
        if inventory is None:
            inventory = await _inventory(view, spool, resources)
        else:
            await _recheck_prefetched(view, resources)
        row = await states.get(*view.key)
        if operation in ("import", "resume", "migrate"):
            _stage("import")
            await DirectImporter(
                db,
                bundles,
                view,
                target,
                journal=journal,
            ).run_parallel(
                inventory,
                workers=resources["workers"],
                io_workers=resources["io_workers"],
                health_check=guard.check,
                io=resources.get("_shared_io"),
            )
        elif row["state"] not in ("imported", "verified"):
            raise TenantFailure("complete tenant import is required")
        else:
            await journal.hydrate(persist=False)
            await journal.validate_ownership()
        if operation in ("verify", "finalize", "migrate"):
            _stage("verify")
            verification_result = await _verify(
                db,
                bundles,
                view,
                inventory,
                target,
                resources,
                guard,
                verification_level=verification_level,
            )
        _stage("final_source_check")
        await _final_source_check(view, inventory, base, resources)
        await guard.check()
        await check_migration_schema(
            db,
            schema,
            source_isolation=view.data.get("source_isolation", False),
        )
        if operation in ("verify", "finalize", "migrate"):
            await states.transition(
                *view.key,
                "verified",
                verification_result,
            )
        if operation in ("finalize", "migrate"):
            _stage("publish")
            # The receipt is service-local; only this tenant's roots are checked.
            selected = {
                **view.data,
                "services": [
                    s
                    for s in view.data["services"]
                    if s["service_unit_id"] == view.key[0]
                ],
            }
            try:
                validate_runtime_roots({**selected, "services": []})
            except ValueError as error:
                raise TenantFailure(
                    "tenant runtime root is unavailable",
                ) from error
            await states.publish(
                *view.key,
                tenant_receipt(view),
            )


_TENANT_FAILURE_REASONS = {
    "tenant input ownership overlaps": "租户输入与其他账号重叠，无法独立发布",
    "tenant source path is unsafe or invalid": "会话路径不安全：检查软链接、越界或特殊文件",
    "tenant input is missing": "冻结会话输入缺失",
    "tenant inventory contains blockers": "会话清单校验失败；查看受限审计清单中的 blockers",
    "tenant message data is invalid": "会话消息格式无效",
    "unregistered tenant share appeared": "出现未登记的分享记录",
    "unpublished tenant original shares changed": "未发布租户的原始分享记录发生变化",
    "tenant semantic verification failed": "导入结果与源会话语义校验不一致",
    "tenant fast verification failed": "导入结果结构校验失败；该来源未发布",
    "complete tenant import is required": "租户导入未完成；先执行 resume --apply",
    "tenant source changed during operation": "迁移期间冻结会话输入发生变化",
    "tenant runtime root is unavailable": "运行时 workspace 目录缺失或不安全",
}


def _failure(tenant, stage, code="tenant_data_invalid", error=None):
    reason = _TENANT_FAILURE_REASONS.get(
        str(error),
        "租户会话输入或完整性校验未通过，修复后重试",
    )
    if isinstance(error, TenantInputError):
        code, reason = (
            "tenant_input_invalid",
            "租户输入无效或准备后发生变化；下次执行将自动重审",
        )
    if isinstance(error, MigrationCapacityError):
        code, reason = (
            "tenant_capacity_exceeded",
            "会话输入超过迁移容量或条目预算",
        )
    if stage == "discover":
        reason = "租户发现失败；查看 discovery.json 中该租户的 blockers"
    return {
        "service_unit_id": tenant["service_unit_id"],
        "tenant_id": tenant["tenant_id"],
        **(
            {"source_id": tenant["source_id"]} if "source_id" in tenant else {}
        ),
        "stage": stage,
        "code": code,
        "reason": reason,
    }


def _write_failures(manifest, operation, failures):
    from .conversation_storage_v3_cmd import _write_json

    destination = manifest.path.parent / (
        manifest.path.name
        + "."
        + operation
        + "."
        + str(time.time_ns())
        + ".failed-tenants.json"
    )
    _write_json(destination, failures)
    return str(destination)


def _write_runtime(output, manifest):
    from .conversation_storage_v3_cmd import _write_json

    output.mkdir(parents=True, exist_ok=True)
    destination = output / "manifest.json"
    if manifest.path.resolve() != destination.resolve():
        shutil.copyfile(manifest.path, destination)
    for service in manifest.data["services"]:
        document = {
            "version": 3,
            "migration_id": manifest.migration_id,
            "service_unit_id": service["service_unit_id"],
            "nas_root": service["nas_root"],
        }
        name = sha256(service["service_unit_id"].encode()).hexdigest()
        _write_json(output / (name + ".runtime.json"), document)


def _review_report(manifest, outcome):
    failures = outcome.get("failures", [])
    return {
        "version": 3,
        "status": "partial_success" if failures else "success",
        "review": outcome,
        "migration_id": manifest.migration_id,
        "failed": len(failures),
        "failure_report": _write_failures(manifest, "retry-review", failures),
    }


async def _rollback_command(
    control,
    manifest,
    output,
    guard,
    apply,
    rollback_inputs,
):
    if not apply or rollback_inputs is None or output is None:
        raise ValueError(
            "rollback-tenants requires --apply, --rollback-inputs and --output-dir",
        )
    from swe.app.conversation_storage.chat_mutations import (
        load_metadata_json,
    )
    from swe.app.conversation_storage.migration.tenant_rollback import (
        TenantRollbackEvidence,
        compose_tenant_rollback,
    )
    from swe.app.conversation_storage.migration.manifest import (
        SourceBoundary,
    )
    from swe.app.conversation_storage.migration.exporter import (
        OldFormatTarget,
    )

    inputs = load_metadata_json(Path(rollback_inputs).read_bytes())
    evidence = TenantRollbackEvidence(
        SourceBoundary(**inputs["boundary"]),
        inputs["writers_stopped_ref"],
        inputs["io_drained_ref"],
        inputs["current_config_review_ref"],
    )
    await guard.check()
    report = await compose_tenant_rollback(
        control,
        manifest,
        output,
        OldFormatTarget(**inputs["target"]),
        evidence,
        current_configs=inputs["current_configs"],
    )
    await guard.check()
    return {
        **report,
        "status": "partial_success",
        "reason": "pinned old image validation is required before rollback",
    }


@asynccontextmanager
async def _migration_sql_owner(control, schema, manifest):
    from swe.database.connection import _named_lock_name
    from swe.app.conversation_storage.migration.lock_guard import (
        MigrationLockGuard,
    )

    db = DMLDatabase(control)
    if _manifest_source_binding(manifest.data) or manifest.data.get(
        "freshness_protocol",
    ):
        identity = await db.fetch_one(
            "SELECT @@server_uuid AS server_uuid,DATABASE() AS schema_name",
        )
        if identity["schema_name"] != schema or not identity["server_uuid"]:
            raise ValueError("database identity differs from target")
        control.expect_identity(identity["server_uuid"], schema)
        guard = await MigrationLockGuard.capture_identity(
            db,
            schema=schema,
            server_uuid=identity["server_uuid"],
        )
        yield db, guard
        return
    async with control.named_lock(
        "conversation-migration:" + schema,
        timeout=0,
    ):
        identity = await db.fetch_one(
            "SELECT @@server_uuid AS server_uuid,DATABASE() AS schema_name",
        )
        if identity["schema_name"] != schema or not identity["server_uuid"]:
            raise ValueError("database identity differs from target")
        guard = await MigrationLockGuard.capture(
            db,
            _named_lock_name("conversation-migration:" + schema),
            schema=schema,
            server_uuid=identity["server_uuid"],
        )
        yield db, guard


async def run_tenants(
    operation,
    manifest,
    output,
    *,
    workers,
    io_workers,
    memory_budget_mib,
    work_dir,
    apply,
    reviewed_discovery=None,
    rollback_inputs=None,
    verification_level="fast",
):
    """Run one SQL-owner job; skip published tenants before reading old input."""
    from swe.database.config import get_database_config
    from swe.database.connection import DatabaseConnection

    base = _work_base(work_dir, manifest.data)
    _validate_tenant_roots(manifest.data)
    resources = {
        "workers": workers,
        "io_workers": io_workers,
        "memory_bytes": memory_budget_mib * 1024 * 1024,
        "_verification_level": verification_level,
    }
    config = get_database_config()
    schema = manifest.data["offline"]["application_schema"]
    if config.database != schema:
        raise ValueError("configured application schema differs from manifest")
    control = DatabaseConnection(
        config.model_copy(update={"time_zone": "+00:00"}),
    )
    try:
        _stage("database_setup")
        await control.connect()
        async with _migration_sql_owner(
            control,
            schema,
            manifest,
        ) as (db, guard):
            await check_migration_schema(
                db,
                schema,
                source_isolation=manifest.data.get("source_isolation", False),
            )
            from swe.app.conversation_storage.migration.tenant_retry import (
                recover_pending_review,
                review_retry,
            )

            if not (
                _manifest_source_binding(manifest.data)
                or manifest.data.get("freshness_protocol")
            ):
                await recover_pending_review(db, manifest)
            # Fix cutoffs under the same lock before first recording SQL binding.
            if (
                operation in ("import", "resume", "migrate")
                and apply
                and not (
                    _manifest_source_binding(manifest.data)
                    or manifest.data.get("freshness_protocol")
                )
            ):
                manifest.begin_tenant_syncs(
                    [
                        unit_key(manifest.data, t)
                        for t in manifest.data["tenants"]
                    ],
                )
            await _check_job_binding(db, manifest, guard.server_uuid)
            if operation == "migrate":
                if not apply:
                    raise ValueError("migrate requires --apply")
                if not (
                    _manifest_source_binding(manifest.data)
                    or manifest.data.get("freshness_protocol")
                ):
                    _stage("automatic_review")
                    resources["_retained_attempts"] = await _auto_review(
                        db,
                        manifest,
                        guard,
                        resources,
                    )
            if operation == "retry-review":
                if not apply or reviewed_discovery is None:
                    raise ValueError(
                        "retry-review requires --apply and --reviewed-discovery",
                    )
                from swe.app.conversation_storage.chat_mutations import (
                    load_metadata_json,
                )

                report = load_metadata_json(
                    Path(reviewed_discovery).read_bytes(),
                )
                await guard.check()
                outcome = await review_retry(db, manifest, report)
                await guard.check()
                return _review_report(manifest, outcome)
            if operation == "rollback-tenants":
                return await _rollback_command(
                    control,
                    manifest,
                    output,
                    guard,
                    apply,
                    rollback_inputs,
                )
            if operation == "preflight":
                if _manifest_source_binding(manifest.data):
                    failures = [
                        _failure(tenant, "discover")
                        for tenant in manifest.data["tenants"]
                        if tenant.get("state") == "failed"
                    ]
                    return {
                        "version": 3,
                        "operation": "preflight",
                        "status": (
                            "partial_success" if failures else "success"
                        ),
                        "migration_id": manifest.migration_id,
                        "tenant_isolation": True,
                        "source_isolation": True,
                        "passed": not failures,
                        "state": "preflight_passed",
                        "tenants": len(manifest.data["tenants"]),
                        "published": 0,
                        "completed": 0,
                        "failed": len(failures),
                        "pending_schema_finalize": False,
                        "failure_report": _write_failures(
                            manifest,
                            "prepare",
                            failures,
                        ),
                    }
                if manifest.data.get("freshness_protocol"):
                    return {
                        "version": 3,
                        "operation": "preflight",
                        "status": "success",
                        "migration_id": manifest.migration_id,
                        "tenant_isolation": True,
                        "source_isolation": True,
                        "passed": True,
                        "state": "preflight_passed",
                        "tenants": len(manifest.data["tenants"]),
                        "published": 0,
                        "completed": 0,
                        "failed": 0,
                        "pending_schema_finalize": False,
                        "failure_report": None,
                    }
                result = await _preview(
                    operation,
                    manifest,
                    base,
                    resources,
                    states=_states(db, manifest),
                )
                return {**result, "passed": result["failed"] == 0}
            if operation in ("inventory", "plan", "inspect") or (
                operation in ("import", "resume", "finalize") and not apply
            ):
                return await _preview(
                    operation,
                    manifest,
                    base,
                    resources,
                    states=_states(db, manifest),
                )
            return await _run_registered(
                operation,
                manifest,
                output,
                db,
                guard,
                base,
                resources,
            )
    finally:
        await control.close()


async def _register_tenants(db, manifest, states, guard):
    _stage("registration")
    tenants = manifest.data["tenants"]
    if not tenants:
        raise ValueError("migration requires at least one discovered tenant")
    registrations = []
    for tenant in tenants:
        view = TenantManifest(manifest, tenant)
        registrations.append({**tenant, "evidence": tenant_evidence(view)})
    # Retain a complete immutable job binding even when every tenant failed
    # discovery; runtime startup can then safely keep all tenants unavailable.
    jobs = await _check_job_binding(db, manifest, guard.server_uuid)
    await states.register(registrations)
    if not jobs:
        binding_journal = MigrationJournal(
            db,
            manifest,
            server_uuid=guard.server_uuid,
        )
        binding_journal.active_tenant = unit_key(manifest.data, tenants[0])
        await binding_journal.prepare()


async def _select_registered_tenants(
    manifest,
    states,
    resources,
    failures,
    published,
):
    tenants = manifest.data["tenants"]
    selected = []
    iterator = iter(tenants)
    async for key, row in _state_rows(states, manifest.data):
        tenant = next(iterator)
        if row["state"] == "published":
            published += 1
            continue
        if tenant["state"] == "failed" and key not in resources.get(
            "_retained_attempts",
            set(),
        ):
            failure = _failure(tenant, "discover")
            await states.fail(
                *key,
                "discover",
                failure["code"],
                failure["reason"],
            )
            failures.append(failure)
            continue
        selected.append(tenant)
    return selected, failures, published


async def _run_registered(
    operation,
    manifest,
    output,
    db,
    guard,
    base,
    resources,
):
    states = _states(db, manifest)
    tenants = manifest.data["tenants"]
    if not tenants:
        raise ValueError("tenant migration has no identifiable tenants")
    if resources.get("_registered_manifest") is manifest.data:
        # Automatic review already registered or atomically revised evidence.
        # Recheck the complete SQL binding before using that registration.
        await _check_job_binding(db, manifest, guard.server_uuid)
    else:
        await _register_tenants(db, manifest, states, guard)
    failures, published, completed = [], 0, 0
    resources = {
        **resources,
        "_journal_recovery": JournalRecovery(db, manifest),
    }
    _stage("selection")
    selected, failures, published = await _select_registered_tenants(
        manifest,
        states,
        resources,
        failures,
        published,
    )
    from .conversation_storage_pipeline import tenant_pipeline

    context = (
        tenant_pipeline(selected, base, manifest, resources)
        if operation == "migrate"
        and not manifest.data.get("freshness_protocol")
        and not _manifest_source_binding(manifest.data)
        else _serial_tenants(selected, resources)
    )
    async with context as results:
        async for tenant, local, error in results:
            view = TenantManifest(manifest, tenant)
            local_guard = _pipeline_guard(guard, local)
            await local_guard.check()
            try:
                if error is not None:
                    raise error
                await _one_tenant(
                    operation,
                    view,
                    db,
                    states,
                    local_guard,
                    base,
                    local,
                )
            except MigrationDiskCapacityError:
                raise
            except (
                TenantFailure,
                TenantInputError,
                MigrationCapacityError,
            ) as error:
                # A failed source may have committed SQL before mirroring it.
                # Reconcile durable tickets before processing the next source.
                resources["_journal_recovery"].confirmed = None
                failures.append(
                    await _record_tenant_failure(
                        states,
                        tenant,
                        operation,
                        error,
                    ),
                )
            else:
                completed += 1
                if operation in ("finalize", "migrate"):
                    published += 1
    # A job may remain partial while the runtime admits individually published tenants.
    pending_schema = False
    if published == len(tenants) and not failures:
        share_column = await db.fetch_one(
            "SELECT IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
            "AND TABLE_NAME='swe_chat_shares' AND COLUMN_NAME='service_unit_key'",
        )
        pending_schema = (
            not share_column or share_column["IS_NULLABLE"] != "NO"
        )
        if not pending_schema:
            await check_schema(
                db,
                manifest.data["offline"]["application_schema"],
                finalized=True,
            )
    state = (
        "ready"
        if published == len(tenants) and not failures and not pending_schema
        else "partial_success"
    )
    changed = await db.execute(
        "UPDATE "
        + JOBS
        + " SET state=%s,updated_at=UTC_TIMESTAMP(6) WHERE migration_id=%s",
        (state, manifest.migration_id.encode()),
    )
    if changed != 1:
        raise ValueError("migration job completion was not confirmed")
    if operation in ("finalize", "migrate"):
        _write_runtime(output, manifest)
    return {
        "version": 3,
        "migration_id": manifest.migration_id,
        "excluded_scopes": ["historical_shares"],
        "tenant_isolation": True,
        **(
            {"source_isolation": True, "counter_unit": "sources"}
            if manifest.data.get("source_isolation")
            else {}
        ),
        "status": (
            "partial_success" if failures or pending_schema else "success"
        ),
        "state": state,
        "tenants": len(tenants),
        "published": published,
        "completed": completed,
        "failed": len(failures),
        "pending_schema_finalize": pending_schema,
        "failure_report": _write_failures(manifest, operation, failures),
        **(
            {
                "verification_level": resources.get(
                    "_verification_level",
                    "fast",
                ),
            }
            if operation in ("verify", "finalize", "migrate")
            else {}
        ),
    }


@asynccontextmanager
async def _serial_tenants(tenants, resources):
    async def results():
        for tenant in tenants:
            yield tenant, resources, None

    yield results()


async def _record_tenant_failure(states, tenant, operation, error):
    failure = _failure(tenant, operation, error=error)
    if isinstance(error, VerificationFailure):
        key = unit_key({"source_isolation": "source_id" in tenant}, tenant)
        await states.record_verification(*key, error.result)
        failure["verification"] = {
            "verification_level": error.result["verification_level"],
            "passed": False,
            "blocker_count": len(error.result.get("blockers", [])),
        }
    await states.fail(
        *unit_key({"source_isolation": "source_id" in tenant}, tenant),
        operation,
        failure["code"],
        failure["reason"],
    )
    return failure


def _pipeline_guard(guard, resources):
    health = resources.get("_pipeline_health")
    if health is None:
        return guard

    async def check():
        await health()
        await guard.check()

    return SimpleNamespace(check=check, server_uuid=guard.server_uuid)


def _validate_tenant_roots(data):
    from swe.app.conversation_storage.migration.discovery import _overlaps

    for online in data["services"]:
        for frozen in data["services"]:
            if data.get("in_place") and online is frozen:
                roots = {
                    online.get(k)
                    for k in (
                        "source_root",
                        "config_root",
                        "snapshot_root",
                        "original_root",
                    )
                }
                if len(roots) != 1 or None in roots:
                    raise ValueError("in-place roots must be identical")
                continue
            if any(
                _overlaps(Path(online["original_root"]), Path(frozen[k]))
                for k in ("source_root", "config_root", "snapshot_root")
                if frozen.get(k)
            ):
                raise ValueError(
                    "partial migration requires isolated frozen inputs",
                )


async def _recheck_prefetched(view, resources):
    if _manifest_source_binding(view.data):
        return
    from swe.app.conversation_storage.migration.tenant_inputs import (
        verify_chats_mtimes,
        verify_input_digest,
    )
    from swe.app.conversation_storage.migration.source_inputs import (
        SourceInputInvalid,
    )

    try:
        async with resources["_shared_resources"].reserve():
            await resources["_shared_io"].call(
                (
                    verify_chats_mtimes
                    if view.data.get("freshness_protocol")
                    else verify_input_digest
                ),
                view.data,
                view.key,
            )
    except SourceInputInvalid as error:
        raise TenantFailure(
            "tenant source path is unsafe or invalid",
        ) from error
    except FileNotFoundError as error:
        if not _source_roots_available(view.data):
            raise
        raise TenantFailure("tenant input is missing") from error


async def _auto_review(db, manifest, guard, resources):
    from swe.app.conversation_storage.migration.tenant_retry import (
        review_retry,
    )

    states = _states(db, manifest)
    await _register_tenants(db, manifest, states, guard)
    _stage("automatic_review")
    eligible = set()
    iterator = iter(manifest.data["tenants"])
    async for key, row in _state_rows(states, manifest.data):
        tenant = next(iterator)
        if row["state"] != "published" and (
            row["state"] == "failed" or tenant["state"] == "failed"
        ):
            eligible.add(key)
    if eligible:
        await guard.check()
        from .conversation_storage_discovery_cmd import _semantic_validator

        validator = _semantic_validator(
            workers=resources["workers"],
            io_workers=resources["io_workers"],
            memory_budget_mib=resources["memory_bytes"] // (1024 * 1024),
            work_dir=str(manifest.path.parent),
        )
        outcome = await review_retry(
            db,
            manifest,
            manifest.data,
            eligible=eligible,
            semantic_validator=validator,
        )
        await guard.check()
        from swe.app.conversation_storage.migration.tenant_inputs import (
            verify_input_digest,
        )
        from swe.app.conversation_storage.migration.source_inputs import (
            SourceInputInvalid,
        )
        from swe.app.conversation_storage.in_place_admission import (
            tenant_write_boundaries,
        )
        from swe.app.conversation_storage.errors import IntegrityError

        allowed = set()
        for pair in outcome.get("retained_keys", []):
            key = tuple(pair)
            tenant = next(
                t
                for t in manifest.data["tenants"]
                if unit_key(manifest.data, t) == key
            )
            if not tenant.get("input_digest"):
                continue
            try:
                tenant_write_boundaries(manifest.data, tenant=key)
                verify_input_digest(manifest.data, key)
            except (
                TenantInputError,
                SourceInputInvalid,
                FileNotFoundError,
                IntegrityError,
            ):
                continue
            allowed.add(key)
        resources["_registered_manifest"] = manifest.data
        return allowed
    resources["_registered_manifest"] = manifest.data
    return set()


async def _check_job_binding(db, manifest, server_uuid):
    journal = MigrationJournal(db, manifest, server_uuid=server_uuid)
    target, source = journal._bindings()
    jobs = await db.fetch_all("SELECT * FROM " + JOBS)
    if any(
        row["migration_id"] != manifest.migration_id.encode() for row in jobs
    ):
        raise ValueError("another migration job owns this application schema")
    if jobs:
        if (
            jobs[0]["target_binding_text"] != target
            or jobs[0]["source_binding_text"] != source
            or jobs[0]["manifest_version"] != 3
        ):
            raise ValueError("migration source or target binding changed")
    else:
        for table in BUSINESS_TABLES:
            if await db.fetch_one("SELECT id FROM " + table + " LIMIT 1"):
                raise ValueError(
                    "first migration requires six empty business tables",
                )
    return jobs


async def _preview(operation, manifest, base, resources, *, states):
    failures, completed = [], 0
    selected = []
    iterator = iter(manifest.data["tenants"])
    async for _key, row in _state_rows(states, manifest.data):
        tenant = next(iterator)
        if row and row["state"] == "published":
            completed += 1
            continue
        if tenant["state"] == "failed":
            failures.append(_failure(tenant, "discover"))
            continue
        selected.append(tenant)
    from .conversation_storage_pipeline import tenant_pipeline

    async with tenant_pipeline(
        selected,
        base,
        manifest,
        resources,
        preview=True,
    ) as results:
        async for tenant, _local, error in results:
            if error is not None:
                failures.append(_failure(tenant, operation, error=error))
            else:
                completed += 1
    return {
        "version": 3,
        "migration_id": manifest.migration_id,
        "excluded_scopes": ["historical_shares"],
        "tenant_isolation": True,
        **(
            {"source_isolation": True, "counter_unit": "sources"}
            if manifest.data.get("source_isolation")
            else {}
        ),
        "preview": True,
        "status": "partial_success" if failures else "success",
        "completed": completed,
        "failed": len(failures),
        "failure_report": _write_failures(manifest, operation, failures),
    }
