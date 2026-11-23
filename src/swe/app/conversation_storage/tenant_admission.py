# -*- coding: utf-8 -*-
"""Database-backed tenant publication admission; no negative cache or fallback."""

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
from contextvars import ContextVar
import json
from copy import deepcopy
from uuid import UUID

from .errors import IntegrityError, StorageUnavailable
from .migration.authority import validate_source_verification

_ADMITTED_TRANSACTION = ContextVar(
    "conversation_admitted_transaction",
    default=None,
)
_MAX_CACHED_PROOFS = 32
_MAX_CACHED_PROOF_BYTES = 256 * 1024


class TenantNotPublished(StorageUnavailable):
    code = "conversation_tenant_not_published"

    def __init__(self):
        super().__init__("Conversation tenant is under maintenance")


class TenantAdmission:
    def __init__(self, database, document):
        if (
            set(document)
            != {
                "version",
                "service_unit_id",
                "nas_root",
                "migration_id",
            }
            or document["version"] != 3
        ):
            raise IntegrityError("invalid partial migration runtime document")
        if str(UUID(document["migration_id"])) != document["migration_id"]:
            raise IntegrityError("invalid partial migration identity")
        self.db = database
        self.document = dict(document)
        self._validated = False
        self._proofs = OrderedDict()

    async def validate(self):
        if self._validated:
            return
        doc = self.document
        job = await self.db.fetch_one(
            "SELECT target_binding_text,source_binding_text FROM "
            "swe_conversation_migration_jobs WHERE migration_id=%s",
            (doc["migration_id"].encode(),),
        )
        if job is None:
            raise IntegrityError("partial migration job is missing")
        binding = json.loads(job["target_binding_text"])
        source = json.loads(job["source_binding_text"])
        if source.get("source_binding_storage") == "manifest-v1":
            source = {
                "tenant_isolation": True,
                "source_isolation": source.get("source_isolation", True),
            }
        self.source_binding = source
        identity = await self.db.fetch_one(
            "SELECT @@server_uuid AS server_uuid,DATABASE() AS schema_name",
        )
        if (
            source.get("tenant_isolation") is not True
            or binding.get("server_uuid") != identity["server_uuid"]
            or binding.get("schema") != identity["schema_name"]
            or binding.get("migration_id") != doc["migration_id"]
            or binding.get("nas_roots", {}).get(doc["service_unit_id"])
            != doc["nas_root"]
        ):
            raise IntegrityError("partial migration authority binding differs")
        self._validated = True

    async def require(
        self,
        tenant_id,
        source_id=None,
        *,
        session=None,
        proof=True,
    ):
        await self.validate()
        doc = self.document
        source_mode = self.source_binding.get("source_isolation", False)
        if source_mode and source_id is None:
            raise TenantNotPublished()
        query = (
            " FROM "
            + (
                "swe_conversation_migration_sources"
                if source_mode
                else "swe_conversation_migration_tenants"
            )
            + " WHERE migration_id=%s AND service_unit_key=%s AND tenant_key=%s"
            + (" AND source_key=%s" if source_mode else "")
        )
        params = (
            doc["migration_id"].encode(),
            doc["service_unit_id"].encode(),
            tenant_id.encode(),
            *((source_id.encode(),) if source_mode else ()),
        )
        db = self.db if session is None else session
        row = await db.fetch_one(
            "SELECT state,SHA2(verification_text,256) AS proof_digest" + query,
            params,
        )
        if row is None or row["state"] != "published":
            raise TenantNotPublished()
        digest = row.get("proof_digest")
        key = tenant_id, source_id, digest
        if digest is not None and key in self._proofs:
            self._proofs.move_to_end(key)
            cached = self._proofs[key]
            if not proof:
                return None
            if cached is not None:
                return deepcopy(cached)
        if "verification_text" not in row:
            row = await db.fetch_one(
                "SELECT state,verification_text,SHA2(verification_text,256) AS proof_digest"
                + query,
                params,
            )
            if row is None or row["state"] != "published":
                raise TenantNotPublished()
            key = tenant_id, source_id, row["proof_digest"]
        verified, _level = validate_source_verification(
            row["verification_text"],
        )
        service = verified["services"].get(doc["service_unit_id"])
        if (
            verified["migration_id"] != doc["migration_id"]
            or set(verified["services"]) != {doc["service_unit_id"]}
            or service is None
            or service["nas_root"] != doc["nas_root"]
            or any(
                item["scope"][1] != tenant_id
                or (source_mode and item["scope"][2] != source_id)
                for item in service["workspaces"]
            )
        ):
            raise IntegrityError("tenant publication proof differs")
        if key[2] is not None:
            cacheable = (
                len(row["verification_text"]) <= _MAX_CACHED_PROOF_BYTES
            )
            self._proofs[key] = (
                deepcopy(service["workspaces"]) if cacheable else None
            )
            self._proofs.move_to_end(key)
            if len(self._proofs) > _MAX_CACHED_PROOFS:
                self._proofs.popitem(last=False)
        return service["workspaces"] if proof else None


