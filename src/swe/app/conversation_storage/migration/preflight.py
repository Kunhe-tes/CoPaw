# -*- coding: utf-8 -*-
"""Read-only structural checks and a DDL-free migration SQL boundary."""

from contextlib import asynccontextmanager
import re
import time

from ....database.prepared import PreparedInsert
from ..schema_contract import COLUMNS, DEFAULTS, EXTRAS, CHARSETS, INDEXES
from .install import _columns, _indexes, _encoding_matches, SHARE_COLUMNS


class DMLDatabase:
    """Keep transaction/session escapes behind the same SQL policy."""

    def __init__(self, database, *, owner=None):
        self._database = database
        self._owner = owner or database
        self.config = self._owner.config

    @property
    def is_connected(self):
        return self._owner.is_connected

    @property
    def max_allowed_packet(self):
        return self._database.max_allowed_packet

    @property
    def _in_transaction(self):
        return self._database._in_transaction

    @asynccontextmanager
    async def acquire(self):
        async with self._owner.acquire() as session:
            yield DMLDatabase(session, owner=self._owner)

    @staticmethod
    def check(query):
        if (
            not isinstance(query, str)
            or ";" in query
            or not re.match(
                r"\A\s*(?:SELECT|INSERT|UPDATE|DELETE)\s",
                query,
                re.IGNORECASE,
            )
            or re.search(r"\b(?:OUTFILE|DUMPFILE)\b", query, re.IGNORECASE)
        ):
            raise ValueError("direct migration permits parameterized DML only")
        return query

    async def fetch_one(self, query, params=None):
        return await self._query("fetch_one", query, params)

    async def fetch_all(self, query, params=None):
        return await self._query("fetch_all", query, params)

    async def execute(self, query, params=None):
        return await self._query("execute", query, params)

    async def execute_result(self, query, params=None):
        return await self._query("execute_result", query, params)

    async def insert(self, query, params=None):
        return await self._query("insert", query, params)

    async def _query(self, method, query, params, **options):
        from .progress import current_progress

        if method == "insert_prepared" and isinstance(query, PreparedInsert):
            self.check(query.prefix + query.row_template + query.suffix)
        else:
            query = self.check(query)
        progress = current_progress()
        started = time.monotonic()
        try:
            return await getattr(self._database, method)(
                query,
                params,
                **options,
            )
        finally:
            if progress is not None:
                progress.data["db_calls"] += 1
                progress.data["db_seconds"] += time.monotonic() - started

    async def execute_many(self, query, params_list):
        return await self._query("execute_many", query, params_list)

    async def insert_prepared(self, template, rows, **options):
        if not isinstance(template, PreparedInsert):
            raise ValueError(
                "direct migration requires a fixed prepared insert",
            )
        return await self._query(
            "insert_prepared",
            template,
            rows,
            **options,
        )

    @asynccontextmanager
    async def transaction(self):
        async with self._owner.transaction() as transaction:
            yield DMLDatabase(transaction, owner=self._owner)


class _SchemaMetadata:
    """One short-lived metadata read per check, never cached across sources."""

    def __init__(self, schema, rows):
        self.schema, self.rows = schema, rows

    @classmethod
    async def load(cls, database, schema):
        names = (
            *COLUMNS,
            "swe_chat_shares",
            *CONTROL_COLUMNS,
            "swe_conversation_migration_tenants",
            "swe_conversation_migration_sources",
        )
        condition = " WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ("
        condition += ",".join("%s" for _ in names) + ")"
        specs = {
            "COLUMNS": (
                "TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,"
                "COLUMN_DEFAULT,EXTRA,GENERATION_EXPRESSION,"
                "CHARACTER_SET_NAME,COLLATION_NAME,ORDINAL_POSITION",
                "TABLE_NAME,ORDINAL_POSITION",
            ),
            "STATISTICS": (
                "TABLE_NAME,INDEX_NAME,NON_UNIQUE,COLUMN_NAME,"
                "SEQ_IN_INDEX,SUB_PART,IS_VISIBLE",
                "TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX",
            ),
            "TABLES": ("TABLE_NAME,ENGINE,ROW_FORMAT", "TABLE_NAME"),
        }
        rows = {}
        for table, (columns, order) in specs.items():
            rows[table] = await database.fetch_all(
                "SELECT "
                + columns
                + " FROM information_schema."
                + table
                + condition
                + " ORDER BY "
                + order,
                (schema, *names),
            )
        return cls(schema, rows)

    async def fetch_all(self, query, params):
        if not params or params[0] != self.schema:
            raise ValueError("metadata schema differs from checked schema")
        for table, rows in self.rows.items():
            if "FROM information_schema." + table in query:
                return [
                    row
                    for row in rows
                    if len(params) == 1 or row["TABLE_NAME"] == params[1]
                ]
        raise ValueError("only schema metadata queries are supported")

    async def fetch_one(self, query, params):
        rows = await self.fetch_all(query, params)
        return rows[0] if rows else None