class TenantDatabase:
    """Protect even previously cached adapters before each database operation."""

    def __init__(self, database, admission, tenant_id, source_id=None):
        self.source_id = source_id
        self.database, self.admission, self.tenant_id = (
            database,
            admission,
            tenant_id,
        )

    def _transaction_key(self):
        return (asyncio.current_task(), self, self.tenant_id, self.source_id)

    async def require(self, session=None):
        if _ADMITTED_TRANSACTION.get() == self._transaction_key():
            return
        if not isinstance(self.admission, TenantAdmission):
            args = () if self.source_id is None else (self.source_id,)
            await self.admission.require(self.tenant_id, *args)
        else:
            await self.admission.require(
                self.tenant_id,
                self.source_id,
                session=session,
                proof=False,
            )

    def __getattr__(self, name):
        member = getattr(self.database, name)
        if name not in {
            "fetch_one",
            "fetch_all",
            "execute",
            "insert",
            "executemany",
            "execute_many",
            "execute_result",
            "insert_prepared",
        }:
            return member

        async def guarded(*args, **kwargs):
            if _ADMITTED_TRANSACTION.get() == self._transaction_key():
                return await member(*args, **kwargs)
            if (
                getattr(self.database, "has_current_session", None)
                is not False
            ):
                await self.require()
                return await member(*args, **kwargs)
            async with self.database.acquire() as session:
                await self.require(session)
                return await member(*args, **kwargs)

        return guarded

    @asynccontextmanager
    async def acquire(self, *args, **kwargs):
        async with self.database.acquire(*args, **kwargs) as session:
            await self.require(session if hasattr(session, "_entry") else None)
            yield TenantDatabase(
                session,
                self.admission,
                self.tenant_id,
                self.source_id,
            )

    @asynccontextmanager
    async def transaction(self, *args, **kwargs):
        key = self._transaction_key()
        if _ADMITTED_TRANSACTION.get() == key:
            yield self
            return
        async with self.database.transaction(*args, **kwargs) as session:
            await self.require(session if hasattr(session, "_entry") else None)
            token = _ADMITTED_TRANSACTION.set(key)
            try:
                yield self
            finally:
                _ADMITTED_TRANSACTION.reset(token)


async def partial_jobs(database, service_unit_id=None):
    """Find opt-in migration jobs without requiring controls on legacy installs."""
    exists = await database.fetch_one(
        "SELECT COUNT(*) AS tenant_controls FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN "
        "('swe_conversation_migration_tenants','swe_conversation_migration_sources')",
    )
    if not exists or not int(exists.get("tenant_controls") or 0):
        return []
    rows = await database.fetch_all(
        "SELECT migration_id,target_binding_text,source_binding_text "
        "FROM swe_conversation_migration_jobs",
    )
    result = []
    for row in rows:
        source = json.loads(row["source_binding_text"])
        if source.get("tenant_isolation") is not True:
            continue
        binding = json.loads(row["target_binding_text"])
        if service_unit_id is None or service_unit_id in binding.get(
            "nas_roots",
            {},
        ):
            result.append((row, binding))
    return result


async def partial_admission(database, scope):
    jobs = await partial_jobs(database, scope.service_unit_id)
    if len(jobs) > 1:
        raise IntegrityError("ambiguous partial migration authority")
    if not jobs:
        return None
    row, binding = jobs[0]
    migration_id = row["migration_id"]
    if isinstance(migration_id, bytes):
        migration_id = migration_id.decode()
    return TenantAdmission(
        database,
        {
            "version": 3,
            "service_unit_id": scope.service_unit_id,
            "nas_root": binding["nas_roots"][scope.service_unit_id],
            "migration_id": migration_id,
        },
    )


async def tenant_maintenance_response(_request, _error):
    """One safe response for failures from endpoints and outer middleware."""
    from starlette.responses import JSONResponse

    return JSONResponse(
        status_code=503,
        content={
            "detail": "Conversation tenant is under maintenance",
            "code": TenantNotPublished.code,
        },
        headers={"Retry-After": "30"},
    )