async def check_migration_schema(
    database,
    schema,
    *,
    source_isolation=False,
):
    metadata = await _SchemaMetadata.load(database, schema)
    await check_schema(metadata, schema, finalized=False)
    await check_tenant_schema(
        metadata,
        schema,
        source_isolation=source_isolation,
    )


async def check_schema(database, schema, *, finalized=False):
    """Never create or repair missing tables; accept one defined NULL transition."""
    await check_control_schema(database, schema)
    for table, expected in COLUMNS.items():
        columns = await _columns(database, schema, table)
        actual = {
            r["COLUMN_NAME"]: (r["COLUMN_TYPE"].lower(), r["IS_NULLABLE"])
            for r in columns
        }
        if actual != expected:
            raise ValueError("precreated columns differ: " + table)
        for row in columns:
            name = row["COLUMN_NAME"]
            if (
                row["GENERATION_EXPRESSION"]
                or row["EXTRA"] != EXTRAS[table].get(name, "")
                or row["COLUMN_DEFAULT"] != DEFAULTS[table].get(name)
                or not _encoding_matches(row, CHARSETS[table][name])
            ):
                raise ValueError(
                    "precreated column definition differs: "
                    + table
                    + "."
                    + name,
                )
        if await _indexes(database, schema, table) != INDEXES[table]:
            raise ValueError("precreated indexes differ: " + table)
    shares = await _columns(database, schema, "swe_chat_shares")
    original = [r for r in shares if r["COLUMN_NAME"] in SHARE_COLUMNS]
    if tuple(r["COLUMN_NAME"] for r in original) != SHARE_COLUMNS:
        raise ValueError("original eight share columns are required")
    extras = {
        r["COLUMN_NAME"]: (
            r["COLUMN_TYPE"].lower(),
            r["IS_NULLABLE"],
            r["COLUMN_DEFAULT"],
            r["EXTRA"],
            r["GENERATION_EXPRESSION"],
        )
        for r in shares
        if r["COLUMN_NAME"] not in SHARE_COLUMNS
    }
    expected = {
        name: ("bigint unsigned", "YES", None, "", "")
        for name in ("publication_id", "byte_offset", "byte_length")
    }
    expected["service_unit_key"] = (
        "varbinary(256)",
        "NO" if finalized else "YES",
        None,
        "",
        "",
    )
    if not finalized and extras.get("service_unit_key") == (
        "varbinary(256)",
        "NO",
        None,
        "",
        "",
    ):
        expected["service_unit_key"] = extras["service_unit_key"]
    if extras != expected:
        raise ValueError("precreated share extension differs")
    indexes = await _indexes(database, schema, "swe_chat_shares")
    for name, spec in {
        "PRIMARY": (0, ("token",)),
        "ix_swe_chat_shares_publication": (1, ("publication_id",)),
        "ix_swe_chat_shares_service_chat": (
            1,
            ("service_unit_key", "chat_id"),
        ),
        "ix_swe_chat_shares_service_creator": (
            1,
            ("service_unit_key", "creator_id"),
        ),
    }.items():
        if indexes.get(name) != spec:
            raise ValueError("precreated share index differs: " + name)
    names = list(COLUMNS) + [
        "swe_chat_shares",
        "swe_conversation_migration_jobs",
        "swe_conversation_migration_entries",
    ]
    rows = await database.fetch_all(
        "SELECT TABLE_NAME,ENGINE,ROW_FORMAT FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s",
        (schema,),
    )
    found = {r["TABLE_NAME"]: r for r in rows}
    if any(
        name not in found
        or found[name]["ENGINE"] != "InnoDB"
        or found[name]["ROW_FORMAT"].lower() != "dynamic"
        for name in names
    ):
        raise ValueError(
            "all business and migration tables must be precreated InnoDB DYNAMIC",
        )
    return {"original_share_columns": original, "share_indexes": indexes}


CONTROL_COLUMNS = {
    "swe_conversation_migration_jobs": {
        "migration_id": ("varbinary(36)", "NO", ""),
        "manifest_version": ("int unsigned", "NO", ""),
        "state": ("varchar(16)", "NO", ""),
        "target_binding_text": ("mediumtext", "NO", ""),
        "source_binding_text": ("mediumtext", "NO", ""),
        "verification_text": ("mediumtext", "YES", ""),
        "created_at": ("datetime(6)", "NO", ""),
        "updated_at": ("datetime(6)", "NO", ""),
    },
    "swe_conversation_migration_entries": {
        "id": ("bigint unsigned", "NO", "auto_increment"),
        "migration_id": ("varbinary(36)", "NO", ""),
        "entry_kind": ("varbinary(32)", "NO", ""),
        "source_key": ("varbinary(2048)", "NO", ""),
        "state": ("varchar(16)", "NO", ""),
        "target_id": ("bigint unsigned", "YES", ""),
        "operation_key": ("varbinary(64)", "YES", ""),
        "details_text": ("mediumtext", "YES", ""),
        "created_at": ("datetime(6)", "NO", ""),
        "updated_at": ("datetime(6)", "NO", ""),
    },
}
CONTROL_INDEXES = {
    "swe_conversation_migration_jobs": {
        "PRIMARY": (0, ("migration_id",)),
        "ix_conv_migration_job_state": (1, ("state", "migration_id")),
    },
    "swe_conversation_migration_entries": {
        "PRIMARY": (0, ("id",)),
        "uq_conv_migration_source": (
            0,
            ("migration_id", "entry_kind", "source_key"),
        ),
        "ix_conv_migration_entry_state": (1, ("migration_id", "state", "id")),
        "ix_conv_migration_target": (1, ("entry_kind", "target_id")),
    },
}


async def check_control_schema(database, schema, *, tables=None):
    """Require the exact DBA control contract before allocating durable IDs."""
    for table in CONTROL_COLUMNS if tables is None else tables:
        rows = await _columns(database, schema, table)
        actual = {
            row["COLUMN_NAME"]: (
                row["COLUMN_TYPE"].lower(),
                row["IS_NULLABLE"],
                row["EXTRA"].lower(),
            )
            for row in rows
        }
        if actual != CONTROL_COLUMNS[table]:
            raise ValueError("precreated migration columns differ: " + table)
        for row in rows:
            name = row["COLUMN_NAME"]
            charset, collation = (
                row["CHARACTER_SET_NAME"],
                row["COLLATION_NAME"],
            )
            if name == "state":
                encoding = charset == "ascii" and collation == "ascii_bin"
            elif row["COLUMN_TYPE"].lower() == "mediumtext":
                encoding = (
                    charset == "utf8mb4"
                    and isinstance(collation, str)
                    and collation.startswith("utf8mb4_")
                )
            else:
                encoding = charset is None and collation is None
            if (
                row["COLUMN_DEFAULT"] is not None
                or row["GENERATION_EXPRESSION"]
                or not encoding
            ):
                raise ValueError(
                    "precreated migration column definition differs: "
                    + table
                    + "."
                    + name,
                )
        if await _indexes(database, schema, table) != CONTROL_INDEXES[table]:
            raise ValueError("precreated migration indexes differ: " + table)


TENANT_CONTROL_COLUMNS = {
    "migration_id": ("varbinary(36)", "NO", ""),
    "service_unit_key": ("varbinary(256)", "NO", ""),
    "tenant_key": ("varbinary(256)", "NO", ""),
    "state": ("varchar(24)", "NO", ""),
    "evidence_text": ("longtext", "NO", ""),
    "verification_text": ("longtext", "NO", ""),
    "failure_text": ("longtext", "YES", ""),
    "attempts": ("int unsigned", "NO", ""),
    "updated_at": ("datetime(6)", "NO", ""),
    "published_at": ("datetime(6)", "YES", ""),
}


async def check_tenant_schema(database, schema, *, source_isolation=False):
    """Explicit opt-in contract; legacy control schemas remain supported."""
    table = (
        "swe_conversation_migration_sources"
        if source_isolation
        else "swe_conversation_migration_tenants"
    )
    expected_columns = dict(TENANT_CONTROL_COLUMNS)
    if source_isolation:
        expected_columns["source_key"] = ("varbinary(256)", "NO", "")
    rows = await _columns(database, schema, table)
    actual = {
        row["COLUMN_NAME"]: (
            row["COLUMN_TYPE"].lower(),
            row["IS_NULLABLE"],
            row["EXTRA"].lower(),
        )
        for row in rows
    }
    if actual != expected_columns:
        raise ValueError("precreated tenant migration columns differ")
    for row in rows:
        kind = row["COLUMN_TYPE"].lower()
        charset, collation = row["CHARACTER_SET_NAME"], row["COLLATION_NAME"]
        if kind == "varchar(24)":
            encoding = (charset, collation) == ("ascii", "ascii_bin")
        elif kind == "longtext":
            encoding = (charset, collation) == ("utf8mb4", "utf8mb4_bin")
        else:
            encoding = charset is None and collation is None
        if (
            row["COLUMN_DEFAULT"] is not None
            or row["GENERATION_EXPRESSION"]
            or not encoding
        ):
            raise ValueError("precreated tenant migration definition differs")
    if await _indexes(database, schema, table) != {
        "PRIMARY": (
            0,
            ("migration_id", "service_unit_key", "tenant_key")
            + (("source_key",) if source_isolation else ()),
        ),
    }:
        raise ValueError("precreated tenant migration indexes differ")
    info = await database.fetch_one(
        "SELECT ENGINE,ROW_FORMAT FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
        (schema, table),
    )
    if (
        not info
        or info["ENGINE"] != "InnoDB"
        or info["ROW_FORMAT"].lower() != "dynamic"
    ):
        raise ValueError("tenant migration table requires InnoDB DYNAMIC")
